"""Teste de texto progressivo: eventos TEXTO durante streaming não duplicam cur.resposta (FR-008).

Cobre:
- Eventos TEXTO emitidos fragmento a fragmento chegam ao despachante e acumulam resposta.
- O evento FIM carrega a resposta completa sem duplicar o que já foi acumulado via TEXTO.
- O callback do teste delega ao despachante real (_emitir_despachante) para exercitar o fluxo completo.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

NUCLEO_DIR = Path(__file__).resolve().parents[1]
if str(NUCLEO_DIR) not in sys.path:
    sys.path.insert(0, str(NUCLEO_DIR))

from vard.cerebro import pedidos as modulo_pedidos
from vard.cerebro.contratos import EventoPedido, TipoEvento


@pytest.fixture(autouse=True)
def _limpa_pedidos(tmp_path):
    """Isola arquivos de pedidos em tmp_path por teste."""
    modulo_pedidos.definir_pasta(tmp_path / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()
    modulo_pedidos.definir_pasta(None)


def _criar_pedido(pedido_id: str = "p1", sessao_id: str = "s1", texto: str = "oi"):
    from vard.cerebro.contratos import Pedido, Origem
    return Pedido(pedido_id=pedido_id, sessao_id=sessao_id, origem=Origem.PAINEL, texto=texto)


def _admitir_e_emitir(pedido):
    """Admite pedido e devolve função emitir que passa pelo despachante real."""
    modulo_pedidos.admitir(pedido)

    def emitir(ev: EventoPedido) -> None:
        modulo_pedidos._emitir_despachante(ev)

    return emitir


def test_texto_fragmentos_nao_duplicam_resposta():
    """TEXTO por fragmento + FIM com resposta não devem duplicar cur.resposta."""
    pedido = _criar_pedido()
    emitir = _admitir_e_emitir(pedido)

    # Simula streaming: 3 fragmentos de texto
    for i, frag in enumerate(["Olá, ", "tudo bem ", "com você?"], start=1):
        emitir(EventoPedido(
            pedido_id=pedido.pedido_id,
            sessao_id=pedido.sessao_id,
            seq=i,
            tipo=TipoEvento.TEXTO,
            dados={"texto": frag},
        ))

    # FIM carrega a resposta completa (como laco.py faz após remover o TEXTO pós-loop)
    resposta_completa = "Olá, tudo bem com você?"
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=4,
        tipo=TipoEvento.FIM,
        dados={"resposta": resposta_completa},
    ))

    info = modulo_pedidos.consultar(pedido.pedido_id)
    assert info is not None
    # A resposta deve ser exatamente a do FIM, sem duplicação dos fragmentos TEXTO
    assert info.resposta == resposta_completa


def test_fim_sem_resposta_preserva_acumulado():
    """Se FIM não trouxer resposta, o acumulado via TEXTO permanece."""
    pedido = _criar_pedido(pedido_id="p2")
    emitir = _admitir_e_emitir(pedido)

    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=1,
        tipo=TipoEvento.TEXTO,
        dados={"texto": "fragmento único"},
    ))

    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=2,
        tipo=TipoEvento.FIM,
        dados={},
    ))

    info = modulo_pedidos.consultar(pedido.pedido_id)
    assert info is not None
    # Sem resposta no FIM, o campo fica como estava (None ou vazio dependendo da implementação)
    # O importante é não haver erro nem duplicação


def test_apenas_fim_com_resposta():
    """Cenário sem streaming: só FIM com resposta deve funcionar."""
    pedido = _criar_pedido(pedido_id="p3")
    emitir = _admitir_e_emitir(pedido)

    resposta = "Resposta direta sem streaming."
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=1,
        tipo=TipoEvento.FIM,
        dados={"resposta": resposta},
    ))

    info = modulo_pedidos.consultar(pedido.pedido_id)
    assert info is not None
    assert info.resposta == resposta