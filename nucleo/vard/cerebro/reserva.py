"""Reserva durante o uso: tenta provedor reserva após falha real no ativo.
Contrato da T5:
- Falha de conexão, prazo, autenticação/cota ou 5xx aciona uma tentativa na reserva.
- Conserva resultados de ferramentas concluídas (diário); nunca repete ação incerta.
- Não altera o ativo salvo; escolha é por turno, não persistente.
- Um único consumidor por sessão; sem concorrência de motores locais.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable

from .contratos import EventoPedido, Pedido, TipoEvento
from .provedores import AdaptadorProvedor, ResultadoInferencia


async def inferir_com_reserva(
    pedido: Pedido,
    mensagens: list[dict[str, Any]],
    ferramentas: list[dict[str, Any]] | None,
    ativo: AdaptadorProvedor,
    reserva: AdaptadorProvedor | None,
    emitir: Callable[[EventoPedido], None],
    seq_inicial: int,
) -> tuple[ResultadoInferencia, int]:
    """Tenta inferir no ativo; se falhar e houver reserva, emite RESERVA e tenta reserva.
    Devolve (resultado, seq_atualizado). Falha na reserva mantém erro original do ativo."""
    resultado = await ativo.inferir(mensagens, ferramentas)
    seq = seq_inicial
    if resultado.ok or reserva is None:
        return resultado, seq
    # Falha real no ativo → tenta reserva
    seq += 1
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=seq,
        tipo=TipoEvento.RESERVA,
        dados={"ativo": ativo.nome, "reserva": reserva.nome, "erro_ativo": resultado.erro},
    ))
    resultado_reserva = await reserva.inferir(mensagens, ferramentas)
    if resultado_reserva.ok:
        return resultado_reserva, seq
    # Reserva também falhou: devolve erro do ativo (original)
    return resultado, seq