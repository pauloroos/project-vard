"""Loja de tarefas da oficina: %LOCALAPPDATA%/rdl-vard/tarefas.json.

Vários processos escrevem aqui (oficina, vigia, consulta e trabalhadores): toda leitura e escrita
passa pela trava de arquivo (msvcrt) e a gravação é atômica (temporário + os.replace).
As funções recebem `arq=None` e resolvem o caminho na hora (os testes trocam ARQUIVO).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import msvcrt
import os
import re
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from vard import config

PASTA = config.pasta_dados()          # pastas do usuário, resolvidas na importação (os testes trocam ARQUIVO)
ARQUIVO = PASTA / "tarefas.json"
PASTA_RESULTADOS = PASTA / "tarefas"

AGENTES = ("claude", "codex", "opencode", "agy")
FERRAMENTAS = (*AGENTES, "pesquisa", "agente_remoto", "manha", "ata", "delegada")
VIVOS = ("preparando", "rodando", "esperando", "travou")
DECIDIDOS = ("aprovada", "descartada", "encerrada")
ESTADOS = (*VIVOS, "terminou", "falhou", *DECIDIDOS)
AVISAVEIS = ("esperando", "travou", "terminou", "falhou")


def agora() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def hora(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso) if iso else dt.datetime.fromtimestamp(0).astimezone()


def resumir(texto: str, limite: int = 200) -> str:
    linha = " ".join(str(texto).split())
    m = re.match(r"(.+?[.!?])(\s|$)", linha)
    frase = m.group(1) if m and len(m.group(1)) >= 15 else linha
    return frase if len(frase) <= limite else frase[: limite - 1].rstrip() + "…"


@dataclass
class Tarefa:
    n: int
    ferramenta: str
    repo: str
    pedido: str
    estado: str = "preparando"
    avisado: str = ""                 # último estado já avisado (vigia)
    origem: str = "voz"               # voz | agenda | telegram
    criada_em: str = field(default_factory=agora)
    atualizada_em: str = field(default_factory=agora)
    iniciada_em: str = ""             # quando o agente recebeu o pedido (carência da vigia)
    ultima_saida_em: str = field(default_factory=agora)
    worktree: str = ""                # <repo-id>::<caminho>
    caminho: str = ""
    branch: str = ""
    terminal: str = ""                # handle do Orca
    cursor: int | None = None         # nextCursor do último terminal read (fluxo; TUI não tem fluxo)
    tela_hash: str = ""               # crc32 da última tela lida: TUI só "mexe" na tela (ver oficina.observar)
    pid: int | None = None            # trabalhador
    pid_inicio: float | None = None   # create_time do processo do pid: o Windows reaproveita pid
    resumo: str = ""
    resultado: str = ""               # caminho do arquivo com a resposta completa
    erro: str = ""
    bloqueio: str = ""                # blockedReason do Orca enquanto "esperando" numa pergunta de confiança
    agente: str = ""                  # delegada: quem respondeu (ou vai responder)
    reserva: str = ""                 # delegada: agente de reserva se o primeiro ficar sem cota ou sem login
    link: str = ""                    # delegada: link para o usuário reconectar o conector
    tentativas: int = 0               # delegada: retomadas depois do login
    modelo: str = ""                  # delegada: modelo do Claude pedido ("" = padrão do config)
    versao: int = 0                   # sobe a cada gravação: base do comparar-e-trocar entre processos

    @property
    def aberta(self) -> bool:
        """Viva, ou terminada esperando o usuário aprovar ou descartar (só tarefas de código)."""
        return self.estado in VIVOS or (self.estado == "terminou" and self.ferramenta in AGENTES)

    @classmethod
    def de_dict(cls, d: dict) -> "Tarefa":
        nomes = {f.name for f in fields(cls)}
        valores = {k: v for k, v in d.items() if k in nomes}
        # Adaptador legado: normaliza liv só na leitura, sem regravar a loja.
        if valores.get("ferramenta") == "liv":
            valores["ferramenta"] = "agente_remoto"
        return cls(**valores)


CAMPOS = {f.name for f in fields(Tarefa)}
IMUTAVEIS = {"n", "criada_em"}


def _arq(arq: Path | None) -> Path:
    """arq explícito > VARD_TAREFAS_ARQUIVO (provas e trabalhadores com loja à parte) > ARQUIVO."""
    if arq:
        return Path(arq)
    return Path(os.environ["VARD_TAREFAS_ARQUIVO"]) if os.environ.get("VARD_TAREFAS_ARQUIVO") else ARQUIVO


@contextlib.contextmanager
def trava(arq: Path | None = None, espera: float = 10.0):
    """Trava exclusiva entre processos no byte 0 de <arq>.lock (o Windows solta se o processo morrer)."""
    alvo = Path(f"{_arq(arq)}.lock")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(alvo, os.O_RDWR | os.O_CREAT)
    try:
        fim = time.monotonic() + espera
        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= fim:
                    raise TimeoutError(f"{alvo.name} ocupado há mais de {espera:.0f} s") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def _ler(arq: Path) -> dict:
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"proximo": 1, "tarefas": []}
    except ValueError as exc:
        raise ValueError(f"{arq} ilegível; não vou sobrescrever") from exc
    if not isinstance(dados, dict) or not isinstance(dados.get("tarefas"), list):
        raise ValueError(f"{arq} ilegível; não vou sobrescrever")
    return dados


def _gravar(arq: Path, dados: dict) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(dados, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, arq)


def listar(arq: Path | None = None) -> list[Tarefa]:
    arq = _arq(arq)
    with trava(arq):
        return [Tarefa.de_dict(d) for d in _ler(arq)["tarefas"]]


def obter(n: int, arq: Path | None = None) -> Tarefa | None:
    return next((t for t in listar(arq) if t.n == n), None)


def _telegram_recente() -> bool:
    marca = Path(os.environ.get("VARD_MARCA_TELEGRAM") or PASTA / "ultimo-telegram.json")
    try:
        dados = json.loads(marca.read_text(encoding="utf-8"))
        return isinstance(dados, dict) and 0 <= time.time() - float(dados["ts"]) < 120
    except (OSError, ValueError, TypeError, KeyError):
        return False


def nova(ferramenta: str, repo: str, pedido: str, *, origem: str = "voz", arq: Path | None = None,
         **extras) -> Tarefa:
    if ferramenta not in FERRAMENTAS:
        raise ValueError(f"ferramenta desconhecida: {ferramenta}")
    ruins = set(extras) - (CAMPOS - IMUTAVEIS - {"versao", "ferramenta", "repo", "pedido", "origem"})
    if ruins:
        raise ValueError(f"campos desconhecidos: {sorted(ruins)}")
    if origem == "voz" and _telegram_recente():
        origem = "telegram"
    arq = _arq(arq)
    with trava(arq):
        dados = _ler(arq)
        t = Tarefa(n=int(dados.get("proximo", 1)), ferramenta=ferramenta, repo=repo, pedido=pedido, origem=origem,
              **extras)
        dados["proximo"] = t.n + 1
        dados["tarefas"].append(asdict(t))
        _gravar(arq, dados)
    return t


def atualizar(n: int, arq: Path | None = None, *, se_estado: str | None = None, se_versao: int | None = None,
              **campos) -> Tarefa:
    return _atualizar(n, arq, se_estado, se_versao, campos)[0]


def trocar(n: int, arq: Path | None = None, *, se_estado: str, se_versao: int, **campos) -> tuple[Tarefa, bool]:
    """Comparar-e-trocar que diz se gravou: (tarefa atual, True só para quem de fato gravou)."""
    return _atualizar(n, arq, se_estado, se_versao, campos)


def reivindicar(n: int, arq: Path | None = None, *, se_estado: str, se_versao: int) -> bool:
    """Compara-e-troca sem campos: True só para quem de fato gravou (quem perdeu a corrida recebe False)."""
    return _atualizar(n, arq, se_estado, se_versao, {})[1]


def _atualizar(n: int, arq: Path | None, se_estado: str | None, se_versao: int | None,
               campos: dict) -> tuple[Tarefa, bool]:
    """Grava `campos` na tarefa n, sob trava. Com `se_estado`, é comparar-e-trocar: se a tarefa já não está
    nesse estado (alguém aprovou, descartou ou respondeu enquanto o chamador observava), nada é gravado e
    a tarefa atual é devolvida. `se_versao` faz o mesmo para qualquer gravação feita por outro processo,
    mesmo sem mudança de estado (ex.: o usuário respondeu). Quem precisa saber se gravou compara `.versao`."""
    desconhecidos = (set(campos) - CAMPOS) | (set(campos) & (IMUTAVEIS | {"versao"}))
    if desconhecidos:
        raise ValueError(f"campos desconhecidos: {sorted(desconhecidos)}")
    if "estado" in campos and campos["estado"] not in ESTADOS:
        raise ValueError(f"estado inválido: {campos['estado']}")
    arq = _arq(arq)
    with trava(arq):
        dados = _ler(arq)
        for d in dados["tarefas"]:
            if d.get("n") == n:
                if se_estado is not None and d.get("estado") != se_estado:
                    return Tarefa.de_dict(d), False
                if se_versao is not None and d.get("versao", 0) != se_versao:
                    return Tarefa.de_dict(d), False
                d.update(campos)
                d["versao"] = d.get("versao", 0) + 1
                d["atualizada_em"] = agora()
                _gravar(arq, dados)
                return Tarefa.de_dict(d), True
    raise KeyError(f"tarefa {n} não existe")


def arquivo_resultado(n: int, arq: Path | None = None) -> Path:
    """Mesma precedência de _arq: arq explícito, depois VARD_TAREFAS_ARQUIVO (loja à parte: os resultados ficam
    ao lado dela, não nos do usuário), depois PASTA_RESULTADOS."""
    if arq or os.environ.get("VARD_TAREFAS_ARQUIVO"):
        pasta = _arq(arq).parent / "tarefas"
    else:
        pasta = PASTA_RESULTADOS
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{n}.md"
