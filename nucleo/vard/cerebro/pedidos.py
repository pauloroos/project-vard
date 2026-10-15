"""Despachante de pedidos do cérebro: admissão, consulta, cancelamento e execução FIFO por sessão.
Persistência atômica em VARD_DADOS/cerebro/pedidos/. Pedidos interrompidos no arranque são marcados
como falhos/execução incerta; não há retomada automática. Um turno por sessão; sessões independentes.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Awaitable

from vard import config
from .contratos import (
    EstadoPedido,
    EstadoPedidoInfo,
    EventoPedido,
    Origem,
    Pedido,
    TipoEvento,
)
from . import sessoes

_pasta_pedidos = None  # sobrescrito em testes
_trava = threading.Lock()
_fila_por_sessao: dict[str, list[str]] = {}
_executores: dict[str, asyncio.Task] = {}
_corpo_por_id: dict[str, str] = {}
_rodar_fn: Callable[[Pedido, Callable[[EventoPedido], None]], Awaitable[None]] | None = None


def _base() -> Path:
    if _pasta_pedidos is not None:
        return Path(_pasta_pedidos)
    return config.pasta_dados() / "cerebro" / "pedidos"


def _arquivo(pedido_id: str) -> Path:
    if not pedido_id or "/" in pedido_id or "\\" in pedido_id:
        raise ValueError(f"pedido_id inválido: {pedido_id!r}")
    return _base() / f"{pedido_id}.json"


def _ler_info(pedido_id: str) -> EstadoPedidoInfo | None:
    arq = _arquivo(pedido_id)
    try:
        texto = arq.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        dados = json.loads(texto)
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    estado = dados.get("estado")
    try:
        est = EstadoPedido(estado)
    except ValueError:
        est = EstadoPedido.FALHOU
    return EstadoPedidoInfo(
        estado=est,
        pedido_id=dados.get("pedido_id", pedido_id),
        sessao_id=dados.get("sessao_id", ""),
        ultimo_seq=int(dados.get("ultimo_seq", 0)),
        resposta=dados.get("resposta"),
        erro=dados.get("erro"),
        provedor_usado=dados.get("provedor_usado"),
        tarefas=list(dados.get("tarefas", [])),
    )


def _gravar_info(info: EstadoPedidoInfo) -> None:
    arq = _arquivo(info.pedido_id)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    dados = {
        "estado": info.estado.value,
        "pedido_id": info.pedido_id,
        "sessao_id": info.sessao_id,
        "ultimo_seq": info.ultimo_seq,
        "resposta": info.resposta,
        "erro": info.erro,
        "provedor_usado": info.provedor_usado,
        "tarefas": info.tarefas,
    }
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, arq)


def configurar_executor(fn: Callable[[Pedido, Callable[[EventoPedido], None]], Awaitable[None]]) -> None:
    """Define a função que executa o laço do pedido."""
    global _rodar_fn
    _rodar_fn = fn


def definir_pasta(caminho: str | Path | None) -> None:
    """Sobrescreve a pasta de pedidos (usada em testes)."""
    global _pasta_pedidos
    _pasta_pedidos = caminho


def admitir(pedido: Pedido) -> tuple[EstadoPedidoInfo, bool]:
    """Admite um pedido. Devolve (info, criado). Se já existe com mesmo corpo, reutiliza; corpo diferente dá conflito."""
    with _trava:
        existente = _ler_info(pedido.pedido_id)
        if existente is not None:
            corpo_atual = _corpo_por_id.get(pedido.pedido_id)
            if corpo_atual == pedido.texto:
                return existente, False
            raise ValueError("conflito: mesmo pedido_id com corpo diferente")
        info = EstadoPedidoInfo(
            estado=EstadoPedido.NA_FILA,
            pedido_id=pedido.pedido_id,
            sessao_id=pedido.sessao_id,
        )
        _gravar_info(info)
        _corpo_por_id[pedido.pedido_id] = pedido.texto
        fila = _fila_por_sessao.setdefault(pedido.sessao_id, [])
        fila.append(pedido.pedido_id)
    return info, True


def consultar(pedido_id: str) -> EstadoPedidoInfo | None:
    return _ler_info(pedido_id)


def cancelar(pedido_id: str) -> EstadoPedidoInfo | None:
    """Cancela um pedido se ainda estiver na fila ou executando."""
    with _trava:
        info = _ler_info(pedido_id)
        if info is None:
            return None
        if info.estado in (EstadoPedido.CONCLUIDO, EstadoPedido.CANCELADO):
            return info
        info.estado = EstadoPedido.CANCELADO
        _gravar_info(info)
        fila = _fila_por_sessao.get(info.sessao_id, [])
        if pedido_id in fila:
            fila.remove(pedido_id)
    task = _executores.get(pedido_id)
    if task and not task.done():
        task.cancel()
    return info


async def processar_fila(sessao_id: str) -> None:
    """Processa pedidos da sessão em ordem FIFO, um por vez."""
    while True:
        with _trava:
            fila = _fila_por_sessao.get(sessao_id, [])
            if not fila:
                return
            proximo = fila[0]
            info = _ler_info(proximo)
            if info is None or info.estado != EstadoPedido.NA_FILA:
                fila.pop(0)
                continue
            info.estado = EstadoPedido.EXECUTANDO
            _gravar_info(info)
            fila.pop(0)

        if _rodar_fn is None:
            info.estado = EstadoPedido.FALHOU
            info.erro = "executor_nao_configurado"
            _gravar_info(info)
            continue

        evento_estado = EventoPedido(
            pedido_id=proximo,
            sessao_id=sessao_id,
            seq=info.ultimo_seq + 1,
            tipo=TipoEvento.ESTADO,
            dados={"estado": EstadoPedido.EXECUTANDO.value},
        )
        info.ultimo_seq += 1
        _gravar_info(info)

        try:
            await _rodar_fn(Pedido(pedido_id=proximo, sessao_id=sessao_id, origem=Origem.PAINEL, texto=""), lambda ev: None)
            info = _ler_info(proximo) or info
            if info.estado == EstadoPedido.EXECUTANDO:
                info.estado = EstadoPedido.CONCLUIDO
                _gravar_info(info)
        except asyncio.CancelledError:
            info = _ler_info(proximo) or info
            if info.estado not in (EstadoPedido.CANCELADO,):
                info.estado = EstadoPedido.CANCELADO
                _gravar_info(info)
        except Exception as exc:
            info = _ler_info(proximo) or info
            info.estado = EstadoPedido.FALHOU
            info.erro = str(exc)[:200]
            _gravar_info(info)


def recuperar_interrupcoes() -> int:
    """No arranque, marca pedidos EXECUTANDO como falhos (interrupção sem retomada)."""
    base = _base()
    if not base.exists():
        return 0
    count = 0
    for arq in base.glob("*.json"):
        try:
            texto = arq.read_text(encoding="utf-8")
            dados = json.loads(texto)
        except (OSError, ValueError):
            continue
        if not isinstance(dados, dict):
            continue
        if dados.get("estado") == EstadoPedido.EXECUTANDO.value:
            dados["estado"] = EstadoPedido.FALHOU.value
            dados["erro"] = "interrupcao_no_arranque"
            tmp = arq.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, arq)
            count += 1
    return count


def limpar_tudo() -> None:
    """Remove todos os arquivos de pedidos e filas (usado em testes)."""
    global _fila_por_sessao, _executores, _corpo_por_id
    _fila_por_sessao.clear()
    _executores.clear()
    _corpo_por_id.clear()
    base = _base()
    if base.exists():
        for arq in base.glob("*.json"):
            try:
                arq.unlink()
            except OSError:
                pass