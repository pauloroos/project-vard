#!/usr/bin/env python3
"""CLI falsa para testes da T13.

Lê NDJSON do stdin e responde no dialeto pedido por --dialeto claude|agy.
Modos de falha: --falhar login|cair|lento|banner.

Uso em testes:
    subprocess.Popen(
        [sys.executable, "cli_falsa.py", "--dialeto", "claude"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
"""
from __future__ import annotations

import argparse
import json
import sys
import time


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ler_stdin() -> list[dict]:
    mensagens: list[dict] = []
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            mensagens.append(json.loads(linha))
        except json.JSONDecodeError:
            # ignora linhas não-JSON (comportamento observado no claude com hooks)
            continue
    return mensagens


def _responder_claude(mensagens: list[dict], falhar: str | None) -> None:
    sessao = "sess-falsa-claude"
    # evento init
    _emit({
        "type": "system",
        "subtype": "init",
        "cwd": "/tmp/vard-cli-teste",
        "session_id": sessao,
        "tools": ["Bash", "Read", "Write"],
        "mcp_servers": [{"name": "vard-mesa", "status": "connected", "source": "user"}],
        "model": "claude-opus-5-5",
        "permissionMode": "auto",
    })

    if falhar == "login":
        _emit({
            "type": "result",
            "stop_reason": None,
            "session_id": sessao,
            "result": "API Error: 401 authentication required",
            "num_turns": 0,
            "is_error": True,
            "api_error_status": 401,
        })
        return

    if falhar == "banner":
        # linha não-JSON antes do fluxo normal; deve ser ignorada pelo adaptador
        sys.stdout.write("Aviso: atualização disponível para claude-cli\n")
        sys.stdout.flush()

    if falhar == "lento":
        time.sleep(2)

    for msg in mensagens:
        conteudo = ""
        payload = msg.get("message", {})
        for bloco in payload.get("content", []):
            if bloco.get("type") == "text":
                conteudo += bloco.get("text", "")
        resposta = f"eco: {conteudo}" if conteudo else "eco: vazio"

        # delta de texto
        _emit({
            "type": "assistant",
            "message": {
                "id": "msg-falsa",
                "role": "assistant",
                "content": [{"type": "text", "text": resposta}],
            },
        })

        # uso de ferramenta sintético quando a mensagem menciona "ferramenta"
        if "ferramenta" in conteudo.lower():
            _emit({
                "type": "assistant",
                "message": {
                    "id": "msg-falsa-tool",
                    "role": "assistant",
                    "content": [{
                        "type": "server_tool_use",
                        "id": "toolu-falso",
                        "name": "Bash",
                        "input": {"command": "echo teste"},
                    }],
                },
            })
            _emit({
                "type": "assistant",
                "message": {
                    "id": "msg-falsa-tool-res",
                    "role": "assistant",
                    "content": [{
                        "type": "bash_tool_result",
                        "tool_use_id": "toolu-falso",
                        "content": "teste",
                    }],
                },
            })

    if falhar == "cair":
        sys.exit(1)

    _emit({
        "type": "result",
        "stop_reason": "end_turn",
        "session_id": sessao,
        "result": resposta if mensagens else "",
        "num_turns": len(mensagens),
        "is_error": False,
    })


def _responder_agy(mensagens: list[dict], falhar: str | None) -> None:
    conv = "conv-falsa-agy"
    _emit({
        "event": "init",
        "conversation_id": conv,
        "init": {
            "model": "gemini-3.8-flash-low",
            "cwd": "/tmp/vard-cli-teste",
            "tools": ["run_command", "read_url_content", "write_to_file"],
            "permission_mode": "request-review",
        },
    })

    if falhar == "login":
        _emit({
            "event": "result",
            "result": {
                "conversation_id": conv,
                "status": "ERROR",
                "error": "authentication failed: not logged in",
                "response": "",
                "duration_seconds": 0,
                "num_turns": 0,
                "usage": {
                    "input_tokens": 0, "output_tokens": 0,
                    "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 0,
                },
            },
        })
        return

    if falhar == "banner":
        sys.stdout.write("aviso: nova versão do agy disponível\n")
        sys.stdout.flush()

    if falhar == "lento":
        time.sleep(2)

    resposta = ""
    for msg in mensagens:
        conteudo = ""
        payload = msg.get("message", {})
        for bloco in payload.get("content", []):
            if bloco.get("type") == "text":
                conteudo += bloco.get("text", "")
        resposta = f"eco: {conteudo}" if conteudo else "eco: vazio"

        # step_update ACTIVE com text_delta
        _emit({
            "event": "step_update",
            "step_update": {
                "conversation_id": conv,
                "step_index": 2,
                "state": "ACTIVE",
                "step_type": "agent_response",
                "text_delta": resposta,
            },
        })
        # step_update DONE fechando o passo
        _emit({
            "event": "step_update",
            "step_update": {
                "conversation_id": conv,
                "step_index": 2,
                "state": "DONE",
                "step_type": "agent_response",
                "text_delta": "\n",
                "duration_seconds": 0.1,
                "usage": {
                    "input_tokens": 10, "output_tokens": len(resposta),
                    "thinking_tokens": 0, "cache_read_tokens": 0,
                    "total_tokens": 10 + len(resposta),
                },
            },
        })

        if "ferramenta" in conteudo.lower():
            _emit({
                "event": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": "toolu-agy-falso",
                        "name": "run_command",
                        "input": {"command": "echo teste"},
                    }],
                },
            })
            _emit({
                "event": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": "toolu-agy-falso",
                        "content": "teste",
                    }],
                },
            })

    if falhar == "cair":
        sys.exit(1)

    _emit({
        "event": "result",
        "result": {
            "conversation_id": conv,
            "status": "SUCCESS",
            "response": resposta,
            "duration_seconds": 0.1,
            "num_turns": len(mensagens),
            "usage": {
                "input_tokens": 10, "output_tokens": len(resposta),
                "thinking_tokens": 0, "cache_read_tokens": 0,
                "total_tokens": 10 + len(resposta),
            },
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI falsa para testes da T13")
    parser.add_argument("--dialeto", choices=["claude", "agy"], required=True)
    parser.add_argument("--falhar", choices=["login", "cair", "lento", "banner"], default=None)
    args = parser.parse_args()

    mensagens = _ler_stdin()
    if args.dialeto == "claude":
        _responder_claude(mensagens, args.falhar)
    else:
        _responder_agy(mensagens, args.falhar)


if __name__ == "__main__":
    main()