"""Regras da oficina: repositórios conhecidos, preparo do agente no Orca, classificação do estado
do terminal e frases. Nada de MCP aqui (isso é oficina_mcp.py); nada imprime.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import subprocess
import tomllib
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path

from vard import config, tarefas
from vard.orca_cli import ErroOrca
from vard.seguro import Frase

log = logging.getLogger("vard.oficina")
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NOMES = {"claude": "Claude", "codex": "Codex", "opencode": "OpenCode", "agy": "Antigravity", "pesquisa": "pesquisa",
         "agente_remoto": "agente remoto", "manha": "rotina da manhã", "ata": "ata da reunião", "delegada": "consulta"}
ESTADO_FALADO = {
    "preparando": "abrindo", "rodando": "rodando", "esperando": "esperando sua resposta",
    "travou": "sem saída há mais de 10 minutos", "terminou": "terminou", "falhou": "falhou",
    "aprovada": "aprovada, esperando o merge", "descartada": "descartada", "encerrada": "encerrada",
}
# Estado do agente segundo o Orca (worktree ps -> agents[]), se o passo 1 achou um confiável.
# Conferido em 12/10 (fixtures worktree-ps-*.json): agents[].state vale working / waiting / done, mas NÃO é
# confiável: depois de recusar uma permissão no Claude o estado ficou "waiting" para sempre, mesmo com o agente
# parado e ocioso. Por isso fica vazio; a classificação usa o terminal (tui-idle + tela). Se algum dia o Orca
# corrigir, preencha {"working": "rodando", "waiting": "esperando", "done": "terminou"} e leia o estado em observar.
MAPA_ORCA: dict[str, str] = {}
PERGUNTA = re.compile(r"\?\s*$|\(s/n\)|\(y/n\)|\[y/n\]|do you want|allow (this|once|always)|approve|permitir|"
                      r"deseja|yes, and don't ask", re.IGNORECASE)
MOLDURA = re.compile(r"[│┃║╭╮╰╯─━═▌▐█❯›»•●◆◇✓✔✗✘⏺⎿]+")
# Linhas de rodapé que as TUIs repintam depois do resumo; encerram a leitura do RESUMO: (o ">" sozinho é a caixa de
# entrada vazia do agy, entre as duas réguas)
RODAPE = re.compile(r"^(worked for|ask codex|\? for shortcuts|gpt-|[✻▣╹⏸◉]|build |esc |enter |>\s*$)", re.IGNORECASE)


FRASE_BLOQUEIO = "pede confirmação de confiança na pasta (responda direto no Orca)"


class ErroGit(Exception):
    """O git não respondeu (não abriu, estourou o tempo ou saiu com erro): diferente de "nada a mostrar"."""


class ErroOficina(Frase):
    """Falha que vira frase para o usuário."""


class JaReivindicada(ErroOficina):
    """Outro trabalhador já pegou (ou já passou) esta tarefa: quem perdeu não pode marcá-la como falhou."""


@dataclass(frozen=True)
class Repo:
    apelido: str
    caminho: str
    github: str
    base: str
    apelidos: tuple[str, ...]


def simples(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace("-", " ").replace("_", " ").split())


def _toml(caminho: Path) -> dict:
    with Path(caminho).open("rb") as f:
        return tomllib.load(f)


def _existe(caminho: Path | None, nome: str) -> Path | None:
    """O arquivo pedido (caminho explícito ou o da pasta do usuário), resolvido NA CHAMADA — nunca na
    importação. None quando não existe: configuração ausente não é erro."""
    alvo = Path(caminho) if caminho else config.arquivo_config(nome)
    return alvo if alvo.is_file() else None


def carregar_repos(caminho: Path | None = None) -> dict[str, Repo]:
    alvo = _existe(caminho, "repos.toml")
    if alvo is None:
        return {}
    dados = _toml(alvo).get("repos", {})
    return {nome: Repo(nome, str(r["caminho"]), str(r.get("github", "")), str(r.get("base", "main")),
                       tuple(str(a) for a in r.get("apelidos", []))) for nome, r in dados.items()}


def dono_github(caminho: Path | None = None) -> str:
    alvo = _existe(caminho, "repos.toml")
    if alvo is None:
        return ""
    return str(_toml(alvo).get("github", {}).get("dono", ""))


def carregar_conf(caminho: Path | None = None) -> dict:
    alvo = _existe(caminho, "oficina.toml")
    return _toml(alvo) if alvo is not None else {}


def resolver_repo(falado: str, repos: dict[str, Repo]) -> Repo | None:
    alvo = simples(falado)
    if not alvo:
        return None
    for r in repos.values():
        if alvo in {simples(r.apelido), *(simples(a) for a in r.apelidos)}:
            return r
    return None


def slug(texto: str, limite: int = 30) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", simples(texto)).strip("-")
    if len(s) > limite:
        s = s[:limite].rsplit("-", 1)[0]
    return s or "tarefa"


def nome_worktree(n: int, pedido: str) -> str:
    return f"vard-{n}-{slug(pedido)}"


def linha_pedido(n: int, pedido: str) -> str:
    """Uma linha só (Enter no meio mandaria o pedido pela metade), com o combinado do fim."""
    linha = " ".join(pedido.split())[:1500]
    return (f"[Tarefa {n} do Vard] {linha} Trabalhe só nesta pasta. Ao terminar, rode os testes do projeto, "
            "faça commit no branch atual e escreva um resumo de até 3 linhas começando com RESUMO:.")


def montar_comando(agente: dict, linha: str) -> str:
    """Linha digitada no PowerShell do terminal do Orca: agente + pedido como literal + '; exit'.

    O PowerShell trata ‘ ’ ‚ ‛ como aspas simples: viram ' antes de dobrar.
    """
    normal = re.sub("[\u2018\u2019\u201a\u201b]", "'", linha)
    literal = "'" + normal.replace("'", "''") + "'"
    forma = agente.get("prompt", "posicional")
    argumento = literal if forma == "posicional" else f"{forma} {literal}"
    return f"{agente['comando']} {argumento}; exit"


def montar_comando_terminal(agente: dict, linha: str) -> str:
    """Mesmo literal do montar_comando, mas para a janela do executor terminal: agente no modo não interativo,
    pedido como último argumento posicional e SEM '; exit' (a janela grava a saída num log e termina sozinha)."""
    normal = re.sub("[‘’‚‛]", "'", linha)
    literal = "'" + normal.replace("'", "''") + "'"
    return f"{agente['terminal']} {literal}"


def _ferramenta(ferramenta: str) -> str:
    f = simples(ferramenta).replace(" ", "")
    return {"claudecode": "claude", "antigravity": "agy", "antigravitycli": "agy", "antigraviti": "agy"}.get(f, f)


def achar_duplicada(ferramenta: str, repo: str, pedido: str, *, repos: dict[str, Repo], agora: dt.datetime,
                    arq: Path | None = None, janela_s: int = 60) -> tarefas.Tarefa | None:
    """Tarefa viva idêntica (ferramenta, repo, pedido) criada há menos de `janela_s`: o modelo repete chamadas."""
    f = _ferramenta(ferramenta)
    r = resolver_repo(repo, repos)
    apelido = r.apelido if r and f in tarefas.AGENTES else ""
    for t in tarefas.listar(arq):
        if (t.ferramenta == f and t.repo == apelido and t.pedido == pedido.strip() and t.estado in tarefas.VIVOS
                and (agora - tarefas.hora(t.criada_em)).total_seconds() < janela_s):
            return t
    return None


def registrar(ferramenta: str, repo: str, pedido: str, *, repos: dict[str, Repo], arq: Path | None = None,
              origem: str = "voz") -> tarefas.Tarefa:
    f = _ferramenta(ferramenta)
    if f not in (*tarefas.AGENTES, "pesquisa"):
        raise ErroOficina(f"Não sei disparar '{ferramenta}'. Posso usar Claude, Codex, OpenCode, Antigravity ou pesquisa.")
    if not pedido.strip():
        raise ErroOficina("Diga o que a tarefa deve fazer.")
    apelido = ""
    if f in tarefas.AGENTES:
        r = resolver_repo(repo, repos)
        if not r:
            raise ErroOficina(f"Não conheço o projeto '{repo}'. Conheço: {', '.join(sorted(repos))}. Em qual deles?")
        apelido = r.apelido
    return tarefas.nova(f, apelido, pedido.strip(), origem=origem, arq=arq)


PADRAO_EXCLUDE = "vard-*/"


def garantir_exclude(repo_caminho: str) -> bool:
    """Orca não deixa escolher a pasta do worktree (sem flag no `worktree create`; o nome é saneado): ele nasce em
    <repo>/vard-N-*. Acrescenta `vard-*/` ao .git/info/exclude do repositório (local, nunca vai para commit),
    para o git status e o git add -A do checkout principal não verem a pasta. Idempotente; True se gravou."""
    git_dir = Path(repo_caminho) / ".git"
    if not git_dir.is_dir():
        return False                    # worktree ligado ou repositório fora do padrão: não mexo
    arq = git_dir / "info" / "exclude"
    atual = arq.read_text(encoding="utf-8") if arq.exists() else ""
    if PADRAO_EXCLUDE in (l.strip() for l in atual.splitlines()):
        return False
    arq.parent.mkdir(parents=True, exist_ok=True)
    with arq.open("a", encoding="utf-8", newline="\n") as f:
        f.write(("" if not atual or atual.endswith("\n") else "\n") + PADRAO_EXCLUDE + "\n")
    return True


AGY_SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def confiar_agy(caminho: str, arq: Path = AGY_SETTINGS) -> bool:
    """O Antigravity CLI (agy) só confia em caminhos exatos de `trustedWorkspaces` (settings.json dele): confiar no
    repositório não vale para o worktree, e a TUI para na pergunta. Grava o caminho do worktree (com barra invertida,
    como o agy escreve) antes de abrir a aba. Idempotente; True se gravou."""
    if not arq.exists():
        return False
    dados = json.loads(arq.read_text(encoding="utf-8"))
    lista = dados.setdefault("trustedWorkspaces", [])
    alvo = str(Path(caminho)).replace("/", "\\")
    if alvo in lista:
        return False
    lista.append(alvo)
    tmp = arq.with_suffix(".json.tmp-vard")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, arq)
    return True


def clonar(github: str, caminho: str) -> None:
    """`git clone https://github.com/<github>.git <caminho>`: o executor terminal precisa da pasta do projeto
    para criar o worktree. Sem janela; falha (git ausente, tempo estourado ou repositório recusado) vira frase."""
    try:
        p = subprocess.run(["git", "clone", f"https://github.com/{github}.git", str(caminho)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600, stdin=subprocess.DEVNULL,
                           creationflags=SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ErroOficina(f"não consegui clonar o {github} ({type(exc).__name__})") from exc
    if p.returncode != 0:
        linhas = (p.stderr or p.stdout or "").strip().splitlines()
        raise ErroOficina(f"não consegui clonar o {github} ({(linhas[0] if linhas else f'saiu com {p.returncode}')[:120]})")


def preparar(n: int, *, orca, repos: dict[str, Repo], conf: dict, arq: Path | None = None) -> tarefas.Tarefa:
    """Roda no trabalhador: worktree novo e terminal visível com o agente já recebendo o pedido."""
    t = tarefas.obter(n, arq)
    if t is None or t.ferramenta not in tarefas.AGENTES:
        raise ErroOficina(f"A tarefa {n} não é de código.")
    if t.estado != "preparando":
        raise JaReivindicada(f"A tarefa {n} já está {ESTADO_FALADO[t.estado]}; não abro de novo.")
    # Reivindica sob a trava: dois trabalhadores que leram "preparando" ao mesmo tempo não criam dois worktrees.
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A tarefa {n} já está sendo aberta por outro trabalhador.")
    worktree = ""
    h = ""
    try:
        repo = repos[t.repo]
        e_terminal = getattr(orca, "e_terminal", False)
        if e_terminal and not Path(repo.caminho).exists():
            if not repo.github:
                raise ErroOficina("a pasta do projeto não existe e não há github cadastrado")
            clonar(repo.github, repo.caminho)
        try:
            garantir_exclude(repo.caminho)
        except OSError:
            log.warning("tarefa %s: não consegui gravar o exclude de %s", n, repo.caminho)
        wt = orca.criar_worktree(repo.caminho, nome_worktree(n, t.pedido))
        worktree = wt["worktree"]
        # Daqui em diante tudo é comparar-e-trocar em "preparando": o usuário pode ter descartado no meio.
        atual = tarefas.atualizar(n, arq, se_estado="preparando", worktree=worktree, caminho=wt["caminho"],
                                  branch=wt["branch"])
        if atual.estado != "preparando":
            return _limpar_perdida(orca, atual, worktree, "")
        if t.ferramenta == "agy":
            try:
                confiar_agy(wt["caminho"])
            except (OSError, ValueError):
                log.warning("tarefa %s: não consegui confiar o worktree no agy", n)
        agente = conf["agentes"][t.ferramenta]
        comando = (montar_comando_terminal if e_terminal else montar_comando)(agente, linha_pedido(n, t.pedido))
        h = orca.criar_terminal(f"id:{worktree}", comando, f"Vard #{n} {NOMES[t.ferramenta]}",
                                shell=conf.get("oficina", {}).get("shell", ""))
    except Exception as exc:  # noqa: BLE001 — qualquer falha de preparo vira "falhou", nunca "preparando" para sempre
        codigo = exc.codigo if isinstance(exc, ErroOrca) else type(exc).__name__
        limpeza: dict = {}
        if worktree:                  # o worktree já existe: remove; se não der, o id fica para o descartar limpar
            try:
                orca.remover_worktree(f"id:{worktree}", forcar=True)
                limpeza = {"worktree": "", "caminho": "", "branch": ""}
            except Exception:  # noqa: BLE001
                limpeza = {"worktree": worktree}
        return tarefas.atualizar(n, arq, se_estado="preparando", estado="falhou",
                                 erro=f"{type(exc).__name__}: {exc}"[:300],
                                 resumo=f"não consegui abrir a tarefa ({codigo})", **limpeza)
    inicio = tarefas.agora()
    final = tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando", terminal=h, iniciada_em=inicio,
                              ultima_saida_em=inicio)
    if final.estado != "rodando" or final.terminal != h:      # descartada enquanto abria: fecha tudo que abriu
        return _limpar_perdida(orca, final, worktree, h)
    return final


def _limpar_perdida(orca, atual: tarefas.Tarefa, worktree: str, terminal: str) -> tarefas.Tarefa:
    """Alguém mudou a tarefa (descartou) enquanto ela abria: o que este trabalhador criou não pode sobrar."""
    if terminal:
        try:
            orca.fechar_terminal(terminal)
        except Exception:  # noqa: BLE001 — já fechado
            pass
    if worktree:
        try:
            orca.remover_worktree(f"id:{worktree}", forcar=True)
        except Exception:  # noqa: BLE001
            log.warning("tarefa %s: não consegui remover o worktree %s depois do descarte", atual.n, worktree)
    return atual


@dataclass
class Observacao:
    saiu: bool = False
    ocioso: bool = False
    nova_saida: bool = False
    tela: str = ""
    estado_orca: str = ""
    bloqueio: str = ""                # blockedReason do wait tui-idle: o agente está parado numa pergunta
    tela_hash: str = ""               # crc32 da tela; TUI não tem fluxo de saída, só a tela muda


def _linhas_uteis(tela: str) -> list[str]:
    return [l for l in (" ".join(MOLDURA.sub(" ", x).split()) for x in tela.splitlines()) if l]


def parece_pergunta(tela: str) -> bool:
    """Olha o fim da tela, depois do último RESUMO: (o que veio antes é de rodadas já respondidas)."""
    i = tela.rfind("RESUMO:")
    depois = tela[i + len("RESUMO:"):] if i >= 0 else tela
    return any(PERGUNTA.search(l) for l in _linhas_uteis(depois)[-8:])


def extrair_resumo(tela: str) -> str:
    """Texto depois do último 'RESUMO:' (o pedido manda o agente terminar assim), até 3 linhas."""
    i = tela.rfind("RESUMO:")
    if i < 0:
        return ""
    linhas: list[str] = []
    for l in _linhas_uteis(tela[i + len("RESUMO:"):]):
        if RODAPE.match(l) or len(linhas) == 3:
            break
        linhas.append(l)
    return " ".join(linhas)[:300]


def classificar(t: tarefas.Tarefa, obs: Observacao, agora: dt.datetime, *, travou_apos: int = 600,
                carencia: int = 60) -> str:
    if obs.estado_orca in MAPA_ORCA:
        return MAPA_ORCA[obs.estado_orca]
    em_carencia = bool(t.iniciada_em) and (agora - tarefas.hora(t.iniciada_em)).total_seconds() < carencia
    if obs.saiu:
        # Fechou sem RESUMO logo ao abrir: o agente nem subiu (comando não achado, handle velho): falhou.
        return "falhou" if em_carencia and "RESUMO:" not in obs.tela else "terminou"
    if obs.bloqueio:                  # fora da carência: a pergunta de confiança aparece nos primeiros segundos
        return "esperando"
    if obs.ocioso and not em_carencia:
        return "esperando" if parece_pergunta(obs.tela) else "terminou"
    if obs.nova_saida:
        return "rodando"
    if (agora - tarefas.hora(t.ultima_saida_em)).total_seconds() >= travou_apos:
        return "travou"
    return t.estado if t.estado in ("rodando", "esperando", "travou") else "rodando"


def observar(t: tarefas.Tarefa, orca) -> tuple[Observacao, int | None]:
    if orca.esperar(t.terminal, "exit", 1000)[0]:
        try:
            tela = orca.ler(t.terminal, limite=120).texto
        except ErroOrca:
            tela = ""
        return Observacao(saiu=True, tela=tela), t.cursor
    try:
        return _observar_vivo(t, orca)
    except ErroOrca as exc:
        if exc.sumiu:                 # o terminal morreu entre o wait e a leitura
            return Observacao(saiu=True), t.cursor
        raise                         # outras falhas: quem chama (a vigia) trata por tarefa


def _observar_vivo(t: tarefas.Tarefa, orca) -> tuple[Observacao, int | None]:
    # Fixture: num agente TUI o fluxo (--cursor) fica vazio e o cursor em 0 para sempre (só a tela existe);
    # num terminal comum o fluxo funciona. Então "saída nova" = fluxo novo OU tela diferente da última vista.
    leitura = orca.ler(t.terminal, cursor=t.cursor or 0)
    ocioso, bloqueio = orca.esperar(t.terminal, "tui-idle", 1000)
    tela = orca.ler_tela(t.terminal)
    digest = f"{zlib.crc32(tela.encode('utf-8', 'replace')):08x}"
    nova = bool(leitura.texto.strip()) or digest != t.tela_hash
    return Observacao(ocioso=ocioso, nova_saida=nova, tela=tela, tela_hash=digest, bloqueio=bloqueio), leitura.proximo


def atualizar_estado(t: tarefas.Tarefa, *, orca, conf: dict, arq: Path | None = None,
                     agora: dt.datetime | None = None) -> tarefas.Tarefa:
    agora = agora or dt.datetime.now().astimezone()
    if t.estado not in (*tarefas.VIVOS, "terminou") or not t.terminal:
        return t                      # decidida, falhou ou ainda preparando: não há o que observar
    obs, cursor = observar(t, orca)
    o = conf.get("oficina", {})
    novo = classificar(t, obs, agora, travou_apos=int(o.get("travou_apos_s", 600)),
                       carencia=int(o.get("carencia_s", 60)))
    campos: dict = {}
    if cursor is not None and cursor != t.cursor:
        campos["cursor"] = cursor
    if obs.tela_hash and obs.tela_hash != t.tela_hash:
        campos["tela_hash"] = obs.tela_hash
    if obs.nova_saida:
        campos["ultima_saida_em"] = agora.isoformat(timespec="seconds")
    if novo != t.estado:
        campos["estado"] = novo
        campos["bloqueio"] = obs.bloqueio if novo == "esperando" else ""
        if novo not in tarefas.AVISAVEIS:
            campos["avisado"] = ""
        if novo == "terminou":
            campos["resumo"] = extrair_resumo(obs.tela) or (
                "o terminal fechou sem deixar resumo; pode ter dado errado, confira" if obs.saiu
                else "terminou sem deixar resumo")
        elif novo == "falhou":
            campos["resumo"] = "o terminal fechou logo ao abrir; o agente pode não ter subido"
        elif novo == "esperando":
            campos["resumo"] = FRASE_BLOQUEIO if obs.bloqueio else (
                _linhas_uteis(obs.tela) or ["fez uma pergunta"])[-1][:200]
        elif novo == "travou":
            campos["resumo"] = "sem saída há mais de 10 minutos"
    if not campos:
        return t
    # Comparar-e-trocar: a observação levou segundos; se o usuário aprovou, descartou ou respondeu nesse meio
    # tempo (outro processo), o estado já não é o de `t` e nada é gravado.
    # A versão cobre o que o estado não vê (uma resposta que mantém o estado "rodando").
    return tarefas.atualizar(t.n, arq, se_estado=t.estado, se_versao=t.versao, **campos)


def ha_quanto(iso: str, agora: dt.datetime) -> str:
    seg = max(0, int((agora - tarefas.hora(iso)).total_seconds()))
    if seg < 90:
        return "agora há pouco"
    if seg < 3600:
        return f"há {seg // 60} min"
    return f"há {seg // 3600} h"


def frase_tarefa(t: tarefas.Tarefa, agora: dt.datetime) -> str:
    onde = f" no {t.repo}" if t.repo else ""
    extra = f" ({t.resumo})" if t.resumo and t.estado in ("esperando", "terminou", "falhou") else ""
    if t.ferramenta == "delegada" and t.estado == "terminou":     # o resumo vem de terceiros (e-mail, issue): não ecoa
        extra = f' (diga "resultado da tarefa {t.n}")'
    quem = f"consulta ao {NOMES.get(t.agente, 'agente')}" if t.ferramenta == "delegada" else NOMES[t.ferramenta]
    return (f"Tarefa {t.n}, {quem}{onde}: {ESTADO_FALADO[t.estado]} "
            f"{ha_quanto(t.atualizada_em, agora)}{extra}.")


def frase_lista(ts: list[tarefas.Tarefa], agora: dt.datetime) -> str:
    if not ts:
        return "Nenhuma tarefa ainda."
    abertas = [t for t in ts if t.aberta]
    fechadas = [t for t in ts if not t.aberta][-10:]
    partes = ["Abertas:\n" + "\n".join(f"- {frase_tarefa(t, agora)}" for t in abertas) if abertas
              else "Nenhuma tarefa aberta."]
    if fechadas:
        partes.append("Últimas fechadas:\n" + "\n".join(f"- {frase_tarefa(t, agora)}" for t in reversed(fechadas)))
    return "\n".join(partes)


def git(caminho: str, *args: str, timeout: float = 20) -> str:
    try:
        p = subprocess.run(["git", "-C", caminho, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ErroGit(f"git {args[0] if args else ''}: {type(exc).__name__}") from exc
    if p.returncode != 0:
        raise ErroGit(f"git {args[0] if args else ''} saiu com {p.returncode}")
    return p.stdout.strip()


def _exigir(n: int, arq: Path | None) -> tarefas.Tarefa:
    t = tarefas.obter(n, arq)
    if t is None:
        raise ErroOficina(f"Não existe tarefa {n}.")
    return t


def _agora() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _base(t: tarefas.Tarefa, repos: dict[str, Repo]) -> str:
    return repos[t.repo].base if t.repo in repos else "main"


def resultado(n: int, *, repos: dict[str, Repo], arq: Path | None = None) -> str:
    t = _exigir(n, arq)
    if t.ferramenta == "delegada":
        from vard import delegada
        return delegada.resultado_texto(t) or frase_tarefa(t, _agora())
    if t.ferramenta not in tarefas.AGENTES:
        if t.resultado and Path(t.resultado).exists():
            return Path(t.resultado).read_text(encoding="utf-8")[:1500]
        return frase_tarefa(t, _agora())
    base = _base(t, repos)
    linhas = [frase_tarefa(t, _agora())]
    try:
        commits = git(t.caminho, "log", "--oneline", f"{base}..HEAD", "-n", "10")
        stat = git(t.caminho, "diff", "--stat", f"{base}...HEAD")
        sujos = git(t.caminho, "status", "--porcelain")
    except ErroGit:
        linhas.append("Não consegui ler o git da pasta dessa tarefa.")
        return "\n".join(linhas)
    linhas.append(f"Commits no branch {t.branch or '?'}:\n{commits}" if commits else "Nenhum commit novo no branch.")
    if stat:
        linhas.append(stat.splitlines()[-1].strip())
    if sujos:
        linhas.append(f"{len(sujos.splitlines())} arquivo(s) alterado(s) sem commit.")
    return "\n".join(linhas)


def responder(n: int, texto: str, *, orca, arq: Path | None = None) -> str:
    t = _exigir(n, arq)
    if t.ferramenta == "delegada":
        from vard import delegada
        return delegada.repetir(n, arq=arq, orca=orca)
    if t.ferramenta not in tarefas.AGENTES or not t.terminal:
        raise ErroOficina(f"A tarefa {n} não tem agente esperando resposta.")
    if t.estado not in ("rodando", "esperando", "travou", "terminou"):
        raise ErroOficina(f"A tarefa {n} está {ESTADO_FALADO[t.estado]}; não dá para responder.")
    if t.estado == "esperando" and t.bloqueio:
        raise ErroOficina(f"A tarefa {n} {FRASE_BLOQUEIO.replace(' (responda direto no Orca)', '')}. "
                          "Isso é decisão sua: responda direto no Orca.")
    orca.enviar(t.terminal, " ".join(texto.split()))
    inicio = tarefas.agora()
    tarefas.atualizar(n, arq, estado="rodando", avisado="", bloqueio="", iniciada_em=inicio,
                      ultima_saida_em=inicio)
    return f"Mandei para a tarefa {n}."


def aprovar(n: int, *, arq: Path | None = None) -> str:
    t = _exigir(n, arq)
    if t.ferramenta not in tarefas.AGENTES:
        raise ErroOficina("Só tarefa de código é aprovada; essa já chegou como resposta.")
    if t.estado not in ("terminou", "esperando", "travou"):
        raise ErroOficina(f"A tarefa {n} está {ESTADO_FALADO[t.estado]}; aprovo quando terminar.")
    tarefas.atualizar(n, arq, estado="aprovada")
    return f"Tarefa {n} aprovada. O branch {t.branch or 'dela'} fica esperando o seu merge."


def descartar(n: int, confirmado: bool, *, orca, repos: dict[str, Repo], arq: Path | None = None) -> str:
    t = _exigir(n, arq)
    if t.estado in ("descartada", "encerrada"):
        return f"A tarefa {n} já foi {t.estado}."
    if t.ferramenta not in tarefas.AGENTES:
        if t.terminal:
            try:
                orca.fechar_terminal(t.terminal)
            except ErroOrca:
                pass
        tarefas.atualizar(n, arq, estado="descartada", terminal="")
        return f"Tarefa {n} descartada."
    if t.estado == "preparando":
        # Ainda abrindo: o trabalhador é quem cria o terminal. Ganha a troca e ele limpa o que criar.
        perdida = tarefas.atualizar(n, arq, se_estado="preparando", estado="descartada")
        if perdida.estado == "descartada":
            if t.worktree or t.caminho:     # o worktree já existia: remove já (o trabalhador remove de novo, sem dano)
                try:
                    orca.remover_worktree(f"id:{t.worktree}" if t.worktree else f"path:{t.caminho}", forcar=True)
                except ErroOrca:
                    pass
            return (f"Tarefa {n} descartada. Ela ainda estava abrindo; o que o agente criar eu removo "
                    "assim que o Orca responder.")
        t = perdida                          # já subiu (rodando): segue o descarte normal, com terminal e tudo
    aprovada = t.estado == "aprovada"
    if not aprovada and not confirmado and t.caminho:
        try:
            tem_trabalho = bool(git(t.caminho, "status", "--porcelain")) or bool(
                git(t.caminho, "log", "--oneline", f"{_base(t, repos)}..HEAD"))
        except ErroGit:
            return (f"Não consegui conferir se a tarefa {n} tem alterações. "
                    "Se quiser jogar fora mesmo assim, confirme.")
        if tem_trabalho:
            return (f"A tarefa {n} tem alterações que não foram aprovadas. "
                    "Se quiser jogar fora mesmo assim, confirme.")
    if t.terminal:
        try:
            orca.fechar_terminal(t.terminal)
        except ErroOrca:
            pass  # terminal já fechado
    if t.worktree or t.caminho:
        orca.remover_worktree(f"id:{t.worktree}" if t.worktree else f"path:{t.caminho}", forcar=confirmado)
    tarefas.atualizar(n, arq, estado="encerrada" if aprovada else "descartada")
    if aprovada:
        return f"Worktree da tarefa {n} removido; o branch {t.branch} ficou para o merge."
    return f"Worktree da tarefa {n} removido."
