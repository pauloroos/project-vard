"""Testes da T010 — contrato de ferramentas nos três adaptadores (FR-010).

Verifica:
- Conversão OpenAI: formato interno → {type, function}
- Conversão Anthropic: formato interno → {name, description, input_schema}
- Acumulação de argumentos por índice até finish_reason (sem emissão prematura)
- Sem emissão de {} quando argumentos estão vazios ou inválidos
- Gemini aceita formato interno sem transformação extra
"""
from __future__ import annotations

import json
from typing import Any

import pytest
import respx
from httpx import Response

from vard.cerebro.provedores import (
    AdaptadorAnthropic,
    AdaptadorGoogle,
    AdaptadorOpenAICompat,
    EventoInferencia,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _coletar(ait) -> list[EventoInferencia]:
    return [ev async for ev in ait]


def _sse_linhas(*chunks: dict) -> str:
    """Monta corpo SSE a partir de dicts."""
    return "".join(f"data: {json.dumps(c)}\n" for c in chunks) + "data: [DONE]\n"


FERRAMENTA_INTERNA = [
    {
        "name": "buscar",
        "description": "Busca web",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    }
]


# ---------------------------------------------------------------------------
# Conversão OpenAI
# ---------------------------------------------------------------------------

class TestConversaoOpenAI:
    @respx.mock
    async def test_formata_interno_para_openai(self):
        """Formato interno {name, description, parameters} é convertido para
        {type: 'function', function: {name, description, parameters}}."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        rota = respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        await _coletar(adp.inferir(
            [{"role": "user", "content": "oi"}],
            ferramentas=FERRAMENTA_INTERNA,
        ))
        req_body = json.loads(rota.calls.last.request.content)
        tools = req_body["tools"]
        assert len(tools) == 1
        t = tools[0]
        assert t["type"] == "function"
        assert t["function"]["name"] == "buscar"
        assert t["function"]["description"] == "Busca web"
        assert t["function"]["parameters"] == FERRAMENTA_INTERNA[0]["parameters"]

    @respx.mock
    async def test_formata_openai_ja_formatado_passa_direto(self):
        """Se já vier no formato OpenAI, repassa sem dupla conversão."""
        body = _sse_linhas({"choices": [{"delta": {"content": "ok"}}]})
        rota = respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        tool_oai = {
            "type": "function",
            "function": {
                "name": "eco",
                "description": "Eco simples",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        await _coletar(adp.inferir(
            [{"role": "user", "content": "oi"}],
            ferramentas=[tool_oai],
        ))
        req_body = json.loads(rota.calls.last.request.content)
        assert req_body["tools"] == [tool_oai]


# ---------------------------------------------------------------------------
# Conversão Anthropic
# ---------------------------------------------------------------------------

class TestConversaoAnthropic:
    @respx.mock
    async def test_formata_interno_para_anthropic(self):
        """Formato interno {name, description, parameters} é convertido para
        {name, description, input_schema}."""
        # Resposta mínima do Anthropic com message_stop
        evento_start = {"type": "message_start", "message": {"id": "msg_1"}}
        evento_stop = {"type": "message_stop"}
        body = f"data: {json.dumps(evento_start)}\ndata: {json.dumps(evento_stop)}\n"
        rota = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorAnthropic(chave="sk-ant-test")
        await _coletar(adp.inferir(
            [{"role": "user", "content": "oi"}],
            ferramentas=FERRAMENTA_INTERNA,
        ))
        req_body = json.loads(rota.calls.last.request.content)
        tools = req_body["tools"]
        assert len(tools) == 1
        t = tools[0]
        assert t["name"] == "buscar"
        assert t["description"] == "Busca web"
        assert t["input_schema"] == FERRAMENTA_INTERNA[0]["parameters"]

    @respx.mock
    async def test_nome_nao_vazio_no_formato_interno(self):
        """O nome da ferramenta NÃO pode vir vazio quando usando formato interno."""
        evento_start = {"type": "message_start", "message": {"id": "msg_1"}}
        evento_stop = {"type": "message_stop"}
        body = f"data: {json.dumps(evento_start)}\ndata: {json.dumps(evento_stop)}\n"
        rota = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorAnthropic(chave="sk-ant-test")
        await _coletar(adp.inferir(
            [{"role": "user", "content": "oi"}],
            ferramentas=FERRAMENTA_INTERNA,
        ))
        req_body = json.loads(rota.calls.last.request.content)
        assert req_body["tools"][0]["name"] != ""


# ---------------------------------------------------------------------------
# Acumulação de argumentos (OpenAI Compat)
# ---------------------------------------------------------------------------

class TestAcumulacaoArgumentos:
    @respx.mock
    async def test_argumentos_fragmentados_acumulados(self):
        """Argumentos fragmentados são acumulados por índice e emitidos completos."""
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0, "id": "call_1",
                        "function": {"name": "buscar", "arguments": '{"query": "tes'},
                    }]
                }
            }]
        }
        c2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": 'te"}'},
                    }]
                }
            }]
        }
        body = _sse_linhas(c1, c2)
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "busca"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert len(chamadas) == 1
        assert chamadas[0].dados["argumentos"] == {"query": "teste"}
        assert chamadas[0].dados["nome"] == "buscar"

    @respx.mock
    async def test_sem_emissao_prematura_durante_streaming(self):
        """Nenhuma chamada é emitida durante o streaming (apenas após fim)."""
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0, "id": "call_1",
                        "function": {"name": "eco", "arguments": '{"val'},
                    }]
                }
            }]
        }
        # JSON parcial '{"val' não é válido; se o código emitir durante o stream,
        # teríamos uma chamada prematura. A emissão deve ser apenas pós-stream.
        body = _sse_linhas(c1)
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        # JSON parcial inválido → nenhuma chamada emitida
        assert chamadas == []

    @respx.mock
    async def test_sem_emissao_com_argumentos_vazios(self):
        """Tool call sem argumentos (string vazia) NÃO é emitida como {}."""
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0, "id": "call_1",
                        "function": {"name": "sem_args", "arguments": ""},
                    }]
                }
            }]
        }
        body = _sse_linhas(c1)
        respx.post("http://lm.local/v1/chat/completions").mock(
            return_value=Response(200, text=body, headers={"content-type": "text/event-stream"})
        )
        adp = AdaptadorOpenAICompat("http://lm.local", "m")
        eventos = await _coletar(adp.inferir([{"role": "user", "content": "oi"}]))
        chamadas = [e for e in eventos if e.tipo == "chamada"]
        assert chamadas == []

    @respx.mock
    async def test_multiplos_indices_acumulados_separadamente(self):
        """Dois tool calls com índices diferentes são acumulados independentemente."""
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "c0", "function": {"name": "a", "arguments": '{"x":'}},
                        {"index": 1, "id": "c1", "function": {"name": "b", "arguments": '{"y":'}},
                    ]
                }
            }]
        }
        c2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": ' 1}'}},
                        {"index": 1, "function": {"arguments": ' 2}'}},
                    ]
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
        assert len(chamadas) == 2
        nomes = {c.dados["nome"] for c in chamadas}
        assert nomes == {"a", "b"}
        args_map = {c.dados["nome"]: c.dados["argumentos"] for c in chamadas}
        assert args_map["a"] == {"x": 1}
        assert args_map["b"] == {"y": 2}


# ---------------------------------------------------------------------------
# Gemini aceita formato interno
# ---------------------------------------------------------------------------

class TestGeminiFormatoInterno:
    @respx.mock
    async def test_gemini_aceita_formato_interno(self):
        """Adaptador Google passa ferramentas no formato interno sem erro."""
        chunk = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "ok"}]
                }
            }]
        }
        body = f"data: {json.dumps(chunk)}\n\n"
        rota = respx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent"
        ).mock(
            return_value=Response(200, text=body, headers={"content-type": "application/json"})
        )
        adp = AdaptadorGoogle(chave="test-key")
        eventos = await _coletar(adp.inferir(
            [{"role": "user", "content": "oi"}],
            ferramentas=FERRAMENTA_INTERNA,
        ))
        assert any(e.tipo == "fim" for e in eventos)
        # Verifica que a requisição foi feita com functionDeclarations
        req_body = json.loads(rota.calls.last.request.content)
        tools = req_body.get("tools", [])
        assert len(tools) == 1
        decls = tools[0].get("functionDeclarations", [])
        assert len(decls) == 1
        assert decls[0]["name"] == "buscar"
        assert decls[0]["description"] == "Busca web"
        assert decls[0]["parameters"] == FERRAMENTA_INTERNA[0]["parameters"]