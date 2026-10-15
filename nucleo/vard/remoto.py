"""Agente remoto opcional por SSH; pedidos seguem exclusivamente por stdin.

T10: aceitar OpenClaw pelo comando SSH já existente, normalizando o envelope JSON do CLI (`envelope =
"openclaw"`); sessão por tarefa por padrão (`{sessao}`), sem `--deliver` (a entrega é do Vard).
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import tomllib
from pathlib import Path

from vard import avisos, config, segredos, tarefas
from vard.consulta import ErroConsulta
from vard.oficina import JaReivindicada

NOME_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
LISTAR = "sudo docker ps --format '{{.Names}}'"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT_S = 180
ENVELOPES = ("texto", "openclaw")


def carregar_conf() -> dict:
    arq = config.arquivo_config("remoto.toml")
    if not arq.exists():
        raise ErroConsulta("O agente remoto não está configurado.")
    try:
        with arq.open("rb") as f:
            conf = tomllib.load(f).get("remoto", {})
        chave, destino = ("", "")
        if "chave" not in conf or "destino" not in conf:
            chave, destino = segredos.remoto_ssh()
        conf = {"chave": chave, "destino": destino, "timeout_s": TIMEOUT_S,
                "nome": "o agente remoto", "container_prefixo": "", "envelope": "texto",
                "sessao": "tarefa", **conf}
        if not str(conf.get("destino", "")).strip():
            raise ErroConsulta("O agente remoto não está configurado.")
        if not str(conf.get("comando", "")).strip():
            raise ErroConsulta("O comando do agente remoto não está configurado.")
        if str(conf.get("envelope", "texto")).strip().lower() not in ENVELOPES:
            raise ErroConsulta("O envelope do agente remoto é inválido.")
        conf["timeout_s"] = float(conf["timeout_s"])
        if conf["timeout_s"] <= 0:
            raise ValueError("timeout")
        return conf
    except (OSError, ValueError, TypeError):
        raise ErroConsulta("A configuração do agente remoto é inválida.") from None


def nome() -> str:
    """Nome falado, disponível mesmo quando a integração ainda não foi configurada."""
    arq = config.arquivo_config("remoto.toml")
    try:
        with arq.open("rb") as f:
            return str(tomllib.load(f).get("remoto", {}).get("nome") or "o agente remoto")
    except (OSError, ValueError):
        return "o agente remoto"


def comando_ssh(chave: str, destino: str, comando: str) -> list[str]:
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if chave:
        args += ["-i", chave]
    return [*args, destino, comando]


def achar_container(nomes: str, prefixo: str, nome: str = "o agente remoto", excluir: tuple[str, ...] = ()) -> str:
    candidatos = [n.strip() for n in nomes.splitlines()
                  if n.strip().startswith(prefixo) and not any(e and e in n for e in excluir)]
    if len(candidatos) != 1:
        raise ErroConsulta(f"Achei {len(candidatos)} containers para {nome}; esperava um.")
    if not NOME_VALIDO.fullmatch(candidatos[0]):
        raise ErroConsulta(f"O nome do container de {nome} veio estranho; não vou montar o comando.")
    return candidatos[0]


def validar_openclaw(comando: str) -> None:
    """A entrega é do Vard e o webhook de admissão não traz a resposta: recusar os dois na configuração."""
    if "--deliver" in comando:
        raise ErroConsulta("O comando do OpenClaw não pode usar --deliver: a entrega é do Vard.")
    if "/hooks/agent" in comando:
        raise ErroConsulta("O webhook de admissão do OpenClaw não devolve a resposta; use o CLI.")


def normalizar_openclaw(saida: str) -> str:
    """Envelope do CLI do OpenClaw: usa `final`; sem ele, junta o texto dos `payloads`."""
    try:
        d = json.loads(str(saida).strip())
    except ValueError:
        raise ErroConsulta("O agente remoto respondeu em formato ilegível.") from None
    if not isinstance(d, dict):
        raise ErroConsulta("O agente remoto respondeu em formato inesperado.")
    final = str(d.get("final") or "").strip()
    if final:
        return final
    partes = []
    for p in d.get("payloads") or []:
        texto = str(p.get("text") or "").strip() if isinstance(p, dict) else str(p).strip()
        if texto:
            partes.append(texto)
    texto = "\n".join(partes).strip()
    if not texto:
        raise ErroConsulta("O agente remoto respondeu sem texto.")
    return texto


def normalizar(saida: str, envelope: str = "texto") -> str:
    if str(envelope).strip().lower() == "openclaw":
        return normalizar_openclaw(saida)
    return str(saida).strip()


def chave_sessao(n: int) -> str:
    """Sessão por tarefa por padrão; `sessao = "vard"` preserva o perfil antigo."""
    try:
        conf = carregar_conf()
    except ErroConsulta:
        conf = {}
    return "vard" if str(conf.get("sessao", "tarefa")).strip().lower() == "vard" else f"tarefa-{n}"


_SESSAO = threading.local()


def sessao_atual() -> str | None:
    """Sessão da tarefa em execução nesta thread (postas por `executar`); None fora de uma tarefa."""
    return getattr(_SESSAO, "valor", None)


def perguntar(pedido: str, *, executar=None, sessao: str | None = None) -> str:
    conf = carregar_conf()
    executar = executar or subprocess.run
    quem = conf["nome"] or "o agente remoto"
    comum = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
    comando = conf["comando"]
    envelope = str(conf.get("envelope", "texto")).strip().lower()
    if envelope == "openclaw":
        validar_openclaw(comando)
    if "{sessao}" in comando:
        comando = comando.replace("{sessao}", sessao or sessao_atual() or "vard")
    try:
        if conf["container_prefixo"]:
            p = executar(comando_ssh(conf["chave"], conf["destino"], LISTAR),
                         stdin=subprocess.DEVNULL, timeout=30, **comum)
            if p.returncode != 0:
                raise ErroConsulta(f"Não consegui chegar em {quem}: o ssh falhou.")
            container = achar_container(p.stdout, conf["container_prefixo"], quem, tuple(str(e) for e in conf.get("container_excluir", ())))
            comando = comando.replace("{container}", container)
        elif "{container}" in comando:
            raise ErroConsulta(f"O prefixo do container de {quem} não está configurado.")
        p = executar(comando_ssh(conf["chave"], conf["destino"], comando),
                     input=pedido, timeout=conf["timeout_s"], **comum)
    except subprocess.TimeoutExpired:
        raise ErroConsulta(f"{quem.capitalize()} demorou demais para responder ({conf['timeout_s']:g} s).") from None
    except FileNotFoundError:
        raise ErroConsulta(f"Não consegui chegar em {quem}: o ssh não está instalado neste PC.") from None
    if p.returncode != 0:
        raise ErroConsulta(f"{quem.capitalize()} não respondeu: o comando remoto falhou.")
    resposta = normalizar(p.stdout, envelope)
    if not resposta:
        raise ErroConsulta(f"{quem.capitalize()} respondeu vazio.")
    return resposta


def perguntar_com_trava(pedido: str, espera: float = TIMEOUT_S * 3, *, sessao: str | None = None) -> str:
    carregar_conf()  # Sem configuração, nem cria a trava.
    with tarefas.trava(config.pasta_dados() / "remoto", espera=espera):
        return perguntar(pedido, sessao=sessao) if sessao is not None else perguntar(pedido)


def executar(n: int, *, arq: Path | None = None, perguntar_fn=None) -> tarefas.Tarefa:
    """Mesmo molde da pesquisa: reivindica por CAS (preparando -> rodando) e só grava o fim se ainda está rodando."""
    t = tarefas.obter(n, arq)
    if t is None:
        raise KeyError(f"tarefa {n} não existe")
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A tarefa de {nome()} {n} já foi pega por outro trabalhador.")
    tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando")
    _SESSAO.valor = chave_sessao(n)
    try:
        try:
            resposta = (perguntar_fn or perguntar_com_trava)(t.pedido)
        except ErroConsulta as exc:
            return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou", resumo=str(exc)[:200], erro=str(exc)[:300])
        except (subprocess.TimeoutExpired, TimeoutError):
            # Conclusão remota desconhecida: a chamada não se repete; só a espera local terminou.
            return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou",
                                     resumo=f"{nome()} não respondeu; só a espera local terminou", erro="timeout")
    finally:
        _SESSAO.valor = None
    res = tarefas.arquivo_resultado(n)
    res.write_text(resposta, encoding="utf-8")
    return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou", resultado=str(res),
                             resumo=avisos.resumo_curto(resposta))
