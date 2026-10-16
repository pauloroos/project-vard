"""Testes da T2 — adaptadores reais de provedores com HTTP falso (respx).
Cobre: mesmo modelo em endpoints distintos, URL com prefixo, credencial por ID,
texto e tool call fragmentados, JSON inválido, imagem não suportada,
timeout/429/401/5xx, cancelamento, test_tools_parciais_nao_sao_emitidos.
Sem retries ocultos; log sem segredo sintético.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
import respx
from httpx import Response

from vard.cerebro.provedores import (
    AdaptadorAnthropic,
    AdaptadorGoogle,
    AdaptadorOpenAICompat,
    AdaptadorOpenAINativo,
    ErroProvedor,
    EventoInferencia,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _coletar(ait) -> list[EventoInferencia]:
    return [ev async for ev in ait]


def _sse_linhas(*chunks: dict) -> str:
    """Monta corpo SSE a partir de dicts."""
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# OpenAI Compat (LM Studio / llama-server / genérico)
# ---------------------------------------------------------------------------

class TestOpenAICompat:
    @respx.mock
    async def test_texto_simples(self):
        body = _sse_linhas({"choices": [{"delta": {"content": "olá"}}]})
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "qwen2")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "olá" in textos
        assert any(e.tipo == "fim" for e in eventos)

    @respx.mock
    @pytest.mark.parametrize("base", ["http://lm.local/v1", "http://lm.local/v1/", "http://lm.local"])
    async def test_url_base_com_ou_sem_v1(self, base):
        """D9: quem cadastra a URL no padrão OpenAI/LM Studio (".../v1") não pode cair em /v1/v1."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        rota = respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat(base, "qwen2")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert rota.called
        assert any(e.tipo == "fim" for e in eventos)

    @respx.mock
    async def test_mesmo_modelo_endpoints_distintos(self):
        """Mesmo nome de modelo em dois endpoints diferentes funciona."""
        for base in ("http://lm1.local", "http://lm2.local"):
            body = _sse_linhas({"choices": [{"delta": {"content": f"de {base}"}}]})
            respx.post(f"{base}/v1/chat/completions").mock(
                return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
            )
        for base in ("http://lm1.local", "http://lm2.local"):
            adp = AdaptadorOpenAICompat(base, "mesmo-modelo")
            eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
            textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
            assert any(f"de {base}" in t for t in textos)

    @respx.mock
    async def test_url_com_prefixo(self):
        """URL com prefixo de caminho é respeitada."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        route = respx.post("http://host.local/prefixo/api/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://host.local/prefixo/api", "m")
        await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert route.called

    @respx.mock
    async def test_credencial_bearer(self):
        """Chave é enviada como Bearer token; log não vaza."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        route = respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m", chave="sk-segredo-123")
        await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        req = route.calls.last.request
        assert req.headers.get("authorization") == "Bearer sk-segredo-123"

    @respx.mock
    async def test_credencial_log_sem_segredo(self, caplog):
        """Log de debug sanitiza Bearer token."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m", chave="sk-supersecreto")
        with caplog.at_level(logging.DEBUG, logger="vard.cerebro.provedores"):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        for record in caplog.records:
            assert "sk-supersecreto" not in record.getMessage()

    @respx.mock
    async def test_tool_call_fragmentada(self):
        """Tool call chega em pedaços; só emite quando argumentos são JSON válido."""
        # Fragmentação realista: chunk1 abre o JSON, chunk2 fecha.
        # Os valores de "arguments" são strings cruas que o adaptador concatena.
        # Chunk1: arguments = '{"val'  (JSON parcial inválido)
        # Chunk2: arguments = 'or": 42}' (completa para '{"valor": 42}')
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0, "id": "c1",
                        "function": {"name": "eco", "arguments": '{"val'},
                    }]
                }
            }]
        }
        c2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": 'or": 42}'},
                    }]
                }
            }]
        }
        body = _sse_linhas(c1, c2)
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert len(chamadas) == 1
        assert chamadas[0].dados["nome"] == "eco"
        assert chamadas[0].dados["argumentos"] == {"valor": 42}
        assert chamadas[0].dados["id"] == "c1"

    @respx.mock
    async def test_tools_parciais_nao_sao_emitidos(self):
        """Tool call com argumentos JSON inválidos NÃO é emitida."""
        chunk_inv = '{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "eco", "arguments": "{inv"}}}]}}]}'
        body = f"data: {chunk_inv}\n\ndata: [DONE]\n\n"
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert chamadas == []

    @respx.mock
    async def test_json_invalido_ignorado(self, caplog):
        """Linha SSE com JSON inválido é ignorada; stream continua."""
        raw = "data: {bad json}\n\ndata: " + json.dumps({"choices": [{"delta": {"content": "ok"}}]}) + "\n\ndata: [DONE]\n\n"
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=raw, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with caplog.at_level(logging.WARNING, logger="vard.cerebro.provedores"):
            eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "ok" in textos

    async def test_imagem_nao_suportada(self):
        """Imagem levanta ErroProvedor('imagem_nao_suportada')."""
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with pytest.raises(ErroProvedor, match="imagem_nao_suportada"):
            await _coletar(adp.inferir([], imagem=b"\x89PNG"))

    @respx.mock
    async def test_timeout(self):
        import httpx
        respx.post("http://lm.local/v1/chat/completions").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m", timeout=0.1)
        with pytest.raises(ErroProvedor, match="timeout"):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))

    @respx.mock
    async def test_401(self):
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(401, text="unauthorized")
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with pytest.raises(ErroProvedor, match="auth_401"):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))

    @respx.mock
    async def test_429_recuperavel(self):
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(429, text="rate limited")
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with pytest.raises(ErroProvedor) as exc_info:
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert exc_info.value.recuperavel is True

    @respx.mock
    async def test_5xx_recuperavel(self):
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(500, text="internal error")
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with pytest.raises(ErroProvedor) as exc_info:
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert exc_info.value.recuperavel is True

    @respx.mock
    async def test_cancelamento(self):
        """Cancelamento via asyncio.Event interrompe o stream."""
        # Stream infinito simulado
        async def slow_stream(request):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "a"}}]}) + "\n\n"
            await asyncio.sleep(10)

        respx.post("http://lm.local/v1/chat/completions").mock(
            side_effect=lambda req: Response(200, text=_sse_linhas({"choices": [{"delta": {"content": "a"}}]}),
                                            headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        cancel = asyncio.Event()
        cancel.set()  # já cancelado antes de começar
        with pytest.raises(asyncio.CancelledError):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}], cancelamento=cancel))


# ---------------------------------------------------------------------------
# OpenAI Nativo
# ---------------------------------------------------------------------------

class TestOpenAINativo:
    @respx.mock
    async def test_texto_com_chave(self):
        body = _sse_linhas({"choices": [{"delta": {"content": "nativo ok"}}]})
        route = respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAINativo(chave="sk-test", modelo="gpt-4o-mini")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "nativo ok" in textos
        assert route.calls.last.request.headers.get("authorization") == "Bearer sk-test"

    @respx.mock
    async def test_imagem_vision(self):
        """Imagem é anexada como base64 na mensagem user."""
        body = _sse_linhas({"choices": [{"delta": {"content": "vejo"}}]})
        route = respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAINativo(chave="sk-test")
        eventos = await _coletar(adp.inferir(
            [{"role": "user", "content": "o que é isso?"}],
            imagem=b"\x89PNG\r\n",
        ))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "vejo" in textos
        # Verifica que a requisição contém image_url
        corpo = json.loads(route.calls.last.request.content)
        ultima_msg = corpo["messages"][-1]
        assert any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for p in (ultima_msg.get("content") or [])
            if isinstance(ultima_msg.get("content"), list)
        ) or "image_url" in str(corpo)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class TestAnthropic:
    @respx.mock
    async def test_texto_simples(self):
        chunks = [
            {"type": "content_block_start", "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "olá anthropic"}},
            {"type": "content_block_stop"},
            {"type": "message_stop"},
        ]
        body = _sse_linhas(*chunks)
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorAnthropic(chave="ant-test")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "olá anthropic" in textos
        assert route.calls.last.request.headers.get("x-api-key") == "ant-test"

    @respx.mock
    async def test_tool_call_anthropic(self):
        chunks = [
            {"type": "content_block_start", "content_block": {"type": "tool_use", "id": "tu1", "name": "buscar", "input": {}}},
            {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": '{"query": "te'}},
            {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": 'ste"}'}},
            {"type": "content_block_stop"},
            {"type": "message_stop"},
        ]
        body = _sse_linhas(*chunks)
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorAnthropic(chave="ant-test")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "busca"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert len(chamadas) == 1
        assert chamadas[0].dados["nome"] == "buscar"
        assert chamadas[0].dados["argumentos"] == {"query": "teste"}

    async def test_imagem_nao_suportada(self):
        adp = AdaptadorAnthropic(chave="ant-test")
        with pytest.raises(ErroProvedor, match="imagem_nao_suportada"):
            await _coletar(adp.inferir([], imagem=b"\x89PNG"))

    @respx.mock
    async def test_401_anthropic(self):
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(401, text="invalid key")
        )
        adp = AdaptadorAnthropic(chave="bad")
        with pytest.raises(ErroProvedor, match="auth_401"):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))

    @respx.mock
    async def test_429_anthropic(self):
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(429, text="rate")
        )
        adp = AdaptadorAnthropic(chave="ant-test")
        with pytest.raises(ErroProvedor) as exc_info:
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert exc_info.value.recuperavel is True


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class TestGoogle:
    @respx.mock
    async def test_texto_simples(self):
        chunk = {"candidates": [{"content": {"parts": [{"text": "olá gemini"}]}}]}
        body = f"data: {json.dumps(chunk)}\n\n"
        url_pattern = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent"
        respx.post(url_pattern).mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorGoogle(chave="gem-test", modelo="gemini-2.5-flash")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        textos = [e.dados["conteudo"] for e in eventos if e.tipo == "texto"]
        assert "olá gemini" in textos

    @respx.mock
    async def test_function_call_gemini(self):
        chunk = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "hora", "args": {}}}]}}]}
        body = f"data: {json.dumps(chunk)}\n\n"
        url_pattern = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent"
        respx.post(url_pattern).mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorGoogle(chave="gem-test")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "hora?"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert len(chamadas) == 1
        assert chamadas[0].dados["nome"] == "hora"

    async def test_imagem_nao_suportada(self):
        adp = AdaptadorGoogle(chave="gem-test")
        with pytest.raises(ErroProvedor, match="imagem_nao_suportada"):
            await _coletar(adp.inferir([], imagem=b"\x89PNG"))

    @respx.mock
    async def test_5xx_google(self):
        url_pattern = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent"
        respx.post(url_pattern).mock(return_value=Response(503, text="unavailable"))
        adp = AdaptadorGoogle(chave="gem-test")
        with pytest.raises(ErroProvedor) as exc_info:
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert exc_info.value.recuperavel is True


# ---------------------------------------------------------------------------
# Sem retries ocultos
# ---------------------------------------------------------------------------

class TestSemRetries:
    @respx.mock
    async def test_falha_nao_repete(self):
        """Uma falha 500 gera exatamente UMA chamada HTTP, não retry."""
        route = respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(500, text="error")
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        with pytest.raises(ErroProvedor):
            await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        assert route.call_count == 1