"""Vigia da oficina: uma thread que olha as tarefas a cada 30 s e avisa cada mudança que merece fala.

Só um processo vigia: trava de SO em vigia.lock (o Windows solta sozinho se o processo morrer).
Processos curtos (preflight, trabalhadores, prova) passam VARD_SEM_VIGIA=1 e nem tentam.
Nada aqui imprime: o stdout do processo da oficina é o protocolo MCP. Log em logs\\vigia.log.
"""
from __future__ import annotations

import datetime as dt
import logging
import msvcrt
import os
import threading
from pathlib import Path
from typing import Callable

import psutil

from vard import avisos, config, delegada, executor, manha, oficina, tarefas
from vard.orca_cli import ErroOrca
TRAVA: Path | None = None
LOG: Path | None = None
INTERVALO_S = 30
log = logging.getLogger("vard.vigia")


def adquirir_trava(caminho: Path | None = None) -> int | None:
    alvo = Path(caminho or TRAVA or config.pasta_dados() / "vigia.lock")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(alvo, os.O_RDWR | os.O_CREAT)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        return None
    return fd      # fica aberto enquanto o processo viver


PREPARANDO_SEM_PID_MIN = 5      # "preparando" sem trabalhador há mais que isso: o lançamento falhou


def trabalhador_vivo(t: tarefas.Tarefa, agora: dt.datetime | None = None) -> bool:
    """O processo do trabalhador ainda é o mesmo? O Windows reaproveita o pid (reboot, por exemplo): confere o
    create_time gravado junto. Sem pid: vivo só até PREPARANDO_SEM_PID_MIN minutos depois de criada."""
    if not t.pid:
        if t.estado != "preparando":
            return True
        agora = agora or dt.datetime.now().astimezone()
        return (agora - tarefas.hora(t.atualizada_em or t.criada_em)).total_seconds() < PREPARANDO_SEM_PID_MIN * 60
    try:
        p = psutil.Process(t.pid)
        return t.pid_inicio is None or abs(p.create_time() - t.pid_inicio) < 2
    except psutil.NoSuchProcess:
        return False
    except psutil.Error:
        return True                     # sem permissão para olhar: não declaro morto


TENTATIVAS_MAX = 3
_tentativas: dict[tuple[int, str], int] = {}


def _trabalhador_sumiu(t: tarefas.Tarefa, arq: Path | None) -> tarefas.Tarefa:
    """Processo morto e tarefa ainda viva: relê antes (ele pode ter terminado e gravado antes de sair) e grava
    só se nada mudou desde a releitura (comparar-e-trocar por estado e versão)."""
    atual = tarefas.obter(t.n, arq)
    if atual and atual.estado in ("preparando", "rodando"):
        return tarefas.atualizar(t.n, arq, se_estado=atual.estado, se_versao=atual.versao, estado="falhou",
                                 resumo="o trabalho foi interrompido", erro="o processo do trabalhador sumiu")
    return atual or t


def _entregar(t: tarefas.Tarefa, avisar: Callable[[tarefas.Tarefa], object]) -> bool:
    """True = pode marcar avisado. Aviso que não chegou a lugar nenhum (avisar devolve False) repete na próxima
    volta, até TENTATIVAS_MAX; depois registra e marca, para não virar tempestade."""
    chave = (t.n, t.estado)
    try:
        entregue = avisar(t) is not False
    except Exception:  # noqa: BLE001 — um aviso ruim não repete nem derruba a volta
        log.exception("aviso da tarefa %s falhou", t.n)
        entregue = True
    if entregue:
        _tentativas.pop(chave, None)
        return True
    _tentativas[chave] = _tentativas.get(chave, 0) + 1
    if _tentativas[chave] >= TENTATIVAS_MAX:
        log.warning("aviso da tarefa %s (%s) não chegou em %s tentativas: desisti", t.n, t.estado, TENTATIVAS_MAX)
        _tentativas.pop(chave, None)
        return True
    log.warning("aviso da tarefa %s (%s) não chegou; tento de novo na próxima volta", t.n, t.estado)
    return False


