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
from .provedores import AdaptadorProvedor, ErroProvedor, EventoInferencia, ResultadoInferencia


async def _consumir_stream(adaptador: AdaptadorProvedor, mensagens: list[dict[str, Any]], ferramentas: list[dict[str, Any]] | None) -> ResultadoInferencia:
    """Consome o stream do adaptador e devolve ResultadoInferencia consolidado.
    Detecta contrato antigo (retorno direto de ResultadoInferencia ou coroutine) e novo (async generator)."""
    import inspect
    resultado_chamada = adaptador.inferir(mensagens, ferramentas)
    # Contrato antigo: coroutine que retorna ResultadoInferencia
    if inspect.iscoroutine(resultado_chamada):
        resultado_chamada = await resultado_chamada
    if isinstance(resultado_chamada, ResultadoInferencia):
        return resultado_chamada
    # Contrato novo: async generator
    texto_partes: list[str] = []
    chamadas: list[dict[str, Any]] = []
    try:
        async for ev in resultado_chamada:
            if ev.tipo == "texto":
                conteudo = ev.dados.get("conteudo", "")
                if conteudo:
                    texto_partes.append(conteudo)
            elif ev.tipo == "chamada":
                chamadas.append(ev.dados)
            elif ev.tipo == "fim":
                break
        return ResultadoInferencia(
            texto="".join(texto_partes) if texto_partes else None,
            chamadas_ferramenta=chamadas,
            provedor=getattr(adaptador, "nome", "") or type(adaptador).__name__,
        )
    except ErroProvedor as ep:
        return ResultadoInferencia(provedor=getattr(adaptador, "nome", ""), erro=ep.codigo)
    except Exception as exc:  # noqa: BLE001
        return ResultadoInferencia(provedor=getattr(adaptador, "nome", ""), erro=str(exc)[:200])


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
    resultado = await _consumir_stream(ativo, mensagens, ferramentas)
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
        dados={"ativo": getattr(ativo, "nome", ""), "reserva": getattr(reserva, "nome", ""), "erro_ativo": resultado.erro},
    ))
    resultado_reserva = await _consumir_stream(reserva, mensagens, ferramentas)
    if resultado_reserva.ok:
        return resultado_reserva, seq
    # Reserva também falhou: devolve erro do ativo (original)
    return resultado, seq