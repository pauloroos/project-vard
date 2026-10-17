"""Recomendação leve do primeiro uso (0.9.4 rodada 2): escolhe a opção mais leve
que funciona na máquina detectada e explica o motivo em português."""
from __future__ import annotations

import pytest

from vard.primeiro_uso.deteccao import (
    Gpu,
    Item,
    RecomendacaoLeve,
    ResultadoDeteccao,
    recomendar_configuracao_leve,
)


def _resultado(*, gpu_backend: str = "", vram_mb: int = 0, lm_studio_acessivel: bool = False) -> ResultadoDeteccao:
    gpu_estado = "encontrado" if gpu_backend else "nao_encontrado"
    itens: list[Item] = []
    if lm_studio_acessivel:
        itens.append(Item("lmstudio", "LM Studio", "encontrado", "0.3.10", "servidor acessível", ""))
    return ResultadoDeteccao(
        itens=tuple(itens),
        gpu=Gpu(estado=gpu_estado, backend=gpu_backend, vram_mb=vram_mb, detalhe=""),
        duracao_ms=0,
    )


def test_sem_gpu_recomenda_kokoro_e_openjarvis():
    r = recomendar_configuracao_leve(_resultado())
    assert isinstance(r, RecomendacaoLeve)
    assert r.voz == "kokoro"
    assert r.cerebro == "openjarvis"
    assert "CPU" in r.motivo or "leve" in r.motivo.lower()


def test_gpu_pouca_vram_recomenda_kokoro():
    r = recomendar_configuracao_leve(_resultado(gpu_backend="nvidia", vram_mb=2048))
    assert r.voz == "kokoro"
    assert "VRAM" in r.motivo or "pouca" in r.motivo.lower()


def test_gpu_com_vram_suficiente_recomenda_xtts():
    r = recomendar_configuracao_leve(_resultado(gpu_backend="nvidia", vram_mb=6000))
    assert r.voz == "xtts"
    assert "XTTS" in r.motivo or "natural" in r.motivo.lower()


def test_lm_studio_acessivel_recomenda_cerebro_local():
    r = recomendar_configuracao_leve(_resultado(lm_studio_acessivel=True))
    assert r.cerebro == "lmstudio"
    assert "local" in r.motivo.lower() or "internet" in r.motivo.lower()