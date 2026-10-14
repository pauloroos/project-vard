"""Cliente MCP mínimo por HTTP (Streamable HTTP): initialize, tools/list e tools/call.

Usado pelo memoria_mcp (ai-memory na VPS, pelo Tailscale) e pelo preflight. Sem o SDK: a API de
cliente do mcp 2.x mudou e aqui bastam três chamadas JSON-RPC. trust_env=False: 100.x é rede privada.
"""
from __future__ import annotations

import json

import httpx

VERSAO = "2025-06-18"


class ErroMCP(Exception):
    pass


def _ler_resposta(r: httpx.Response) -> dict:
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        for linha in r.text.splitlines():
            if linha.startswith("data:"):
                dados = json.loads(linha[5:].strip())
                if isinstance(dados, dict) and "id" in dados:
                    return dados
        raise ErroMCP("SSE sem resposta")
    dados = r.json()
    if not isinstance(dados, dict):
        raise ErroMCP("resposta que não é um objeto JSON")
    return dados


class ClienteMCP:
    def __init__(self, url: str, token: str, *, timeout: float = 20.0):
        self.url = url
        self._token = token
        self._timeout = timeout
        self._sessao = ""
        self._id = 0

    def _cabecalhos(self) -> dict:
        cab = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": VERSAO}
        if self._token:
            cab["Authorization"] = f"Bearer {self._token}"
        if self._sessao:
            cab["Mcp-Session-Id"] = self._sessao
        return cab

    def _post(self, corpo: dict) -> dict | None:
        try:
            with httpx.Client(timeout=self._timeout, trust_env=False) as c:
                r = c.post(self.url, json=corpo, headers=self._cabecalhos())
        except httpx.HTTPError as exc:
            raise ErroMCP(f"sem conexão ({type(exc).__name__})") from None
        if r.status_code == 401:
            raise ErroMCP("token recusado (401)")
        if r.status_code >= 400:
            raise ErroMCP(f"HTTP {r.status_code}")
        if r.headers.get("mcp-session-id"):
            self._sessao = r.headers["mcp-session-id"]
        if "id" not in corpo:
            return None              # notificação: 202 sem corpo
        try:
            return _ler_resposta(r)
        except ValueError:
            raise ErroMCP("resposta que não é JSON") from None

    def _rpc(self, metodo: str, params: dict | None = None) -> dict:
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": metodo, "params": params or {}})
        if not resp or "error" in resp:
            raise ErroMCP(str((resp or {}).get("error", "sem resposta"))[:200])
        return resp.get("result", {})

    def iniciar(self) -> None:
        self._rpc("initialize", {"protocolVersion": VERSAO, "capabilities": {},
                                 "clientInfo": {"name": "vard", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def listar_ferramentas(self) -> list[dict]:
        return self._rpc("tools/list").get("tools", [])

    def chamar(self, nome: str, argumentos: dict) -> str:
        res = self._rpc("tools/call", {"name": nome, "arguments": argumentos})
        texto = "".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
        if res.get("isError"):
            raise ErroMCP(texto[:200] or "erro na ferramenta")
        return texto
