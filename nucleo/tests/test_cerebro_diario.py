"""Testes da T4 — diário de efeitos: intenção, resultado confirmado, incerto e deduplicação.
Persistência atômica em VARD_DADOS/cerebro/diario/<pedido_id>.jsonl.
Leitura ignora linhas corrompidas. Repetição no mesmo turno reutiliza resultado confirmado;
incerto termina sem repetir.
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


async def test_registrar_intencao_e_resultado():
    """Registrar intenção + resultado confirmado; obter_resultado devolve o valor."""
    chave = diario.registrar_intencao("p1", "salvar", {"ok": True})
    diario.registrar_resultado("p1", chave, {"status": "ok"})
    assert diario.obter_resultado("p1", chave) == {"status": "ok"}
    assert not diario.tem_incerto("p1", chave)


async def test_multiplos_resultados_ultimo_vence():
    """Múltiplos resultados para mesma chave: último confirmado vence."""
    chave = diario._chave_canonica("eco", {"texto": "x"})
    diario.registrar_intencao("p2", "eco", {"texto": "x"})
    diario.registrar_resultado("p2", chave, "primeiro")
    diario.registrar_resultado("p2", chave, "segundo")
    assert diario.obter_resultado("p2", chave) == "segundo"


async def test_linha_corrompida_eh_ignorada():
    """Leitura ignora linha não-JSON sem quebrar; entradas válidas retornam."""
    arq = diario._arquivo_diario("p3")
    arq.parent.mkdir(parents=True, exist_ok=True)
    chave = diario._chave_canonica("acao", {})
    arq.write_text(
        f'{{"tipo":"intencao","chave":"{chave}","nome":"acao"}}\n'
        f'linha-ruim\n'
        f'{{"tipo":"resultado","chave":"{chave}","resultado":"ok"}}\n',
        encoding="utf-8",
    )
    assert diario.obter_resultado("p3", chave) == "ok"


async def test_diarios_de_pedidos_diferentes_sao_isolados():
    """Efeitos de pedidos diferentes ficam em arquivos separados."""
    chave_a = diario.registrar_intencao("pa", "x", {"v": 1})
    chave_b = diario.registrar_intencao("pb", "x", {"v": 2})
    diario.registrar_resultado("pa", chave_a, "res-a")
    diario.registrar_resultado("pb", chave_b, "res-b")
    assert diario.obter_resultado("pa", chave_a) == "res-a"
    assert diario.obter_resultado("pb", chave_b) == "res-b"
    assert diario.obter_resultado("pa", chave_b) is None


async def test_limpar_diario_remove_arquivo():
    """limpar_diario apaga o arquivo do pedido; listar volta vazio."""
    chave = diario.registrar_intencao("pc", "y", {})
    diario.registrar_resultado("pc", chave, 9)
    assert diario.listar_efeitos("pc")
    diario.limpar_diario("pc")
    assert diario.listar_efeitos("pc") == []


async def test_pedido_sem_diario_retorna_vazio():
    """Listar efeitos de pedido inexistente devolve lista vazia."""
    assert diario.listar_efeitos("inexistente") == []
    assert diario.obter_resultado("inexistente", "qualquer") is None


async def test_marcar_incerto():
    """marcar_incerto grava entrada incerto; tem_incerto retorna True."""
    chave = diario.registrar_intencao("pd", "falha", {})
    diario.marcar_incerto("pd", chave)
    assert diario.tem_incerto("pd", chave)
    assert not diario.tem_resultado("pd", chave)


async def test_chave_canonica_deduplica():
    """Mesma ferramenta com mesmos argumentos gera mesma chave canônica."""
    c1 = diario._chave_canonica("eco", {"texto": "oi"})
    c2 = diario._chave_canonica("eco", {"texto": "oi"})
    c3 = diario._chave_canonica("eco", {"texto": "outro"})
    assert c1 == c2
    assert c1 != c3