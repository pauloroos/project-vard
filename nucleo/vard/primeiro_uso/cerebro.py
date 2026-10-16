"""Teste de cérebro para o assistente de primeiro uso (T3).

Envia 'Responda apenas: pronto' ao provedor escolhido via adaptador existente,
com timeout total de 30 s, sem ferramentas nem histórico. Registra primeiro token
e resultado; falha permite tentar de novo ou deixar pendente. Não escolhe outro
modelo, não baixa LLM, não altera configuração ativa.
"""
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary
from typing import Any

from vard.cerebro import provedores as mod_provedores

log = logging.getLogger(__name__)

TEXTO_TESTE = "Responda apenas: pronto"
TIMEOUT_TOTAL_S = 30.0
_travas = WeakKeyDictionary()


def validar_endpoint(base_url: str) -> None:
    url = urlsplit(base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("endpoint_invalido")


@asynccontextmanager
async def _exclusivo(base_url):
    travas = _travas.setdefault(asyncio.get_running_loop(), {})
    trava = travas.setdefault(base_url.rstrip("/"), asyncio.Lock())
    async with trava:
        yield


async def listar_modelos(tipo: str, base_url: str, chave: str = ""):
    validar_endpoint(base_url)
    if tipo != "lmstudio":
        raise ValueError("listagem_requer_lmstudio")
    return await mod_provedores.ClienteLMStudio(base_url, chave).listar()


async def trocar_modelo(base_url: str, modelo: str, chave: str = ""):
    try:
        validar_endpoint(base_url)
        async with asyncio.timeout(TIMEOUT_TOTAL_S), _exclusivo(base_url):
            instancia = await mod_provedores.ClienteLMStudio(base_url, chave).trocar(modelo)
        return {"ok": True, "detalhe": "modelo_carregado", "instancia": instancia}
    except mod_provedores.ErroProvedor as exc:
        return {"ok": False, "detalhe": exc.codigo}
    except (ValueError, TimeoutError):
        return {"ok": False, "detalhe": "troca_interrompida"}



def _montar_adaptador(
    tipo: str,
    base_url: str,
    modelo: str,
    chave: str = "",
) -> mod_provedores.AdaptadorProvedor:
    """Cria adaptador concreto pelo tipo informado; tipos desconhecidos levantam ValueError."""
    if tipo in ("openai_compat", "lmstudio", "local"):
        return mod_provedores.AdaptadorOpenAICompat(base_url=base_url, modelo=modelo, chave=chave, timeout=TIMEOUT_TOTAL_S)
    if tipo == "anthropic":
        return mod_provedores.AdaptadorAnthropic(chave=chave, modelo=modelo, base_url=base_url, timeout=TIMEOUT_TOTAL_S)
    if tipo == "google":
        return mod_provedores.AdaptadorGoogle(chave=chave, modelo=modelo, base_url=base_url, timeout=TIMEOUT_TOTAL_S)
    if tipo == "openai_nativo":
        return mod_provedores.AdaptadorOpenAINativo(chave=chave, modelo=modelo, base_url=base_url, timeout=TIMEOUT_TOTAL_S)
    raise ValueError(f"tipo_de_provedor_desconhecido: {tipo}")


async def _testar_cerebro(
    tipo: str,
    base_url: str,
    modelo: str,
    chave: str = "",
) -> dict[str, Any]:
    """Executa teste curto contra o provedor indicado.

    Devolve {"ok": bool, "detalhe": str, "primeiro_token_ms": int|None}.
    - ok=True: recebeu pelo menos um evento de texto ou fim dentro do prazo.
    - ok=False: detalhe descreve o erro (timeout, conexão, auth, etc.).
    Nunca altera estado global, nunca troca modelo, nunca usa ferramentas.
    """
    if not base_url or not base_url.strip():
        return {"ok": False, "detalhe": "base_url_vazia", "primeiro_token_ms": None}
    if not modelo or not modelo.strip():
        return {"ok": False, "detalhe": "modelo_vazio", "primeiro_token_ms": None}

    try:
        validar_endpoint(base_url)
        if tipo in ("anthropic", "google", "openai_nativo") and not chave:
            return {"ok": False, "detalhe": "credencial_ausente", "primeiro_token_ms": None}
        if tipo == "lmstudio":
            modelos = await listar_modelos(tipo, base_url, chave)
            alvo = next((m for m in modelos if m["id"] == modelo), None)
            if not alvo:
                return {"ok": False, "detalhe": "modelo_inexistente", "primeiro_token_ms": None}
            if len(alvo["instancias"]) != 1 or sum(len(m["instancias"]) for m in modelos) != 1:
                return {"ok": False, "detalhe": "modelo_nao_carregado", "primeiro_token_ms": None}
            modelo = alvo["instancias"][0]["id"]
        adaptador = _montar_adaptador(tipo, base_url.strip(), modelo.strip(), chave)
    except mod_provedores.ErroProvedor as exc:
        return {"ok": False, "detalhe": exc.codigo, "primeiro_token_ms": None}
    except ValueError as exc:
        return {"ok": False, "detalhe": str(exc), "primeiro_token_ms": None}

    mensagens = [{"role": "user", "content": TEXTO_TESTE}]
    t0 = time.monotonic()
    primeiro_token_ms: int | None = None
    texto_recebido = ""

    try:
        async with asyncio.timeout(TIMEOUT_TOTAL_S):
            async for evento in adaptador.inferir(mensagens, ferramentas=None, imagem=None, cancelamento=None):
                if evento.tipo == "texto":
                    conteudo = evento.dados.get("conteudo", "")
                    if conteudo and primeiro_token_ms is None:
                        primeiro_token_ms = int((time.monotonic() - t0) * 1000)
                    texto_recebido += conteudo
                elif evento.tipo == "fim":
                    break
                elif evento.tipo == "erro":
                    detalhe_erro = evento.dados.get("mensagem") or evento.dados.get("detalhe") or "erro_no_stream"
                    return {"ok": False, "detalhe": str(detalhe_erro)[:200], "primeiro_token_ms": primeiro_token_ms}
    except asyncio.TimeoutError:
        return {"ok": False, "detalhe": f"timeout_{TIMEOUT_TOTAL_S:.0f}s", "primeiro_token_ms": primeiro_token_ms}
    except mod_provedores.ErroProvedor as exc:
        return {"ok": False, "detalhe": exc.codigo, "primeiro_token_ms": primeiro_token_ms}
    except Exception as exc:  # pragma: no cover - defesa contra erros inesperados
        log.warning("testar_cerebro erro inesperado: %s", type(exc).__name__)
        return {"ok": False, "detalhe": f"erro_inesperado: {type(exc).__name__}"[:200], "primeiro_token_ms": primeiro_token_ms}

    if not texto_recebido.strip() and primeiro_token_ms is None:
        return {"ok": False, "detalhe": "sem_resposta_do_modelo", "primeiro_token_ms": None}

    return {"ok": True, "detalhe": "resposta_recebida", "primeiro_token_ms": primeiro_token_ms}

async def testar_cerebro(tipo: str, base_url: str, modelo: str, chave: str = ""):
    """Prazo total inclui espera da trava, sondagem e infer?ncia, sem troca impl?cita."""
    try:
        async with asyncio.timeout(TIMEOUT_TOTAL_S):
            if tipo == "lmstudio":
                async with _exclusivo(base_url):
                    return await _testar_cerebro(tipo, base_url, modelo, chave)
            return await _testar_cerebro(tipo, base_url, modelo, chave)
    except TimeoutError:
        return {"ok": False, "detalhe": f"timeout_{TIMEOUT_TOTAL_S:.0f}s", "primeiro_token_ms": None}
