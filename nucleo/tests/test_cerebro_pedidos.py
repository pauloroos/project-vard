"""Testes da T1 — sessões isoladas, FIFO, pedidos simultâneos e recuperação de interrupções.
Usa asyncio.Event para bloquear A, concluir B e verificar A ainda pendente, sem sleeps arbitrários.
Nenum HISTORICO global; tudo por sessão. Rodar falso injetável via configurar_executor.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from vard.cerebro import pedidos, sessoes
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido


@pytest.fixture(autouse=True)
def _isolar_dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cada teste usa pasta temporária de dados/config."""
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    pedidos.definir_pasta(dados / "cerebro" / "pedidos")
    pedidos.limpar_tudo()
    yield
    pedidos.limpar_tudo()


def _pedido(pid: str, sid: str, texto: str = "oi") -> Pedido:
    return Pedido(pedido_id=pid, sessao_id=sid, origem=Origem.PAINEL, texto=texto)


async def test_sessoes_nao_misturam_historico():
    """Históricos de sessões diferentes são independentes."""
    sessoes.adicionar_mensagem("s1", {"role": "user", "content": "a"})
    sessoes.adicionar_mensagem("s2", {"role": "user", "content": "b"})
    assert [m["content"] for m in sessoes.obter_historico("s1")] == ["a"]
    assert [m["content"] for m in sessoes.obter_historico("s2")] == ["b"]
    sessoes.limpar("s1")
    sessoes.limpar("s2")


async def test_mesma_sessao_fifo():
    """Dois pedidos na mesma sessão executam em ordem; segundo espera primeiro terminar."""
    ordem: list[str] = []
    trava_a = asyncio.Event()

    async def rodar(ped: Pedido, emitir):
        if ped.pedido_id == "p1":
            await trava_a.wait()
        ordem.append(ped.pedido_id)
        info = pedidos.consultar(ped.pedido_id)
        if info:
            info.estado = EstadoPedido.CONCLUIDO
            pedidos._gravar_info(info)

    pedidos.configurar_executor(rodar)
    pedidos.admitir(_pedido("p1", "s"))
    pedidos.admitir(_pedido("p2", "s"))

    tarefa = asyncio.create_task(pedidos.processar_fila("s"))
    await asyncio.sleep(0)  # cede para fila iniciar p1
    info1 = pedidos.consultar("p1")
    assert info1 and info1.estado == EstadoPedido.EXECUTANDO
    info2 = pedidos.consultar("p2")
    assert info2 and info2.estado == EstadoPedido.NA_FILA

    trava_a.set()
    await tarefa

    assert ordem == ["p1", "p2"]
    assert pedidos.consultar("p1").estado == EstadoPedido.CONCLUIDO
    assert pedidos.consultar("p2").estado == EstadoPedido.CONCLUIDO


async def test_outra_sessao_progride():
    """Sessões diferentes progridem em paralelo; bloqueio em A não impede B."""
    trava_a = asyncio.Event()
    concluido_b = asyncio.Event()

    async def rodar(ped: Pedido, emitir):
        if ped.pedido_id == "a1":
            await trava_a.wait()
        else:
            concluido_b.set()
        info = pedidos.consultar(ped.pedido_id)
        if info:
            info.estado = EstadoPedido.CONCLUIDO
            pedidos._gravar_info(info)

    pedidos.configurar_executor(rodar)
    pedidos.admitir(_pedido("a1", "sa"))
    pedidos.admitir(_pedido("b1", "sb"))

    ta = asyncio.create_task(pedidos.processar_fila("sa"))
    tb = asyncio.create_task(pedidos.processar_fila("sb"))

    await concluido_b.wait()
    assert pedidos.consultar("b1").estado == EstadoPedido.CONCLUIDO
    assert pedidos.consultar("a1").estado == EstadoPedido.EXECUTANDO

    trava_a.set()
    await ta
    await tb
    assert pedidos.consultar("a1").estado == EstadoPedido.CONCLUIDO


async def test_id_repetido_nao_executa_duas_vezes():
    """Mesmo pedido_id com mesmo corpo reutiliza; corpo diferente dá ValueError."""
    chamadas: list[str] = []

    async def rodar(ped: Pedido, emitir):
        chamadas.append(ped.pedido_id)
        info = pedidos.consultar(ped.pedido_id)
        if info:
            info.estado = EstadoPedido.CONCLUIDO
            pedidos._gravar_info(info)

    pedidos.configurar_executor(rodar)
    pedidos.admitir(_pedido("r1", "s", texto="x"))
    _, criado = pedidos.admitir(_pedido("r1", "s", texto="x"))
    assert not criado  # reutilizado

    with pytest.raises(ValueError):
        pedidos.admitir(_pedido("r1", "s", texto="y"))

    await pedidos.processar_fila("s")
    assert chamadas == ["r1"]


async def test_queda_nao_reinicia_pedido():
    """Recuperação no arranque marca EXECUTANDO como falho; executor não é chamado novamente."""
    async def rodar(ped: Pedido, emitir):
        raise AssertionError("nao deveria executar apos recuperacao")

    pedidos.configurar_executor(rodar)
    pedidos.admitir(_pedido("q1", "s"))
    info = pedidos.consultar("q1")
    assert info is not None
    info.estado = EstadoPedido.EXECUTANDO
    pedidos._gravar_info(info)

    n = pedidos.recuperar_interrupcoes()
    assert n == 1
    info2 = pedidos.consultar("q1")
    assert info2 and info2.estado == EstadoPedido.FALHOU
    assert info2.erro == "interrupcao_no_arranque"


async def test_cancelar_na_fila():
    """Cancelar pedido na fila atualiza estado e remove da fila; processar_fila ignora."""
    async def rodar(ped: Pedido, emitir):
        raise AssertionError("cancelado nao executa")

    pedidos.configurar_executor(rodar)
    pedidos.admitir(_pedido("c1", "s"))
    info = pedidos.cancelar("c1")
    assert info and info.estado == EstadoPedido.CANCELADO

    await pedidos.processar_fila("s")
    assert pedidos.consultar("c1").estado == EstadoPedido.CANCELADO