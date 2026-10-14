"""Testes da T5 — reserva durante o uso: troca de provedor após falha real no ativo.
Cobre: ativo ok (sem reserva), ativo falha e reserva ok, ambos falham (erro do ativo preservado),
evento RESERVA emitido apenas quando há troca, e conservação de efeitos já registrados.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from vard.cerebro import diario, pedidos as modulo_pedidos
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard.cerebro.provedores import AdaptadorFalso, AdaptadorProvedor, ResultadoInferencia
from vard.cerebro.reserva import inferir_com_reserva


@pytest.fixture(autouse=True)
def _isolar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    modulo_pedidos.definir_pasta(dados / "cerebro" / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()


def _pedido(pid: str = "p1", sid: str = "s1") -> Pedido:
    return Pedido(pedido_id=pid, sessao_id=sid, origem=Origem.PAINEL, texto="oi")


async def test_ativo_ok_nao_usa_reserva():
    """Ativo com sucesso não aciona reserva nem emite evento RESERVA."""
    eventos: list[Any] = []
    ativo = AdaptadorFalso(resposta="certo")
    reserva = AdaptadorFalso(resposta="reserva")
    ped = _pedido()
    res, seq = await inferir_com_reserva(
        ped, [{"role": "user", "content": "oi"}], None,
        ativo, reserva, lambda ev: eventos.append(ev), seq_inicial=0,
    )
    assert res.ok
    assert res.texto == "certo"
    assert res.provedor == "falso"
    assert not any(e.tipo == TipoEvento.RESERVA for e in eventos)


async def test_ativo_falha_e_reserva_ok():
    """Falha no ativo aciona reserva; evento RESERVA emitido e resultado vem da reserva."""
    eventos: list[Any] = []
    ativo = AdaptadorFalso(falhar=True)
    reserva = AdaptadorFalso(resposta="salvo")
    ped = _pedido()
    res, seq = await inferir_com_reserva(
        ped, [], None, ativo, reserva, lambda ev: eventos.append(ev), seq_inicial=0,
    )
    assert res.ok
    assert res.texto == "salvo"
    reserva_ev = next((e for e in eventos if e.tipo == TipoEvento.RESERVA), None)
    assert reserva_ev is not None
    assert reserva_ev.dados["ativo"] == "falso"
    assert reserva_ev.dados["reserva"] == "falso"
    assert reserva_ev.dados.get("erro_ativo") == "falha_simulada"
    assert seq >= 1


async def test_ambos_falham_mantem_erro_do_ativo():
    """Se reserva também falha, devolve erro original do ativo (não o da reserva)."""
    eventos: list[Any] = []
    ativo = AdaptadorFalso(falhar=True)
    # Reserva com erro diferente
    class AdpReservaFalha(AdaptadorProvedor):
        nome = "reserva-falha"
        async def inferir(self, mensagens, ferramentas=None):
            return ResultadoInferencia(provedor=self.nome, erro="erro-reserva")

    ped = _pedido()
    res, seq = await inferir_com_reserva(
        ped, [], None, ativo, AdpReservaFalha(), lambda ev: eventos.append(ev), seq_inicial=0,
    )
    assert not res.ok
    assert res.erro == "falha_simulada"  # erro do ativo, não da reserva
    assert any(e.tipo == TipoEvento.RESERVA for e in eventos)


async def test_sem_reserva_nao_emite_evento():
    """Sem reserva configurada, falha no ativo não emite RESERVA."""
    eventos: list[Any] = []
    ativo = AdaptadorFalso(falhar=True)
    ped = _pedido()
    res, seq = await inferir_com_reserva(
        ped, [], None, ativo, None, lambda ev: eventos.append(ev), seq_inicial=0,
    )
    assert not res.ok
    assert not any(e.tipo == TipoEvento.RESERVA for e in eventos)
    assert seq == 0


async def test_diario_conservado_na_troca():
    """Efeitos registrados antes da falha permanecem no diário após troca para reserva."""
    chave = diario.registrar_intencao("p1", "acao", {"ok": True})
    diario.registrar_resultado("p1", chave, {"status": "antes"})
    eventos: list[Any] = []
    ativo = AdaptadorFalso(falhar=True)
    reserva = AdaptadorFalso(resposta="depois")
    ped = _pedido()
    res, _ = await inferir_com_reserva(
        ped, [], None, ativo, reserva, lambda ev: eventos.append(ev), seq_inicial=0,
    )
    assert res.ok
    # Resultado confirmado permanece no diário após troca
    assert diario.obter_resultado("p1", chave) == {"status": "antes"}
    diario.limpar_diario("p1")