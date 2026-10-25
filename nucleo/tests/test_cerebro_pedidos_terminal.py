"""Testes de garantia de evento terminal do despachante (FR-001).

Garante que todo pedido do cérebro próprio emite evento terminal (erro e/ou fim)
em todos os caminhos:
- executor não configurado
- exceção antes do laço
- cancelamento durante a execução
- cancelamento enquanto aguarda na fila
- conclusão normal sem emissão explícita de fim
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vard.cerebro import pedidos
from vard.cerebro.contratos import (
    EstadoPedido,
    EventoPedido,
    Origem,
    Pedido,
    TipoEvento,
)


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


async def test_executor_nao_configurado_emite_terminal():
    """Quando o executor não está configurado, o pedido falha e emite evento terminal."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)
    pedidos.configurar_executor(None)

    pedidos.admitir(_pedido("p-sem-exec", "s-term"))
    tarefa = pedidos._lacos_ativos.get("s-term")
    if tarefa:
        await tarefa

    info = pedidos.consultar("p-sem-exec")
    assert info is not None
    assert info.estado == EstadoPedido.FALHOU
    assert info.erro == "executor_nao_configurado"

    terminais = [
        e for e in eventos
        if e.pedido_id == "p-sem-exec" and e.tipo in (TipoEvento.ERRO, TipoEvento.FIM)
    ]
    assert len(terminais) >= 1, "esperava evento terminal para executor não configurado"


async def test_excecao_antes_do_laco_emite_terminal():
    """Exceção levantada pelo executor emite evento terminal e marca falha."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)

    async def _executor_com_erro(ped: Pedido, emitir):
        raise RuntimeError("falha na inicializacao do provedor")

    pedidos.configurar_executor(_executor_com_erro)
    pedidos.admitir(_pedido("p-erro-cedo", "s-term"))
    tarefa = pedidos._lacos_ativos.get("s-term")
    if tarefa:
        await tarefa

    info = pedidos.consultar("p-erro-cedo")
    assert info is not None
    assert info.estado == EstadoPedido.FALHOU
    assert "falha na inicializacao" in (info.erro or "")

    terminais = [
        e for e in eventos
        if e.pedido_id == "p-erro-cedo" and e.tipo in (TipoEvento.ERRO, TipoEvento.FIM)
    ]
    assert len(terminais) >= 1, "esperava evento terminal para exceção antes do laço"


async def test_cancelamento_durante_execucao_emite_terminal():
    """Cancelamento de pedido em execução emite evento terminal."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)
    iniciou = asyncio.Event()
    bloqueio = asyncio.Event()

    async def _executor_lento(ped: Pedido, emitir):
        iniciou.set()
        await bloqueio.wait()

    pedidos.configurar_executor(_executor_lento)
    pedidos.admitir(_pedido("p-cancel-exec", "s-term"))

    await iniciou.wait()
    info_exec = pedidos.consultar("p-cancel-exec")
    assert info_exec and info_exec.estado == EstadoPedido.EXECUTANDO

    pedidos.cancelar("p-cancel-exec")
    tarefa = pedidos._lacos_ativos.get("s-term")
    if tarefa:
        await tarefa

    info = pedidos.consultar("p-cancel-exec")
    assert info is not None
    assert info.estado == EstadoPedido.CANCELADO

    terminais = [
        e for e in eventos
        if e.pedido_id == "p-cancel-exec" and e.tipo in (TipoEvento.ERRO, TipoEvento.FIM)
    ]
    assert len(terminais) >= 1, "esperava evento terminal para cancelamento em execução"


async def test_cancelamento_na_fila_emite_terminal():
    """Cancelamento de pedido ainda na fila emite evento terminal."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)
    iniciou = asyncio.Event()
    bloqueio = asyncio.Event()

    async def _executor_bloqueia_primeiro(ped: Pedido, emitir):
        if ped.pedido_id == "p-fila-1":
            iniciou.set()
            await bloqueio.wait()

    pedidos.configurar_executor(_executor_bloqueia_primeiro)
    pedidos.admitir(_pedido("p-fila-1", "s-fila"))
    pedidos.admitir(_pedido("p-fila-2", "s-fila"))

    await iniciou.wait()
    info_f2 = pedidos.consultar("p-fila-2")
    assert info_f2 and info_f2.estado == EstadoPedido.NA_FILA

    pedidos.cancelar("p-fila-2")
    info_cancelado = pedidos.consultar("p-fila-2")
    assert info_cancelado and info_cancelado.estado == EstadoPedido.CANCELADO

    terminais = [
        e for e in eventos
        if e.pedido_id == "p-fila-2" and e.tipo in (TipoEvento.ERRO, TipoEvento.FIM)
    ]
    assert len(terminais) >= 1, "esperava evento terminal para cancelamento na fila"

    bloqueio.set()
    tarefa = pedidos._lacos_ativos.get("s-fila")
    if tarefa:
        await tarefa


async def test_execucao_sem_fim_explicito_garante_terminal():
    """Executor que não emite fim explicitamente tem evento fim garantido pelo despachante."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)

    async def _executor_mudo(ped: Pedido, emitir):
        info = pedidos.consultar(ped.pedido_id)
        if info:
            info.resposta = "ok sem emitir"
            pedidos._gravar_info(info)

    pedidos.configurar_executor(_executor_mudo)
    pedidos.admitir(_pedido("p-sem-fim", "s-term"))
    tarefa = pedidos._lacos_ativos.get("s-term")
    if tarefa:
        await tarefa

    info = pedidos.consultar("p-sem-fim")
    assert info is not None
    assert info.estado == EstadoPedido.CONCLUIDO

    fins = [
        e for e in eventos
        if e.pedido_id == "p-sem-fim" and e.tipo == TipoEvento.FIM
    ]
    assert len(fins) == 1, "esperava exatamente um evento fim garantido pelo despachante"


async def test_execucao_com_fim_nao_duplica_terminal():
    """Quando o executor já emite fim, o despachante não emite fim duplicado."""
    eventos: list[EventoPedido] = []
    pedidos.configurar_emissor(eventos.append)

    async def _executor_correto(ped: Pedido, emitir):
        emitir(EventoPedido(
            pedido_id=ped.pedido_id,
            sessao_id=ped.sessao_id,
            seq=1,
            tipo=TipoEvento.FIM,
            dados={"resposta": "tudo certo", "erro": None},
        ))

    pedidos.configurar_executor(_executor_correto)
    pedidos.admitir(_pedido("p-correto", "s-term"))
    tarefa = pedidos._lacos_ativos.get("s-term")
    if tarefa:
        await tarefa

    fins = [
        e for e in eventos
        if e.pedido_id == "p-correto" and e.tipo == TipoEvento.FIM
    ]
    assert len(fins) == 1, "não deve duplicar evento fim quando já emitido"
