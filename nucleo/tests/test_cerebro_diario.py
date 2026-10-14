"""Testes da T4 — diário de efeitos: persistência atômica, leitura tolerante e isolamento por pedido.
Cada efeito é um dict; linhas corrompidas são ignoradas na leitura. Arquivos ficam em
VARD_DADOS/cerebro/diario/<pedido_id>.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vard.cerebro import diario


@pytest.fixture(autouse=True)
def _isolar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    yield


async def test_registrar_e_listar_efeito():
    """Registrar efeito grava linha JSON legível; listar devolve o dict."""
    diario.registrar_efeito("p1", {"acao": "salvar", "ok": True})
    efeitos = diario.listar_efeitos("p1")
    assert efeitos == [{"acao": "salvar", "ok": True}]


async def test_multiplos_efeitos_mantem_ordem():
    """Vários efeitos são gravados em ordem e lidos na mesma ordem."""
    diario.registrar_efeito("p2", {"n": 1})
    diario.registrar_efeito("p2", {"n": 2})
    diario.registrar_efeito("p2", {"n": 3})
    efeitos = diario.listar_efeitos("p2")
    assert [e["n"] for e in efeitos] == [1, 2, 3]


async def test_linha_corrompida_eh_ignorada():
    """Leitura ignora linha não-JSON sem quebrar; efeitos válidos retornam."""
    arq = diario._arquivo_diario("p3")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text('{"n":1}\nlinha-ruim\n{"n":2}\n', encoding="utf-8")
    efeitos = diario.listar_efeitos("p3")
    assert [e["n"] for e in efeitos] == [1, 2]


async def test_diarios_de_pedidos_diferentes_sao_isolados():
    """Efeitos de pedidos diferentes ficam em arquivos separados."""
    diario.registrar_efeito("pa", {"x": 1})
    diario.registrar_efeito("pb", {"x": 2})
    assert diario.listar_efeitos("pa") == [{"x": 1}]
    assert diario.listar_efeitos("pb") == [{"x": 2}]


async def test_limpar_diario_remove_arquivo():
    """limpar_diario apaga o arquivo do pedido; listar volta vazio."""
    diario.registrar_efeito("pc", {"y": 9})
    assert diario.listar_efeitos("pc")
    diario.limpar_diario("pc")
    assert diario.listar_efeitos("pc") == []


async def test_pedido_sem_diario_retorna_vazio():
    """Listar efeitos de pedido inexistente devolve lista vazia."""
    assert diario.listar_efeitos("inexistente") == []


async def test_efeito_nao_dict_levanta_typeerror():
    """Registrar algo que não é dict levanta TypeError."""
    with pytest.raises(TypeError):
        diario.registrar_efeito("pd", "nao-dict")  # type: ignore[arg-type]