"""Laço de inferência do cérebro: modelo → ferramenta → resposta com diário e slot local.

Contrato mínimo da T4:
- Recebe Pedido, AdaptadorProvedor e GerenciadorFerramentas.
- Mantém histórico da sessão via sessoes.obter_historico/adicionar_mensagem.
- Emite EventosPedido (texto, ferramenta, fim, erro) via callback.
- Diário registra intenção antes do efeito e resultado após confirmação.
- Repetição no mesmo turno reutiliza resultado confirmado; incerto termina sem repetir.
- Slot de inferência por motor local liberado antes de executar ferramenta.
- Operações síncronas vão para thread sem bloquear o event loop.
- Limite de 8 turnos evita laço infinito; sem framework de agentes.
- Erro de ferramenta volta ao modelo como erro, nunca como sucesso.
- Não fala raciocínio nem JSON de ferramenta.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Awaitable

from .contratos import (
    EstadoPedido,
    EventoPedido,
    Pedido,
    TipoEvento,
)
from .provedores import AdaptadorProvedor, ErroProvedor, ResultadoInferencia
from . import diario
from . import pedidos as modulo_pedidos
from . import sessoes

log = logging.getLogger(__name__)

LIMITE_TURNOS = 8


async def executar_pedido(
    pedido: Pedido,
    adaptador: AdaptadorProvedor,
    emitir: Callable[[EventoPedido], None],
    gerenciador_ferramentas: Any | None = None,
    slot_local: asyncio.Semaphore | None = None,
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
            # --- Verifica incertos pendentes ANTES de chamar o adaptador ---
            efeitos = diario.listar_efeitos(pedido.pedido_id)
            for efeito in efeitos:
                if efeito.get("tipo") == "incerto":
                    chave_inc = efeito.get("chave", "")
                    nome_inc = chave_inc.split(":")[0] if ":" in chave_inc else chave_inc
                    log.warning("Diário: efeito incerto pendente para %s; terminando sem repetir", nome_inc)
                    erro_final = f"efeito_incerto_{nome_inc}"
                    seq += 1
                    emitir(EventoPedido(
                        pedido_id=pedido.pedido_id,
                        sessao_id=pedido.sessao_id,
                        seq=seq,
                        tipo=TipoEvento.ERRO,
                        dados={"erro": erro_final},
                    ))
                    break
            if erro_final:
                break

            # --- Slot local: adquirido apenas durante inferência, liberado antes de ferramenta ---
            if slot_local is not None:
                await slot_local.acquire()
            try:
                texto_acumulado: list[str] = []
                chamadas_coletadas: list[dict[str, Any]] = []
                erro_stream: str | None = None

                try:
                    resultado_chamada = adaptador.inferir(mensagens, ferramentas=None)
                    # Contrato antigo: coroutine que retorna ResultadoInferencia
                    if inspect.iscoroutine(resultado_chamada):
                        resultado_chamada = await resultado_chamada
                    if isinstance(resultado_chamada, ResultadoInferencia):
                        if not resultado_chamada.ok:
                            erro_stream = resultado_chamada.erro or "erro_desconhecido"
                        else:
                            if resultado_chamada.texto:
                                texto_acumulado.append(resultado_chamada.texto)
                            chamadas_coletadas.extend(resultado_chamada.chamadas_ferramenta)
                    else:
                        # Contrato novo: async generator
                        async for ev in resultado_chamada:
                            if ev.tipo == "texto":
                                conteudo = ev.dados.get("conteudo", "")
                                if conteudo:
                                    texto_acumulado.append(conteudo)
                            elif ev.tipo == "chamada":
                                chamadas_coletadas.append(ev.dados)
                            elif ev.tipo == "fim":
                                break
                except ErroProvedor as ep:
                    erro_stream = ep.codigo
                except Exception as exc:  # noqa: BLE001
                    erro_stream = str(exc)[:200]
            finally:
                # Liberar slot ANTES de executar ferramenta
                if slot_local is not None:
                    slot_local.release()

            if erro_stream:
                erro_final = erro_stream
                seq += 1
                emitir(EventoPedido(
                    pedido_id=pedido.pedido_id,
                    sessao_id=pedido.sessao_id,
                    seq=seq,
                    tipo=TipoEvento.ERRO,
                    dados={"erro": erro_final},
                ))
                break

            # --- Chamadas de ferramenta com diário ---
            if chamadas_coletadas:
                for chamada in chamadas_coletadas:
                    nome = chamada.get("nome") or chamada.get("name", "")
                    argumentos = chamada.get("argumentos") or chamada.get("arguments", {})
                    chave = diario._chave_canonica(nome, argumentos)

                    # Verifica se já tem resultado confirmado no diário (reutiliza)
                    resultado_existente = diario.obter_resultado(pedido.pedido_id, chave)
                    if resultado_existente is not None:
                        log.debug("Diário: reutilizando resultado confirmado para %s", nome)
                        mensagens.append({
                            "role": "tool",
                            "tool_call_id": chamada.get("id", ""),
                            "content": _serializar_resultado(resultado_existente),
                        })
                        continue

                    # Verifica se há efeito incerto (termina sem repetir)
                    if diario.tem_incerto(pedido.pedido_id, chave):
                        log.warning("Diário: efeito incerto para %s; terminando sem repetir", nome)
                        erro_final = f"efeito_incerto_{nome}"
                        seq += 1
                        emitir(EventoPedido(
                            pedido_id=pedido.pedido_id,
                            sessao_id=pedido.sessao_id,
                            seq=seq,
                            tipo=TipoEvento.ERRO,
                            dados={"erro": erro_final},
                        ))
                        break

                    # Registra intenção ANTES do efeito
                    diario.registrar_intencao(pedido.pedido_id, nome, argumentos)

                    seq += 1
                    emitir(EventoPedido(
                        pedido_id=pedido.pedido_id,
                        sessao_id=pedido.sessao_id,
                        seq=seq,
                        tipo=TipoEvento.FERRAMENTA,
                        dados=chamada,
                    ))

                    # Executa ferramenta
                    res_ferramenta: dict[str, Any] | None = None
                    try:
                        if gerenciador_ferramentas is not None:
                            identificador = chamada.get("identificador", "interno")
                            texto_resultado = await gerenciador_ferramentas.chamar(
                                identificador, nome, argumentos
                            )
                            res_ferramenta = {"resultado": texto_resultado}
                        else:
                            res_ferramenta = {"erro": "gerenciador_ferramentas_nao_configurado"}
                    except Exception as exc:  # noqa: BLE001
                        res_ferramenta = {"erro": str(exc)[:200]}

                    # Registra resultado ou marca incerto
                    if res_ferramenta and "erro" not in res_ferramenta:
                        diario.registrar_resultado(pedido.pedido_id, chave, res_ferramenta)
                    else:
                        # Efeito pode ter ocorrido mas resultado não foi gravado → incerto
                        diario.marcar_incerto(pedido.pedido_id, chave)

                    mensagens.append({
                        "role": "tool",
                        "tool_call_id": chamada.get("id", ""),
                        "content": _serializar_resultado(res_ferramenta),
                    })

                if erro_final:
                    break
                continue

            # --- Resposta textual final ---
            texto = "".join(texto_acumulado)
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
    info.provedor_usado = getattr(adaptador, 'nome', '') or type(adaptador).__name__
    modulo_pedidos._gravar_info(info)


def _serializar_resultado(dados: dict[str, Any] | None) -> str:
    if dados is None:
        return "{}"
    try:
        return json.dumps(dados, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(dados)