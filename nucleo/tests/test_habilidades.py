"""Contrato compartilhado da Oficina e persistência real em pasta isolada."""
import json
from pathlib import Path

import pytest

from vard import habilidades

CASOS = json.loads((Path(__file__).resolve().parents[2] / "tests/fixtures/habilidades/contrato.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["nome"])
def test_contrato_compartilhado(caso):
    if caso["valido"]:
        habilidades.validar_habilidades(caso["valor"])
    else:
        with pytest.raises(ValueError):
            habilidades.validar_habilidades(caso["valor"])


def test_ausente_padrao_independente():
    cfg = habilidades.ler_habilidades()
    cfg["desligadas"].append("computador")
    assert habilidades.ler_habilidades() == habilidades.HABILIDADES_PADRAO


def test_grava_le_e_substitui_atomicamente(monkeypatch):
    cfg = next(c["valor"] for c in CASOS if c["nome"] == "treinada")
    habilidades.gravar_habilidades(cfg)
    assert habilidades.ler_habilidades()["habilidades"] == cfg["habilidades"]
    anterior = habilidades.caminho().read_bytes()
    def falhar(*_):
        raise OSError("troca indisponível")
    monkeypatch.setattr(habilidades.os, "replace", falhar)
    with pytest.raises(OSError):
        habilidades.gravar_habilidades(habilidades.HABILIDADES_PADRAO)
    assert habilidades.caminho().read_bytes() == anterior
    assert list(habilidades.caminho().parent.glob("habilidades.*.tmp")) == []


def test_invalido_preserva_arquivo():
    habilidades.gravar_habilidades(habilidades.HABILIDADES_PADRAO)
    antes = habilidades.caminho().read_bytes()
    with pytest.raises(ValueError):
        habilidades.gravar_habilidades({"versao": 2})
    assert habilidades.caminho().read_bytes() == antes
    habilidades.caminho().write_text("{quebrado", encoding="utf-8")
    with pytest.raises(ValueError):
        habilidades.ler_habilidades()
    assert habilidades.caminho().read_text(encoding="utf-8") == "{quebrado"
