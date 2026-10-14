"""Cliente MCP stdio mínimo para os MCPs do Vard, igual ao que o OpenJarvis faz (Popen em modo texto
com a codificação do Windows). Usado pelo teste de seam e pelo preflight."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path

# Pasta nucleo/ do projeto: é nela que uv run --project precisa apontar (e não na raiz do repositório).
NUCLEO = Path(__file__).resolve().parent.parent


def chamar_ferramenta(
    nome: str, argumentos: dict | None = None, *, utf8: bool = True, timeout: float = 60,
    script: str = "mesa_mcp.py",
) -> str:
    """Sobe <script> (um MCP do Vard), faz o handshake e chama uma ferramenta; devolve o texto da resposta.

    Imita o OpenJarvis: Popen(text=True) sem `encoding` usa a codificação padrão do processo
    LEITOR. Com PYTHONUTF8=1 no OpenJarvis ela é UTF-8; sem, é cp1252 neste PC. O SDK mcp
    sempre escreve UTF-8. Por isso utf8=False levanta UnicodeDecodeError com "Á", "∅" ou "🔍".
    VARD_SEM_VIGIA=1: um cliente curto (preflight, prova) nunca sobe uma segunda vigia.
    """
    codificacao = "utf-8" if utf8 else "cp1252"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    if utf8:
        env["PYTHONUTF8"] = "1"
    env["VARD_SEM_VIGIA"] = "1"
    proc = subprocess.Popen(
        ["uv", "run", "--project", str(NUCLEO), "python", str(NUCLEO / script)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding=codificacao, env=env,
    )
    linhas: queue.Queue = queue.Queue()

    def ler() -> None:
        try:
            for linha in proc.stdout:  # type: ignore[union-attr]
                linhas.put(linha)
        except Exception as exc:  # noqa: BLE001 — repassa à thread principal (ex.: UnicodeDecodeError)
            linhas.put(exc)
        linhas.put(None)

    threading.Thread(target=ler, daemon=True).start()

    def enviar(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def esperar(id_: int) -> dict:
        while True:
            item = linhas.get(timeout=timeout)
            if isinstance(item, Exception):
                raise item
            if item is None:
                raise RuntimeError(f"{script} encerrou sem responder")
            msg = json.loads(item)
            if msg.get("id") == id_:
                return msg

    try:
        enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "vard-teste", "version": "0"}}})
        esperar(1)
        enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": nome, "arguments": argumentos or {}}})
        resposta = esperar(2)
    finally:
        proc.kill()
        proc.wait(timeout=10)
    if "error" in resposta:
        raise RuntimeError(str(resposta["error"])[:200])
    return "".join(c.get("text", "") for c in resposta["result"].get("content", []))
