"""Trabalhos demorados fora do processo do MCP: `python -m vard.trabalhador <n>`.

Processo, não thread: o MCP pode ser um processo curto (jarvis ask, preflight) e a thread morreria com
ele. stdout em arquivo: o stdout do MCP é o protocolo JSON-RPC; um filho que o herde corrompe a
conversa e pendura o OpenJarvis.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import psutil

from vard import config, tarefas
from vard.oficina import JaReivindicada
from vard.segredos import PASTA

REPO = Path(__file__).resolve().parent.parent
PASTA_LOGS = PASTA / "logs"
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
log = logging.getLogger("vard.trabalhador")


def _ambiente(arq: Path | None = None) -> dict[str, str]:
    """Ambiente do filho: as pastas de configuração e dados entram explícitas, mesmo que o pai não as tenha."""
    env = {**os.environ, "PYTHONUTF8": "1", "VARD_SEM_VIGIA": "1",
           "VARD_CONFIG": str(config.pasta_config().resolve()), "VARD_DADOS": str(config.pasta_dados().resolve())}
    if arq:
        env["VARD_TAREFAS_ARQUIVO"] = str(arq)       # o filho grava na mesma loja (provas e testes com arquivo à parte)
    return env


def _comecar(n: int, popen=subprocess.Popen) -> int:
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    with open(PASTA_LOGS / f"trabalhador-{n}.log", "ab") as saida:
        p = popen([sys.executable, "-m", "vard.trabalhador", str(n)], cwd=str(REPO), env=_ambiente(),
                  stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT,
                  creationflags=FLAGS, close_fds=True)
    return p.pid                      # o pid é gravado pelo próprio trabalhador (executar), sem corrida com o pai


def lancar(n: int, *, arq: Path | None = None, popen=subprocess.Popen) -> int:
    """Lança o trabalhador por um intermediário que sai logo (`--destacar`). Assim o trabalhador não é descendente
    do MCP: o `taskkill /T` que o vard-modo dá no OpenJarvis (jogo, recarregar) não o leva junto."""
    p = popen([sys.executable, "-m", "vard.trabalhador", "--destacar", str(n)], cwd=str(REPO), env=_ambiente(arq),
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              creationflags=FLAGS, close_fds=True)
    return p.pid


def _inicio_do_processo() -> float | None:
    try:
        return psutil.Process().create_time()
    except psutil.Error:
        return None


def executar(n: int, arq: Path | None = None) -> None:
    try:
        tarefas.atualizar(n, arq, pid=os.getpid(), pid_inicio=_inicio_do_processo())      # antes de reivindicar: nunca mexe na versão no meio da corrida
    except KeyError:
        log.warning("tarefa %s não existe", n)
        return
    t = tarefas.obter(n, arq)
    pode_falhar = "preparando"
    try:
        if t.ferramenta in tarefas.AGENTES:
            from vard import executor, oficina
            conf = oficina.carregar_conf()
            oficina.preparar(n, orca=executor.roteador(conf), repos=oficina.carregar_repos(), conf=conf, arq=arq)
        elif t.ferramenta == "pesquisa":
            from vard import pesquisa
            pode_falhar = "rodando"
            pesquisa.executar(n, arq=arq)
        elif t.ferramenta == "agente_remoto":
            from vard import remoto
            pode_falhar = "rodando"
            remoto.executar(n, arq=arq)
        elif t.ferramenta == "manha":
            from vard import manha
            pode_falhar = "rodando"
            manha.executar(n, arq=arq)
        elif t.ferramenta == "ata":
            from vard import reuniao
            pode_falhar = "rodando"
            reuniao.executar_ata(n, arq=arq)
        elif t.ferramenta == "delegada":
            from vard import delegada, oficina, orca_cli
            pode_falhar = "rodando"
            delegada.executar(n, arq=arq, orca=orca_cli.Orca(), repos=oficina.carregar_repos())
        else:
            raise ValueError(f"sem trabalhador para {t.ferramenta}")
    except JaReivindicada as exc:
        log.warning("tarefa %s: %s", n, exc)                # outro trabalhador é o dono: não derruba a tarefa dele
    except Exception as exc:  # noqa: BLE001 — o trabalhador nunca morre calado
        log.exception("tarefa %s falhou", n)
        # Só marca falhou se a tarefa ainda está no estado em que este trabalhador a deixou.
        tarefas.atualizar(n, arq, se_estado=pode_falhar, estado="falhou", erro=f"{type(exc).__name__}: {exc}"[:300],
                          resumo="deu erro no meio do caminho")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if sys.argv[1] == "--destacar":
        _comecar(int(sys.argv[2]))      # o intermediário morre ao sair; o trabalhador fica órfão de propósito
    else:
        executar(int(sys.argv[1]))
