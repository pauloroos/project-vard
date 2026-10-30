"""Teste de texto progressivo: eventos TEXTO durante streaming e acumulação em pedidos (FR-008).

Cobre:
- laco.py emite TEXTO events durante o loop de streaming do provedor.
- pedidos._emitir_despachante acumula resposta via TEXTO antes do FIM.
- pedidos.consultar() reflete texto acumulado ANTES do evento FIM chegar.
- O evento FIM carrega a resposta completa sem duplicar o que já foi acumulado via TEXTO.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import MagicMock

import pytest

NUCLEO_DIR = Path(__file__).resolve().parents[1]
if str(NUCLEO_DIR) not in sys.path:
    sys.path.insert(0, str(NUCLEO_DIR))

from vard.cerebro import pedidos as modulo_pedidos
from vard.cerebro.contratos import EventoPedido, Pedido, Origem, TipoEvento
from vard.cerebro.laco import executar_pedido


@pytest.fixture(autouse=True)
def _limpa_pedidos(tmp_path):
    """Isola arquivos de pedidos em tmp_path por teste."""
    modulo_pedidos.definir_pasta(tmp_path / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()
    modulo_pedidos.definir_pasta(None)


def _criar_pedido(pedido_id: str = "p1", sessao_id: str = "s1", texto: str = "oi"):
    return Pedido(pedido_id=pedido_id, sessao_id=sessao_id, origem=Origem.PAINEL, texto=texto)


def _admitir_e_emitir(pedido):
    """Admite pedido e devolve função emitir que passa pelo despachante real."""
    modulo_pedidos.admitir(pedido)

    def emitir(ev: EventoPedido) -> None:
        modulo_pedidos._emitir_despachante(ev)

    return emitir


# --- Helpers para testes assíncronos sem pytest-asyncio ---

class _EventoStream:
    """Evento simples simulando o contrato async generator do provedor."""
    def __init__(self, tipo: str, dados: dict[str, Any]):
        self.tipo = tipo
        self.dados = dados


async def _provedor_streaming_fragmentos(*_args, **_kwargs) -> AsyncIterator[_EventoStream]:
    """Provedor falso que yields fragmentos de texto como streaming."""
    for frag in ["Olá, ", "tudo bem ", "com você?"]:
        yield _EventoStream("texto", {"conteudo": frag})
    yield _EventoStream("fim", {})


def test_laco_emite_texto_durante_streaming():
    """laco.py deve emitir eventos TEXTO durante o loop async for do provedor."""
    pedido = _criar_pedido()
    modulo_pedidos.admitir(pedido)

    eventos_emitidos: list[EventoPedido] = []

    def capturar(ev: EventoPedido) -> None:
        eventos_emitidos.append(ev)
        modulo_pedidos._emitir_despachante(ev)

    adaptador = MagicMock()
    adaptador.inferir = _provedor_streaming_fragmentos
    adaptador.nome = "teste"

    asyncio.run(executar_pedido(pedido, adaptador, capturar))

    # Deve haver eventos TEXTO emitidos durante o streaming
    textos = [ev for ev in eventos_emitidos if ev.tipo == TipoEvento.TEXTO]
    assert len(textos) == 3, f"Esperava 3 eventos TEXTO, recebeu {len(textos)}"
    assert textos[0].dados["texto"] == "Olá, "
    assert textos[1].dados["texto"] == "tudo bem "
    assert textos[2].dados["texto"] == "com você?"

    # FIM deve carregar a resposta completa
    fins = [ev for ev in eventos_emitidos if ev.tipo == TipoEvento.FIM]
    assert len(fins) == 1
    assert fins[0].dados["resposta"] == "Olá, tudo bem com você?"


def test_consultar_reflete_texto_acumulado_antes_do_fim():
    """pedidos.consultar() deve refletir texto acumulado via TEXTO antes do FIM chegar."""
    pedido = _criar_pedido(pedido_id="p_consulta")
    emitir = _admitir_e_emitir(pedido)

    # Emite 2 fragmentos TEXTO (simulando streaming em andamento)
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=1,
        tipo=TipoEvento.TEXTO,
        dados={"texto": "Parte um. "},
    ))
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=2,
        tipo=TipoEvento.TEXTO,
        dados={"texto": "Parte dois."},
    ))

    # Consulta ANTES do FIM: deve ter o texto acumulado
    info = modulo_pedidos.consultar(pedido.pedido_id)
    assert info is not None
    assert info.resposta == "Parte um. Parte dois."

    # Agora emite FIM com resposta completa (deve substituir, não duplicar)
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=3,
        tipo=TipoEvento.FIM,
        dados={"resposta": "Parte um. Parte dois."},
    ))

    info_final = modulo_pedidos.consultar(pedido.pedido_id)
    assert info_final is not None
    assert info_final.resposta == "Parte um. Parte dois."


# --- Testes originais preservados (regressão) ---

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

    # FIM carrega a resposta completa (substitui o acumulado, não duplica)
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
    # Sem resposta no FIM, o acumulado via TEXTO permanece
    assert info.resposta == "fragmento único"


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