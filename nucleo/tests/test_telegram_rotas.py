"""Testes dos endpoints HTTP /telegram/descobrir_chat e /telegram/testar.

Usa Bot API falsa (mesmo padrão de test_telegram.py). Token nunca aparece
em resposta, log ou erro.
"""
from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import Any

import pytest
import httpx
from httpx import Response


@pytest.fixture(autouse=True)
def _isolar_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cada teste usa pasta temporária de config."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    yield


class BotAPIFalsaTelegram:
    """Servidor HTTP mínimo que simula a Bot API do Telegram para testes de rotas."""

    def __init__(self) -> None:
        self._updates: list[dict] = []
        self._sent_messages: list[dict] = []
        self._falhar_send = False

    def adicionar_update(self, update: dict) -> None:
        self._updates.append(update)

    def set_falhar_send(self, valor: bool) -> None:
        self._falhar_send = valor

    @property
    def mensagens_enviadas(self) -> list[dict]:
        return list(self._sent_messages)

    async def handler(self, request: httpx.Request) -> Response:
        path = request.url.path
        if path.endswith("/getUpdates"):
            params = dict(request.url.params)
            offset = params.get("offset")
            off = int(offset) if offset else 0
            results = [u for u in self._updates if u.get("update_id", 0) >= off]
            return Response(200, json={"ok": True, "result": results})

        if path.endswith("/sendMessage"):
            if self._falhar_send:
                return Response(500, json={"ok": False, "description": "send failed"})
            try:
                body = json.loads(request.content.decode())
            except (ValueError, UnicodeDecodeError):
                body = {}
            self._sent_messages.append(body)
            return Response(200, json={"ok": True, "result": {"message_id": len(self._sent_messages)}})

        return Response(404, json={"ok": False, "description": "not found"})


@pytest.fixture()
async def bot_falso_rotas():
    """Sobe um servidor Bot API falso e devolve a instância controlável."""
    api = BotAPIFalsaTelegram()

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode()
        body_parts = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
        raw_body = b"".join(body_parts)
        url = httpx.URL(f"http://127.0.0.1{path}?{query_string}")
        req = httpx.Request(method, url, content=raw_body)
        resp = await api.handler(req)
        await send({
            "type": "http.response.start",
            "status": resp.status_code,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": resp.content,
        })

    import uvicorn
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        await asyncio.sleep(0.3)
        yield api, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            sock.close()


async def test_descobrir_chat_retorna_chat_id(bot_falso_rotas, tmp_path):
    """GET /telegram/descobrir_chat retorna o chat_id do último /start pendente."""
    from vard import config as cfg_mod
    import tomli_w

    api, base_url = bot_falso_rotas

    # Configura telegram.toml com token
    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": True,
        "token": "TOKEN_FALSO_ROTA",
        "chats_permitidos": [],
        "base_url": base_url,
    }), encoding="utf-8")

    # Adiciona update de /start
    api.adicionar_update({
        "update_id": 100,
        "message": {
            "message_id": 1,
            "chat": {"id": 555666777, "type": "private"},
            "text": "/start",
        },
    })

    # Importa server e chama endpoint diretamente
    import server
    resposta = await server.telegram_descobrir_chat()
    assert resposta.get("ok") is True
    assert str(resposta.get("chat_id")) == "555666777"
    # Token não aparece na resposta
    assert "TOKEN_FALSO_ROTA" not in json.dumps(resposta)


async def test_descobrir_chat_sem_updates(bot_falso_rotas):
    """GET /telegram/descobrir_chat sem updates pendentes retorna ok=false."""
    from vard import config as cfg_mod
    import tomli_w

    _, base_url = bot_falso_rotas

    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": True,
        "token": "TOKEN_FALSO_VAZIO",
        "chats_permitidos": [],
        "base_url": base_url,
    }), encoding="utf-8")

    import server
    resposta = await server.telegram_descobrir_chat()
    assert resposta.get("ok") is False


async def test_testar_envia_mensagem(bot_falso_rotas):
    """POST /telegram/testar envia mensagem de teste ao chat configurado."""
    from vard import config as cfg_mod
    import tomli_w

    api, base_url = bot_falso_rotas

    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": True,
        "token": "TOKEN_FALSO_TESTE",
        "chats_permitidos": ["111222333"],
        "base_url": base_url,
    }), encoding="utf-8")

    import server
    resposta = await server.telegram_testar()
    assert resposta.get("ok") is True
    assert len(api.mensagens_enviadas) >= 1
    msg = api.mensagens_enviadas[0]
    assert str(msg.get("chat_id")) == "111222333"
    # Token não aparece na resposta
    assert "TOKEN_FALSO_TESTE" not in json.dumps(resposta)


async def test_testar_sem_chat_configurado(bot_falso_rotas):
    """POST /telegram/testar sem chat configurado retorna erro claro."""
    from vard import config as cfg_mod
    import tomli_w

    _, base_url = bot_falso_rotas

    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": True,
        "token": "TOKEN_FALSO_SEM_CHAT",
        "chats_permitidos": [],
        "base_url": base_url,
    }), encoding="utf-8")

    import server
    resposta = await server.telegram_testar()
    assert resposta.get("ok") is False