def passo(*, orca, conf: dict, arq: Path | None = None, agora: dt.datetime | None = None,
          avisar: Callable[[tarefas.Tarefa], object] = avisos.avisar) -> list[tarefas.Tarefa]:
    """Uma volta: atualiza o que está vivo e avisa uma vez cada estado avisável novo."""
    avisadas = []
    try:
        delegada.limpar_antigas(arq=arq, agora=agora or dt.datetime.now().astimezone())
    except Exception:  # noqa: BLE001 — a limpeza nunca derruba a volta
        log.warning("limpeza das respostas antigas falhou", exc_info=True)
    for t in tarefas.listar(arq):
        try:
            if t.ferramenta in tarefas.AGENTES and t.terminal and t.estado in ("rodando", "esperando", "travou"):
                t = oficina.atualizar_estado(t, orca=orca, conf=conf, arq=arq, agora=agora)
            elif t.ferramenta == "delegada" and t.estado == "esperando" and t.terminal:
                t = delegada.observar_login(t, orca=orca, arq=arq)
            elif t.estado in ("preparando", "rodando") and not trabalhador_vivo(t, agora):
                t = _trabalhador_sumiu(t, arq)
        except ErroOrca as exc:
            log.warning("tarefa %s: o Orca respondeu %s", t.n, exc.codigo)
            continue
        except Exception as exc:  # noqa: BLE001 — uma tarefa ruim não para as outras
            log.warning("tarefa %s: o acompanhamento falhou (%s)", t.n, type(exc).__name__)
            continue
        if t.estado == "rodando" and t.avisado:
            t = tarefas.atualizar(t.n, arq, se_estado="rodando", avisado="")   # voltou a andar: avisa de novo depois
        if t.estado in tarefas.AVISAVEIS and t.avisado != t.estado:
            if _entregar(t, avisar):
                tarefas.atualizar(t.n, arq, se_estado=t.estado, avisado=t.estado)   # estado mudou no meio: não grava
                avisadas.append(t)
    return avisadas


def _configurar_log() -> None:
    alvo = LOG or config.pasta_dados() / "logs" / "vigia.log"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(alvo, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    raiz = logging.getLogger("vard")
    raiz.addHandler(h)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False


PARAR = threading.Event()


def parar() -> None:
    """Pede à thread da vigia que saia (shutdown do MCP); ela solta a trava ao sair."""
    PARAR.set()


def _laco(orca, conf: dict, fd: int | None) -> None:
    try:
        while not PARAR.is_set():
            if fd is None:                      # outro processo vigia: tenta assumir se ele morrer
                fd = adquirir_trava()
                if fd is not None:
                    log.info("vigia assumiu a trava (pid %s)", os.getpid())
            if fd is not None:
                try:
                    passo(orca=orca, conf=conf)
                except Exception:  # noqa: BLE001 — uma volta ruim não derruba a vigia
                    log.exception("volta da vigia falhou")
                try:
                    manha.agendar_se_preciso()      # 8h de segunda a sexta (config/manha.toml); só quem tem a trava
                except Exception:  # noqa: BLE001
                    log.exception("agenda da manhã falhou")
                try:
                    from vard import reuniao       # serviço opcional, disponível a partir da etapa de reuniões
                    reuniao.manutencao_diaria()     # áudio vencido e retenção das reuniões, uma vez por dia
                except ImportError:
                    pass
                except Exception:  # noqa: BLE001
                    log.exception("manutenção das reuniões falhou")
            PARAR.wait(INTERVALO_S)
    finally:
        if fd is not None:
            os.close(fd)


def iniciar(*, orca=None, conf: dict | None = None) -> threading.Thread | None:
    if os.environ.get("VARD_SEM_VIGIA") == "1":
        return None
    PARAR.clear()
    fd = adquirir_trava()
    _configurar_log()
    conf = conf or oficina.carregar_conf()
    th = threading.Thread(target=_laco, args=(orca or executor.roteador(conf), conf, fd),
                          name="vard-vigia", daemon=True)
    th.start()
    log.info("vigia %s (pid %s)", "no ar" if fd is not None else "à espera da trava", os.getpid())
    return th
