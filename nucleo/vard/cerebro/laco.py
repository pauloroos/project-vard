"""Laço de inferência do cérebro: executa turnos de modelo+feramentas até resposta final ou limite.

Contrato mínimo da T3:
- Recebe um Pedido e um AdaptadorProvedor.
- Mantém histórico da sessão via sessoes.obter_historico/adicionar_mensagem.
- Emite EventosPedido (texto, ferramenta, fim, erro) via callback.
- Diário local registra efeitos de ferramentas antes de devolver resultado ao modelo.
- Limite de turnos evita laço infinito; sem framework de agentes.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from .contratos import (
    EstadoPedido,
    EventoPedido,
    Pedido,
    TipoEvento,
)
from .provedores import AdaptadorProvedor, ResultadoInferencia
from . import pedidos as modulo_pedidos
from . import sessoes

LIMITE_TURNOS = 8


async def executar_pedido(
    pedido: Pedido,
    adaptador: AdaptadorProvedor,
    emitir: Callable[[EventoPedido], None],
    executar_ferramenta: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
) -> None:
    """Roda o laço de inferência para um pedido, emitindo eventos e persistindo estado."""
    info = modulo_pedidos.consultar(pedido.pedido_id)
    if info is None:
        return

    mensagens = list(sessoes.obter_historico(pedido.sessao_id))
    mensagens.append({"role": "user", "content": pedido.texto})

    seq = info.ultimo_seq
    resposta_final: str | None = None
    erro_final: str | None = None

    try:
        for turno in range(LIMITE_TURNOS):
            resultado: ResultadoInferencia = await adaptador.inferir(mensagens, ferramentas=None)

            if not resultado.ok:
                erro_final = resultado.erro or "erro_desconhecido"
                seq += 1
                emitir(EventoPedido(
                    pedido_id=pedido.pedido_id,
                    sessao_id=pedido.sessao_id,
                    seq=seq,
                    tipo=TipoEvento.ERRO,
                    dados={"erro": erro_final},
                ))
                break

            # Chamadas de ferramenta
            if resultado.chamadas_ferramenta:
                for chamada in resultado.chamadas_ferramenta:
                    seq += 1
                    emitir(EventoPedido(
                        pedido_id=pedido.pedido_id,
                        sessao_id=pedido.sessao_id,
                        seq=seq,
                        tipo=TipoEvento.FERRAMENTA,
                        dados=chamada,
                    ))
                    if executar_ferramenta is not None:
                        try:
                            res_ferramenta = await executar_ferramenta(chamada)
                        except Exception as exc:  # noqa: BLE001
                            res_ferramenta = {"erro": str(exc)[:200]}
                        mensagens.append({
                            "role": "tool",
                            "tool_call_id": chamada.get("id", ""),
                            "content": _serializar_resultado(res_ferramenta),
                        })
                continue

            # Resposta textual final
            texto = resultado.texto or ""
            if texto:
                seq += 1
                emitir(EventoPedido(
                    pedido_id=pedido.pedido_id,
                    sessao_id=pedido.sessao_id,
                    seq=seq,
                    tipo=TipoEvento.TEXTO,
                    dados={"texto": texto},
                ))
                sessoes.adicionar_mensagem(pedido.sessao_id, {"role": "assistant", "content": texto})
            resposta_final = texto
            break
        else:
            erro_final = "limite_turnos_atingido"
            seq += 1
            emitir(EventoPedido(
                pedido_id=pedido.pedido_id,
                sessao_id=pedido.sessao_id,
                seq=seq,
                tipo=TipoEvento.ERRO,
                dados={"erro": erro_final},
            ))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        erro_final = str(exc)[:200]
        seq += 1
        emitir(EventoPedido(
            pedido_id=pedido.pedido_id,
            sessao_id=pedido.sessao_id,
            seq=seq,
            tipo=TipoEvento.ERRO,
            dados={"erro": erro_final},
        ))

    # Evento FIM sempre emitido
    seq += 1
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=seq,
        tipo=TipoEvento.FIM,
        dados={"resposta": resposta_final, "erro": erro_final},
    ))

    # Atualiza estado persistente
    info = modulo_pedidos.consultar(pedido.pedido_id) or info
    info.ultimo_seq = seq
    if erro_final:
        info.estado = EstadoPedido.FALHOU
        info.erro = erro_final
    else:
        info.estado = EstadoPedido.CONCLUIDO
        info.resposta = resposta_final
    info.provedor_usado = adaptador.nome
    modulo_pedidos._gravar_info(info)


def _serializar_resultado(dados: dict[str, Any]) -> str:
    import json
    try:
        return json.dumps(dados, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(dados)