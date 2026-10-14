"""Testes da T2 — adaptadores de provedores, fábrica e contratos de inferência.
Adaptador falso para provas sem rede; fábrica rejeita nome desconhecido.
ResultadoInferencia distingue sucesso de falha por campo `erro`.
"""
from __future__ import annotations

import pytest

from vard.cerebro.provedores import (
    AdaptadorFalso,
    ResultadoInferencia,
    listar_provedores,
    obter,
    registrar,
)


async def test_adaptador_falso_retorna_texto():
    """Adaptador falso devolve resposta fixa sem erro."""
    adp = AdaptadorFalso(resposta="olá")
    res = await adp.inferir([{"role": "user", "content": "oi"}])
    assert res.ok
    assert res.texto == "olá"
    assert res.provedor == "falso"
    assert res.chamadas_ferramenta == []


async def test_adaptador_falso_pode_falhar():
    """Adaptador falso com falhar=True devolve erro e ok=False."""
    adp = AdaptadorFalso(falhar=True)
    res = await adp.inferir([])
    assert not res.ok
    assert res.erro == "falha_simulada"
    assert res.texto is None


def test_fabrica_obtem_registrado():
    """obter() instancia adaptador registrado pelo nome."""
    adp = obter("falso", resposta="x")
    assert isinstance(adp, AdaptadorFalso)


def test_fabrica_rejeita_desconhecido():
    """obter() com nome não registrado levanta ValueError."""
    with pytest.raises(ValueError, match="desconhecido"):
        obter("inexistente")


def test_listar_provedores_inclui_falso():
    """listar_provedores devolve pelo menos o adaptador falso padrão."""
    nomes = listar_provedores()
    assert "falso" in nomes


def test_registrar_novo_adaptador():
    """registrar() adiciona novo adaptador e obter() passa a funcionar."""

    class AdpTmp(AdaptadorFalso):
        nome = "tmp"

    registrar("tmp", AdpTmp)
    try:
        adp = obter("tmp")
        assert isinstance(adp, AdpTmp)
    finally:
        # limpa registro temporário
        from vard.cerebro.provedores import _REGISTRO

        _REGISTRO.pop("tmp", None)


def test_resultado_inferencia_congelado():
    """ResultadoInferencia é frozen; campos não são mutáveis."""
    res = ResultadoInferencia(texto="a", provedor="falso")
    with pytest.raises(AttributeError):
        res.texto = "b"  # type: ignore[misc]