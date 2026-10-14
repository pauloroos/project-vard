"""Agente remoto opcional por SSH; pedidos seguem exclusivamente por stdin."""
from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from vard import avisos, config, segredos, tarefas
from vard.consulta import ErroConsulta
from vard.oficina import JaReivindicada

NOME_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
LISTAR = "sudo docker ps --format '{{.Names}}'"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT_S = 180


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
                "nome": "o agente remoto", "container_prefixo": "", **conf}
        if not str(conf.get("destino", "")).strip():
            raise ErroConsulta("O agente remoto não está configurado.")
        if not str(conf.get("comando", "")).strip():
            raise ErroConsulta("O comando do agente remoto não está configurado.")
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


def perguntar(pedido: str, *, executar=None) -> str:
    conf = carregar_conf()
    executar = executar or subprocess.run
    quem = conf["nome"] or "o agente remoto"
    comum = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
    comando = conf["comando"]
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
    resposta = p.stdout.strip()
    if not resposta:
        raise ErroConsulta(f"{quem.capitalize()} respondeu vazio.")
    return resposta


def perguntar_com_trava(pedido: str, espera: float = TIMEOUT_S * 3) -> str:
    carregar_conf()  # Sem configuração, nem cria a trava.
    with tarefas.trava(config.pasta_dados() / "remoto", espera=espera):
        return perguntar(pedido)


def executar(n: int, *, arq: Path | None = None, perguntar_fn=None) -> tarefas.Tarefa:
    """Mesmo molde da pesquisa: reivindica por CAS (preparando -> rodando) e só grava o fim se ainda está rodando."""
    t = tarefas.obter(n, arq)
    if t is None:
        raise KeyError(f"tarefa {n} não existe")
    if not tarefas.reivindicar(n, arq, se_estado="preparando", se_versao=t.versao):
        raise JaReivindicada(f"A tarefa de {nome()} {n} já foi pega por outro trabalhador.")
    tarefas.atualizar(n, arq, se_estado="preparando", estado="rodando")
    try:
        resposta = (perguntar_fn or perguntar_com_trava)(t.pedido)
    except ErroConsulta as exc:
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou", resumo=str(exc)[:200], erro=str(exc)[:300])
    except (subprocess.TimeoutExpired, TimeoutError):
        return tarefas.atualizar(n, arq, se_estado="rodando", estado="falhou",
                                 resumo=f"{nome()} não respondeu a tempo", erro="timeout")
    res = tarefas.arquivo_resultado(n)
    res.write_text(resposta, encoding="utf-8")
    return tarefas.atualizar(n, arq, se_estado="rodando", estado="terminou", resultado=str(res),
                             resumo=avisos.resumo_curto(resposta))
