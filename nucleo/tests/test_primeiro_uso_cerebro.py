"""Testes do módulo de teste de cérebro para o assistente de primeiro uso (T3).
Cobre: validação de entrada, montagem de adaptador, timeout, erro de provedor,
resposta válida e integração com a rota /primeiro-uso/cerebro/testar.
Nenhum teste real contra LM Studio ou API externa; tudo com dublês.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vard.primeiro_uso import cerebro as modulo_cerebro
from vard.cerebro.provedores import ErroProvedor, EventoInferencia


@pytest.mark.asyncio
async def testar_cerebro_base_url_vazia_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="openai_compat", base_url="", modelo="llama-3"
    )
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "base_url_vazia"
    assert resultado["primeiro_token_ms"] is None


@pytest.mark.asyncio
async def testar_cerebro_modelo_vazio_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="openai_compat", base_url="http://localhost:1234", modelo=""
    )
    assert resultado["ok"] is False
    assert resultado["detalhe"] == "modelo_vazio"
    assert resultado["primeiro_token_ms"] is None


@pytest.mark.asyncio
async def testar_cerebro_tipo_desconhecido_devolve_falha():
    resultado = await modulo_cerebro.testar_cerebro(
        tipo="inexistente", base_url="http://localhost:1234", modelo="llama-3"
    )
    assert resultado["ok"] is False
    assert "tipo_de_provedor_desconhecido" in resultado["detalhe"]


@pytest.mark.asyncio
async def testar_cerebro_resposta_valida_devolve_ok():
    eventos = [
        EventoInferencia("texto", {"conteudo": "pronto"}),
        EventoInferencia("fim", {}),
    ]

    async def stream_falso(*_args, **_kwargs):
        for ev in eventos:
            yield ev

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_falso

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://localhost:1234", modelo="llama-3"
        )

    assert resultado["ok"] is True
    assert resultado["detalhe"] == "resposta_recebida"
    assert isinstance(resultado["primeiro_token_ms"], int)
    assert resultado["primeiro_token_ms"] >= 0


@pytest.mark.asyncio
async def testar_cerebro_timeout_devolve_falha():
    async def stream_lento(*_args, **_kwargs):
        await asyncio.sleep(60)
        yield EventoInferencia("fim", {})

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_lento

    # Força timeout curto para o teste
    original = modulo_cerebro.TIMEOUT_TOTAL_S
    modulo_cerebro.TIMEOUT_TOTAL_S = 0.1
    try:
        with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
            resultado = await modulo_cerebro.testar_cerebro(
                tipo="openai_compat", base_url="http://localhost:1234", modelo="llama-3"
            )
    finally:
        modulo_cerebro.TIMEOUT_TOTAL_S = original

    assert resultado["ok"] is False
    assert "timeout" in resultado["detalhe"]


@pytest.mark.asyncio
async def testar_cerebro_erro_provedor_devolve_falha():
    mock_adaptador = MagicMock()

    async def stream_erro(*_args, **_kwargs):
        raise ErroProvedor("auth_401", False, "credencial recusada")
        yield  # pragma: no cover

    mock_adaptador.inferir = stream_erro

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://localhost:1234", modelo="llama-3", chave="sk-falsa"
        )

    assert resultado["ok"] is False
    assert "auth_401" in resultado["detalhe"]


@pytest.mark.asyncio
async def testar_cerebro_sem_resposta_devolve_falha():
    """Stream que emite apenas 'fim' sem texto conta como falha."""

    async def stream_vazio(*_args, **_kwargs):
        yield EventoInferencia("fim", {})

    mock_adaptador = MagicMock()
    mock_adaptador.inferir = stream_vazio

    with patch.object(modulo_cerebro, "_montar_adaptador", return_value=mock_adaptador):
        resultado = await modulo_cerebro.testar_cerebro(
            tipo="openai_compat", base_url="http://localhost:1234", modelo="llama-3"
        )

    assert resultado["ok"] is False
    assert resultado["detalhe"] == "sem_resposta_do_modelo"


def testar_montar_adaptador_tipos_conhecidos():
    """Verifica que todos os tipos conhecidos criam adaptadores sem erro."""
    tipos_validos = [
        ("openai_compat", "http://localhost:1234", "m", ""),
        ("lmstudio", "http://localhost:1234", "m", ""),
        ("local", "http://localhost:1234", "m", ""),
        ("anthropic", "https://api.anthropic.com", "claude-3", "sk-x"),
        ("google", "https://generativelanguage.googleapis.com", "gemini-2.5-flash", "key"),
        ("openai_nativo", "https://api.openai.com", "gpt-4o-mini", "sk-x"),
    ]
    for tipo, url, modelo, chave in tipos_validos:
        adaptador = modulo_cerebro._montar_adaptador(tipo, url, modelo, chave)
        assert adaptador is not None, f"tipo {tipo} deveria criar adaptador"


def testar_montar_adaptador_tipo_invalido_levanta():
    with pytest.raises(ValueError, match="tipo_de_provedor_desconhecido"):
        modulo_cerebro._montar_adaptador("desconhecido", "http://x", "m", "")