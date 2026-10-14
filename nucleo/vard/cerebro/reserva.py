"""Reserva durante o uso: tenta provedor reserva após falha real no ativo (T5).

Contrato da T5:
- Falha de conexão, prazo, autenticação/cota ou 5xx aciona uma tentativa na reserva.
- Conserva resultados de ferramentas concluídas (diário); nunca repete ação incerta.
- Não altera o ativo salvo; escolha é por turno, não persistente.
- Snapshot por turno: mensagens + chamadas + diário antes de cada inferência.
- Códigos recuperáveis: conexao|prazo|credencial|cota|servidor.
- Uma troca por turno; com texto entregue ou ferramenta incerta encerra sem retomar.
- Schema/capacidade/cancelamento NÃO acionam reserva.
- Coordenação global de motores locais via ControleMotorLocal (injetável).
- Se descarga falha, não carrega; não toca em processos/modelos externos.
- Reserva de API não exige segunda carga local.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

from .contratos import EventoPedido, Pedido, TipoEvento
from .provedores import AdaptadorProvedor, ErroProvedor, ResultadoInferencia
from . import diario

log = logging.getLogger(__name__)

CODIGOS_RECUPERAVEIS = frozenset({"conexao", "prazo", "credencial", "cota", "servidor"})
CODIGOS_NAO_RECUPERAVEIS = frozenset({"schema_invalido", "contexto_excedido", "capacidade"})


def _eh_recuperavel(erro: str | None) -> bool:
    """Verifica se o código de erro é recuperável (aciona reserva).
    Usa match exato nos códigos conhecidos; fallback genérico só se nenhum
    código não-recuperável estiver presente na string."""
    if not erro:
        return False
    erro_lower = erro.lower().strip()
    # Match exato nos códigos não-recuperáveis primeiro
    for codigo in CODIGOS_NAO_RECUPERAVEIS:
        if erro_lower == codigo or erro_lower.startswith(codigo + ":") or erro_lower.startswith(codigo + "_"):
            return False
    # Match exato nos códigos recuperáveis
    for codigo in CODIGOS_RECUPERAVEIS:
        if erro_lower == codigo or erro_lower.startswith(codigo + ":") or erro_lower.startswith(codigo + "_"):
            return True
    # Fallback genérico: só se NÃO contiver nenhum termo não-recuperável
    for codigo in CODIGOS_NAO_RECUPERAVEIS:
        if codigo in erro_lower:
            return False
    return any(kw in erro_lower for kw in ("connection", "timeout", "503", "502", "500", "429", "401", "403"))


async def _consumir_stream(
    adaptador: AdaptadorProvedor,
    mensagens: list[dict[str, Any]],
    ferramentas: list[dict[str, Any]] | None,
) -> ResultadoInferencia:
    """Consome o stream do adaptador e devolve ResultadoInferencia consolidado.
    Captura ErroProvedor tanto na chamada inicial quanto durante iteração."""
    try:
        resultado_chamada = adaptador.inferir(mensagens, ferramentas)
        if inspect.iscoroutine(resultado_chamada):
            resultado_chamada = await resultado_chamada
        if isinstance(resultado_chamada, ResultadoInferencia):
            return resultado_chamada
        # Contrato novo: async generator
        texto_partes: list[str] = []
        chamadas: list[dict[str, Any]] = []
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
        return ResultadoInferencia(
            provedor=getattr(adaptador, "nome", ""),
            erro=ep.codigo,
        )
    except Exception as exc:  # noqa: BLE001
        return ResultadoInferencia(
            provedor=getattr(adaptador, "nome", ""),
            erro=str(exc)[:200],
        )


async def _trocar_motor_local(
    controle: Any,
    modelo_reserva: str,
    cronologia: list[str],
) -> bool:
    """Coordena troca de motor local usando método atômico se disponível.
    Retorna True se troca foi bem-sucedida. Se descarga falhar, não carrega."""
    if controle is None:
        return True  # API-only, sem motor local para trocar

    # Usa método atômico se disponível (lock de escopo amplo impede intercalação)
    if hasattr(controle, "trocar_modelo"):
        ok = await controle.trocar_modelo(modelo_reserva)
        cronologia.extend(controle.cronologia)
        return ok

    # Fallback: sequência manual (sem proteção contra concorrência entre sessões)
    await controle.bloquear_inferencias()
    cronologia.append("bloqueado")

    await controle.esperar_ativas(timeout_s=30.0)
    cronologia.append("esperar_ativas_ok")

    ok_descarga = await controle.descarregar()
    if not ok_descarga:
        cronologia.append("descarga_falhou")
        await controle.desbloquear_inferencias()
        return False
    cronologia.append("descarga_confirmada")

    ok_carga = await controle.carregar(modelo_reserva)
    if not ok_carga:
        cronologia.append("carga_falhou")
        await controle.desbloquear_inferencias()
        return False
    cronologia.append(f"carga:{modelo_reserva}")

    ok_pronto = await controle.confirmar_prontidao()
    cronologia.append("prontidao_ok" if ok_pronto else "prontidao_falhou")

    await controle.desbloquear_inferencias()
    cronologia.append("desbloqueado")
    return ok_pronto


async def inferir_com_reserva(
    pedido: Pedido,
    mensagens: list[dict[str, Any]],
    ferramentas: list[dict[str, Any]] | None,
    ativo: AdaptadorProvedor,
    reserva: AdaptadorProvedor | None,
    emitir: Callable[[EventoPedido], None],
    seq_inicial: int,
    controle_motor: Any | None = None,
    modelo_reserva: str | None = None,
) -> tuple[ResultadoInferencia, int]:
    """Tenta inferir no ativo; se falhar com código recuperável e houver reserva,
    emite RESERVA e tenta reserva. Devolve (resultado, seq_atualizado).

    Regras T5:
    - Só aciona reserva para erros recuperáveis (conexao/prazo/credencial/cota/servidor).
    - Schema/capacidade/cancelamento NÃO acionam reserva.
    - Se já houve texto entregue ou ferramenta incerta, encerra sem retomar.
    - Uma troca por turno.
    - Coordenação de motor local se controle_motor for fornecido.
    - Ativo salvo não muda; escolha é por turno.
    """
    seq = seq_inicial
    texto_ja_entregue = False

    # Verifica estado prévio: texto parcial em mensagens históricas impede reserva
    for msg in mensagens:
        if msg.get("role") == "assistant" and msg.get("content"):
            texto_ja_entregue = True
            break

    # Verifica ferramenta incerta no diário ANTES de tentar inferência
    efeitos = diario.listar_efeitos(pedido.pedido_id)
    for efeito in efeitos:
        if efeito.get("tipo") == "incerto":
            log.warning("Reserva: ferramenta incerta pendente no diário; encerrando sem retomar")
            return ResultadoInferencia(
                provedor=getattr(ativo, "nome", ""),
                erro=f"efeito_incerto_{efeito.get('chave', '')}",
            ), seq

    resultado = await _consumir_stream(ativo, mensagens, ferramentas)

    if resultado.ok:
        return resultado, seq

    # Detecta texto parcial entregue via streaming nesta chamada
    if resultado.texto:
        texto_ja_entregue = True

    # Verifica se erro é recuperável
    if not _eh_recuperavel(resultado.erro):
        log.info("Reserva: erro '%s' não é recuperável; não aciona reserva", resultado.erro)
        return resultado, seq

    if reserva is None:
        log.info("Reserva: erro recuperável mas sem provedor reserva configurado")
        return resultado, seq

    if texto_ja_entregue:
        log.warning("Reserva: texto já entregue ao usuário; encerrando sem retomar")
        return resultado, seq

    # Emite evento RESERVA
    seq += 1
    emitir(EventoPedido(
        pedido_id=pedido.pedido_id,
        sessao_id=pedido.sessao_id,
        seq=seq,
        tipo=TipoEvento.RESERVA,
        dados={
            "ativo": getattr(ativo, "nome", ""),
            "reserva": getattr(reserva, "nome", ""),
            "erro_ativo": resultado.erro,
        },
    ))

    # Coordenação de motor local se necessário
    cronologia: list[str] = []
    if controle_motor is not None and modelo_reserva is not None:
        ok_troca = await _trocar_motor_local(controle_motor, modelo_reserva, cronologia)
        if not ok_troca:
            log.error("Reserva: troca de motor local falhou; cronologia=%s", cronologia)
            return resultado, seq

    # Tenta reserva
    resultado_reserva = await _consumir_stream(reserva, mensagens, ferramentas)
    if resultado_reserva.ok:
        return resultado_reserva, seq

    # Reserva também falhou: devolve erro do ativo (original)
    return resultado, seq