"""Servidor MCP falso para testes do cérebro (T3).
Implementa o protocolo JSON-RPC sobre stdio: initialize, notifications/initialized,
tools/list e tools/call. Usa apenas a biblioteca padrão para evitar dependências
no processo filho. O pai envia/recebe mensagens delimitadas por newline.
"""
from __future__ import annotations

import json
import sys
import time


def _write(msg: dict) -> None:
    linha = json.dumps(msg, ensure_ascii=False) + "\n"
    sys.stdout.write(linha)
    sys.stdout.flush()


def _read() -> dict | None:
    linha = sys.stdin.readline()
    if not linha:
        return None
    try:
        return json.loads(linha)
    except ValueError:
        return None


FERRAMENTAS = [
    {
        "name": "hora_atual",
        "description": "Devolve a hora atual em ISO-8601.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "eco",
        "description": "Repete o texto recebido.",
        "inputSchema": {
            "type": "object",
            "properties": {"texto": {"type": "string"}},
            "required": ["texto"],
        },
    },
    {
        "name": "falha_sempre",
        "description": "Sempre retorna erro.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "bloqueante",
        "description": "Bloqueia por N segundos (default 5).",
        "inputSchema": {
            "type": "object",
            "properties": {"segundos": {"type": "number"}},
        },
    },
]


def _call_tool(name: str, arguments: dict) -> dict:
    if name == "hora_atual":
        return {"content": [{"type": "text", "text": time.strftime("%Y-%m-%dT%H:%M:%S")}]}
    if name == "eco":
        texto = arguments.get("texto", "")
        if not isinstance(texto, str):
            return {"isError": True, "content": [{"type": "text", "text": "texto deve ser string"}]}
        return {"content": [{"type": "text", "text": texto}]}
    if name == "falha_sempre":
        return {"isError": True, "content": [{"type": "text", "text": "erro simulado"}]}
    if name == "bloqueante":
        segundos = float(arguments.get("segundos", 5))
        time.sleep(segundos)
        return {"content": [{"type": "text", "text": f"bloquei {segundos}s"}]}
    return {"isError": True, "content": [{"type": "text", "text": f"ferramenta desconhecida: {name}"}]}


def main() -> None:
    initialized = False
    while True:
        msg = _read()
        if msg is None:
            break
        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            _write({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mcp-falso", "version": "1.0"},
                },
            })
        elif method == "notifications/initialized":
            initialized = True
            # Notificação: sem resposta
        elif method == "tools/list":
            _write({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": FERRAMENTAS},
            })
        elif method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = _call_tool(name, arguments)
            _write({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result,
            })
        else:
            if msg_id is not None:
                _write({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"método desconhecido: {method}"},
                })


if __name__ == "__main__":
    main()