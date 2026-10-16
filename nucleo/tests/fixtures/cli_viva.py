#!/usr/bin/env python3
"""CLI falsa viva para testes do SupervisorCli (T16).

Diferente da cli_falsa.py, esta NÃO espera EOF no stdin. Ela emite o evento
init imediatamente ao iniciar e depois lê mensagens linha a linha, respondendo
a cada uma sem bloquear. Isso permite que o supervisor mantenha o processo
vivo com stdin aberto.

Uso: subprocess.Popen([sys.executable, "cli_viva.py", "--dialeto", "claude"], ...)
"""
from __future__ import annotations

import argparse
import json
import sys
import threading


def _emit(obj: dict) -> None:
    linha = json.dumps(obj, ensure_ascii=False) + "\n"
    sys.stdout.buffer.write(linha.encode("utf-8"))
    sys.stdout.buffer.flush()


def _responder_claude(mensagem: dict) -> None:
    sessao = "sess-viva-claude"
    conteudo = ""
    payload = mensagem.get("message", {})
    for bloco in payload.get("content", []):
        if bloco.get("type") == "text":
            conteudo += bloco.get("text", "")
    resposta = f"eco: {conteudo}" if conteudo else "eco: vazio"

    _emit({
        "type": "assistant",
        "message": {
            "id": "msg-viva",
            "role": "assistant",
            "content": [{"type": "text", "text": resposta}],
        },
    })
    _emit({
        "type": "result",
        "stop_reason": "end_turn",
        "session_id": sessao,
        "result": resposta,
        "num_turns": 1,
        "is_error": False,
    })


def _responder_agy(mensagem: dict) -> None:
    conv = "conv-viva-agy"
    conteudo = ""
    payload = mensagem.get("message", {})
    for bloco in payload.get("content", []):
        if bloco.get("type") == "text":
            conteudo += bloco.get("text", "")
    resposta = f"eco: {conteudo}" if conteudo else "eco: vazio"

    _emit({
        "event": "step_update",
        "step_update": {
            "conversation_id": conv,
            "step_index": 1,
            "state": "ACTIVE",
            "step_type": "agent_response",
            "text_delta": resposta,
        },
    })
    _emit({
        "event": "step_update",
        "step_update": {
            "conversation_id": conv,
            "step_index": 1,
            "state": "DONE",
            "step_type": "agent_response",
            "text_delta": "",
            "duration_seconds": 0.01,
            "usage": {
                "input_tokens": 5, "output_tokens": len(resposta),
                "thinking_tokens": 0, "cache_read_tokens": 0,
                "total_tokens": 5 + len(resposta),
            },
        },
    })
    _emit({
        "event": "result",
        "result": {
            "conversation_id": conv,
            "status": "SUCCESS",
            "response": resposta,
            "duration_seconds": 0.01,
            "num_turns": 1,
            "usage": {
                "input_tokens": 5, "output_tokens": len(resposta),
                "thinking_tokens": 0, "cache_read_tokens": 0,
                "total_tokens": 5 + len(resposta),
            },
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI falsa viva para testes T16")
    parser.add_argument("--dialeto", choices=["claude", "agy"], required=True)
    parser.add_argument("--lento", type=float, default=0.0,
                        help="segundos de espera antes de cada resposta (simula uma resposta longa)")
    parser.add_argument("--linha-grande", type=int, default=0,
                        help="antes do init, emite eventos system como a CLI real (hooks e lista de comandos com N bytes)")
    args = parser.parse_args()

    if args.dialeto == "claude" and args.linha_grande:
        # A CLI real (claude 2.1.x) manda hook_started/hook_response e um commands_changed de dezenas de KB
        _emit({"type": "system", "subtype": "hook_started", "hook": "SessionStart"})
        _emit({"type": "system", "subtype": "hook_response", "hook": "SessionStart", "output": "ok"})
        _emit({"type": "system", "subtype": "commands_changed", "commands": ["x" * args.linha_grande]})

    sessao = "sess-viva-claude" if args.dialeto == "claude" else "conv-viva-agy"

    # Emite init IMEDIATAMENTE (não espera stdin)
    if args.dialeto == "claude":
        _emit({
            "type": "system",
            "subtype": "init",
            "cwd": "/tmp/vard-cli-viva",
            "session_id": sessao,
            "tools": ["Bash", "Read", "Write"],
            "mcp_servers": [],
            "model": "claude-teste",
            "permissionMode": "auto",
        })
    else:
        _emit({
            "event": "init",
            "conversation_id": sessao,
            "init": {
                "model": "agy-teste",
                "cwd": "/tmp/vard-cli-viva",
                "tools": ["run_command"],
                "permission_mode": "auto",
            },
        })

    # Lê mensagens linha a linha (não bloqueia esperando EOF total)
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            msg = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if args.lento:
            import time
            time.sleep(args.lento)
        if args.dialeto == "claude":
            _responder_claude(msg)
        else:
            _responder_agy(msg)


if __name__ == "__main__":
    main()