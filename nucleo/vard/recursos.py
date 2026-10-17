"""Monitor de recursos do Vard (0.9.4 leve): memória e CPU por componente.

Identifica processos pelos PIDs registrados (pids/) e pela árvore de processos,
nunca por nome solto. Devolve JSON com uso por componente e totais.
Componentes externos (OpenJarvis, LM Studio) aparecem separados como 'fora do Vard'.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from vard import config

log = logging.getLogger("vard.recursos")


@dataclass
class ComponenteRecursos:
    nome: str
    memoria_mb: float = 0.0
    cpu_percent: float = 0.0
    pids: list[int] = field(default_factory=list)
    detalhes: str = ""


def _ler_pids_registrados() -> dict[str, list[int]]:
    """Lê PIDs gravados na pasta de dados do Vard (pids/)."""
    pasta = config.pasta_dados() / "pids"
    resultado: dict[str, list[int]] = {}
    if not pasta.is_dir():
        return resultado
    for arq in pasta.glob("*.pid"):
        try:
            texto = arq.read_text(encoding="utf-8").strip()
            pid = int(texto.splitlines()[0])
            nome = arq.stem
            resultado.setdefault(nome, []).append(pid)
        except (ValueError, OSError):
            continue
    return resultado


def _processo_seguro(pid: int) -> psutil.Process | None:
    try:
        p = psutil.Process(pid)
        p.status()  # força NoSuchProcess se morreu
        return p
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def _memoria_mb(proc: psutil.Process) -> float:
    try:
        return proc.memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return 0.0


def _cpu_percent(proc: psutil.Process) -> float:
    try:
        return proc.cpu_percent(interval=0.05)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return 0.0


def _filhos_recursivos(pid: int) -> list[psutil.Process]:
    """Retorna todos os filhos recursivos de um PID."""
    filhos: list[psutil.Process] = []
    proc = _processo_seguro(pid)
    if proc is None:
        return filhos
    try:
        for filho in proc.children(recursive=True):
            filhos.append(filho)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    return filhos


def _coletar_componente(nome: str, pids: list[int], detalhes_extra: str = "") -> ComponenteRecursos:
    comp = ComponenteRecursos(nome=nome, detalhes=detalhes_extra)
    vistos: set[int] = set()
    for pid in pids:
        if pid in vistos:
            continue
        vistos.add(pid)
        proc = _processo_seguro(pid)
        if proc is None:
            continue
        comp.pids.append(pid)
        comp.memoria_mb += _memoria_mb(proc)
        comp.cpu_percent += _cpu_percent(proc)
        # Inclui filhos diretos do processo (ex.: WebView do widget)
        for filho in _filhos_recursivos(pid):
            if filho.pid not in vistos:
                vistos.add(filho.pid)
                comp.pids.append(filho.pid)
                comp.memoria_mb += _memoria_mb(filho)
                comp.cpu_percent += _cpu_percent(filho)
    return comp


def _detectar_xtts_carregado(voz_pids: list[int]) -> bool:
    """Verifica se o XTTS está carregado consultando /saude do serviço de voz."""
    if not voz_pids:
        return False
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:4710/saude", timeout=2, trust_env=False)
        if r.status_code == 200:
            dados = r.json()
            return bool(dados.get("xtts"))
    except Exception:  # noqa: BLE001
        pass
    return False


def _detectar_externos() -> list[ComponenteRecursos]:
    """Detecta OpenJarvis e LM Studio rodando fora do Vard."""
    externos: list[ComponenteRecursos] = []
    # OpenJarvis: porta 8000
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2, trust_env=False)
        if r.status_code < 400:
            externos.append(ComponenteRecursos(
                nome="OpenJarvis",
                detalhes="servidor externo ativo",
            ))
    except Exception:  # noqa: BLE001
        pass
    # LM Studio: porta 1234
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:1234/v1/models", timeout=2, trust_env=False)
        if r.status_code < 400:
            externos.append(ComponenteRecursos(
                nome="LM Studio",
                detalhes="servidor externo ativo",
            ))
    except Exception:  # noqa: BLE001
        pass
    return externos


def coletar_recursos() -> dict[str, Any]:
    """Coleta uso de recursos de todos os componentes do Vard."""
    pids_reg = _ler_pids_registrados()

    componentes: list[ComponenteRecursos] = []

    # Widget (vard.exe + WebView filhos)
    widget_pids = pids_reg.get("widget", []) or pids_reg.get("app", [])
    if not widget_pids:
        # Fallback: busca vard.exe por nome (só quando não há PID registrado)
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"] and "vard" in proc.info["name"].lower():
                        widget_pids.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:  # noqa: BLE001
            pass
    componentes.append(_coletar_componente("Widget", widget_pids))

    # Núcleo
    nucleo_pids = pids_reg.get("nucleo", []) or pids_reg.get("ponte", [])
    componentes.append(_coletar_componente("Núcleo", nucleo_pids))

    # MCPs
    mcp_pids = pids_reg.get("mcp", []) or pids_reg.get("mcps", [])
    componentes.append(_coletar_componente("MCPs", mcp_pids))

    # Voz
    voz_pids = pids_reg.get("voz", [])
    xtts_carregado = _detectar_xtts_carregado(voz_pids)
    voz_comp = _coletar_componente("Voz", voz_pids, f"XTTS {'carregado' if xtts_carregado else 'descarregado'}")
    componentes.append(voz_comp)

    # Reunião
    reuniao_pids = pids_reg.get("reuniao", [])
    componentes.append(_coletar_componente("Reunião", reuniao_pids))

    # Bandeja
    bandeja_pids = pids_reg.get("bandeja", [])
    componentes.append(_coletar_componente("Bandeja", bandeja_pids))

    # Externos (fora do Vard)
    externos = _detectar_externos()

    total_mem = sum(c.memoria_mb for c in componentes)
    total_cpu = sum(c.cpu_percent for c in componentes)

    return {
        "componentes": [
            {
                "nome": c.nome,
                "memoria_mb": round(c.memoria_mb, 1),
                "cpu_percent": round(c.cpu_percent, 1),
                "pids": c.pids[:10],  # limita lista para não inflar resposta
                "detalhes": c.detalhes,
            }
            for c in componentes
        ],
        "externos": [
            {"nome": e.nome, "detalhes": e.detalhes}
            for e in externos
        ],
        "total_memoria_mb": round(total_mem, 1),
        "total_cpu_percent": round(total_cpu, 1),
    }