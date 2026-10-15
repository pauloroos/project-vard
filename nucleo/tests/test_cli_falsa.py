"""Testes da CLI falsa (T13).

A CLI falsa é um processo real que lê NDJSON do stdin e responde no dialeto
pedido. Estes testes exercitam o comportamento observado na sondagem real,
sem depender de rede ou conta.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "cli"
CLI_FALSA = Path(__file__).parent / "fixtures" / "cli_falsa.py"


def _rodar_cli_falsa(
    dialeto: str,
    entrada: str,
    falhar: str | None = None,
) -> tuple[list[dict], int]:
    """Roda a CLI falsa como subprocesso e retorna (eventos JSON, returncode)."""
    cmd = [sys.executable, str(CLI_FALSA), "--dialeto", dialeto]
    if falhar:
        cmd += ["--falhar", falhar]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout, _ = proc.communicate(input=entrada, timeout=10)
    eventos: list[dict] = []
    for linha in stdout.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            eventos.append(json.loads(linha))
        except json.JSONDecodeError:
            # linhas não-JSON são ignoradas (comportamento esperado com banner)
            continue
    return eventos, proc.returncode


def _msg_user(texto: str, dialeto: str) -> str:
    """Monta linha NDJSON de entrada no dialeto certo."""
    payload = {
        "role": "user",
        "content": [{"type": "text", "text": texto}],
    }
    if dialeto == "claude":
        return json.dumps({"type": "user", "message": payload})
    return json.dumps({"event": "user", "message": payload})


class TestCliFalsaClaude:
    def test_init_com_ferramentas_e_mcp(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("oi", "claude"))
        assert rc == 0
        init = next(e for e in eventos if e.get("type") == "system" and e.get("subtype") == "init")
        assert "Bash" in init["tools"]
        assert any(m["name"] == "vard-mesa" for m in init["mcp_servers"])

    def test_texto_em_delta(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("ola", "claude"))
        assert rc == 0
        textos = [
            c["text"]
            for e in eventos
            if e.get("type") == "assistant"
            for c in e.get("message", {}).get("content", [])
            if c.get("type") == "text"
        ]
        assert any("eco:" in t for t in textos)

    def test_ferramenta_quando_mencionada(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("use ferramenta", "claude"))
        assert rc == 0
        tool_use = [
            c
            for e in eventos
            if e.get("type") == "assistant"
            for c in e.get("message", {}).get("content", [])
            if c.get("type") == "server_tool_use"
        ]
        assert len(tool_use) >= 1
        assert tool_use[0]["name"] == "Bash"

    def test_result_final_com_num_turns(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("oi", "claude"))
        assert rc == 0
        result = next(e for e in eventos if e.get("type") == "result")
        assert result["stop_reason"] == "end_turn"
        assert result["num_turns"] == 1
        assert result["is_error"] is False

    def test_erro_login(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("oi", "claude"), falhar="login")
        assert rc == 0
        result = next(e for e in eventos if e.get("type") == "result")
        assert result["is_error"] is True
        assert result["api_error_status"] == 401

    def test_banner_nao_quebra_fluxo(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("oi", "claude"), falhar="banner")
        assert rc == 0
        # deve ter init + assistant + result apesar do banner não-JSON
        tipos = [e.get("type") for e in eventos]
        assert "system" in tipos
        assert "assistant" in tipos
        assert "result" in tipos

    def test_cair_retorna_codigo_nao_zero(self) -> None:
        eventos, rc = _rodar_cli_falsa("claude", _msg_user("oi", "claude"), falhar="cair")
        assert rc != 0
        # não deve ter result de sucesso quando o processo cai
        results = [e for e in eventos if e.get("type") == "result" and not e.get("is_error")]
        assert len(results) == 0


class TestCliFalsaAgy:
    def test_init_com_ferramentas_e_permissao(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("oi", "agy"))
        assert rc == 0
        init = next(e for e in eventos if e.get("event") == "init")
        assert "run_command" in init["init"]["tools"]
        assert init["init"]["permission_mode"] == "request-review"

    def test_step_update_com_text_delta(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("ola", "agy"))
        assert rc == 0
        deltas = [
            e["step_update"]["text_delta"]
            for e in eventos
            if e.get("event") == "step_update"
            and e.get("step_update", {}).get("state") == "ACTIVE"
        ]
        assert any("eco:" in d for d in deltas)

    def test_ferramenta_quando_mencionada(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("use ferramenta", "agy"))
        assert rc == 0
        tool_use = [
            c
            for e in eventos
            if e.get("event") == "assistant"
            for c in e.get("message", {}).get("content", [])
            if c.get("type") == "tool_use"
        ]
        assert len(tool_use) >= 1
        assert tool_use[0]["name"] == "run_command"

    def test_result_final_success(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("oi", "agy"))
        assert rc == 0
        result = next(e for e in eventos if e.get("event") == "result")
        assert result["result"]["status"] == "SUCCESS"
        assert result["result"]["num_turns"] == 1

    def test_erro_login(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("oi", "agy"), falhar="login")
        assert rc == 0
        result = next(e for e in eventos if e.get("event") == "result")
        assert result["result"]["status"] == "ERROR"
        assert "authentication" in result["result"]["error"].lower()

    def test_banner_nao_quebra_fluxo(self) -> None:
        eventos, rc = _rodar_cli_falsa("agy", _msg_user("oi", "agy"), falhar="banner")
        assert rc == 0
        eventos_tipos = [e.get("event") for e in eventos]
        assert "init" in eventos_tipos
        assert "result" in eventos_tipos