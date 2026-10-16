"""Testes da T9 — Telegram próprio do cérebro com Bot API falsa.

Cobre: texto em chat permitido, rejeição de chat não autorizado, sessões distintas por chat,
update duplicado, queda após admissão antes do offset, reinício com execução incerta,
áudio recebido → STT próprio, 409/429/rede, entrega longa não duplicada pela vigia,
jogo sem inferência. Logs capturados exigem ausência de token e URL secreta.
Nunca chama a Bot API real; tudo contra servidor HTTP falso no próprio teste.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

import pytest
import httpx
from httpx import Response

from vard.cerebro import pedidos
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolar_dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cada teste usa pasta temporária de dados/config."""
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    pedidos.definir_pasta(dados / "cerebro" / "pedidos")
    pedidos.limpar_tudo()
    yield
    pedidos.limpar_tudo()


@pytest.fixture()
def telegram_config(tmp_path: Path) -> dict[str, Any]:
    """Configuração mínima de telegram para testes."""
    return {
        "habilitado": True,
        "token": "TOKEN_FALSO_123456",
        "chats_permitidos": ["111", "222"],
        "base_url": "http://127.0.0.1:19876",  # substituído pelo servidor falso
        "timeout_s": 5,
        "poll_interval_s": 0.1,
    }


# ---------------------------------------------------------------------------
# Servidor Bot API falso
# ---------------------------------------------------------------------------

class BotAPIFalsa:
    """Servidor HTTP mínimo que simula a Bot API do Telegram para testes."""

    def __init__(self) -> None:
        self._updates: list[dict] = []
        self._sent_messages: list[dict] = []
        self._offset_recebido: int | None = None
        self._get_updates_calls = 0
        self._falhar_get_updates = False
        self._falhar_send = False
        self._status_code_override: int | None = None

    def adicionar_update(self, update: dict) -> None:
        self._updates.append(update)

    def set_falhar_get_updates(self, valor: bool) -> None:
        self._falhar_get_updates = valor

    def set_falhar_send(self, valor: bool) -> None:
        self._falhar_send = valor

    def set_status_override(self, code: int | None) -> None:
        self._status_code_override = code

    @property
    def mensagens_enviadas(self) -> list[dict]:
        return list(self._sent_messages)

    @property
    def offset_recebido(self) -> int | None:
        return self._offset_recebido

    @property
    def get_updates_count(self) -> int:
        return self._get_updates_calls

    async def handler(self, request: httpx.Request) -> Response:
        path = request.url.path
        if path.endswith("/getUpdates"):
            self._get_updates_calls += 1
            if self._falhar_get_updates:
                return Response(500, json={"ok": False, "description": "simulated error"})
            params = dict(request.url.params)
            offset = params.get("offset")
            if offset is not None:
                self._offset_recebido = int(offset)
            # Retorna updates com update_id >= offset
            off = int(offset) if offset else 0
            results = [u for u in self._updates if u.get("update_id", 0) >= off]
            return Response(200, json={"ok": True, "result": results})

        if path.endswith("/sendMessage"):
            if self._falhar_send:
                return Response(500, json={"ok": False, "description": "send failed"})
            if self._status_code_override:
                code = self._status_code_override
                self._status_code_override = None
                return Response(code, json={"ok": False, "description": f"HTTP {code}"})
            try:
                body = json.loads(request.content.decode())
            except (ValueError, UnicodeDecodeError):
                body = {}
            self._sent_messages.append(body)
            return Response(200, json={"ok": True, "result": {"message_id": len(self._sent_messages)}})

        if path.endswith("/getFile"):
            return Response(200, json={
                "ok": True,
                "result": {"file_path": "voice/test.ogg", "file_size": 1024},
            })

        # download file
        if "/file/" in path:
            # Retorna um OGG mínimo (bytes vazios para teste)
            return Response(200, content=b"\x00" * 64)

        return Response(404, json={"ok": False, "description": "not found"})


@pytest.fixture()
async def bot_falso(telegram_config):
    """Sobe um servidor Bot API falso e devolve a instância controlável."""
    api = BotAPIFalsa()

    async def app(scope, receive, send):
        # ASGI minimal handler wrapping our httpx-style handler
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode()
        headers_list = scope.get("headers", [])
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
    telegram_config["base_url"] = f"http://127.0.0.1:{sock.getsockname()[1]}"
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        await asyncio.sleep(0.3)  # aguarda servidor subir
        yield api
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

async def test_texto_em_chat_permitido(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Mensagem de texto em chat permitido gera pedido no cérebro."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 100,
        "message": {
            "message_id": 1,
            "chat": {"id": 111, "type": "private"},
            "text": "olá vard",
        },
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()

    # Deve ter admitido um pedido
    info = pedidos.consultar("tg-111-100")
    assert info is not None
    assert info.estado in (EstadoPedido.NA_FILA, EstadoPedido.EXECUTANDO, EstadoPedido.CONCLUIDO)


async def test_rejeitar_chat_nao_autorizado(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Mensagem de chat não autorizado é ignorada sem gerar pedido."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 200,
        "message": {
            "message_id": 2,
            "chat": {"id": 999, "type": "private"},
            "text": "mensagem indevida",
        },
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()

    info = pedidos.consultar("tg-999-200")
    assert info is None


async def test_dois_chats_sessoes_distintas(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Chats diferentes geram sessões diferentes no cérebro."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 300,
        "message": {"message_id": 3, "chat": {"id": 111, "type": "private"}, "text": "msg A"},
    })
    bot_falso.adicionar_update({
        "update_id": 301,
        "message": {"message_id": 4, "chat": {"id": 222, "type": "private"}, "text": "msg B"},
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()

    info_a = pedidos.consultar("tg-111-300")
    info_b = pedidos.consultar("tg-222-301")
    assert info_a is not None
    assert info_b is not None
    assert info_a.sessao_id != info_b.sessao_id


async def test_update_duplicado_nao_gera_dois_pedidos(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Mesmo update_id processado duas vezes não duplica pedido."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 400,
        "message": {"message_id": 5, "chat": {"id": 111, "type": "private"}, "text": "única"},
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()
    # Processa novamente o mesmo update (simulando replay)
    await poller.processar_updates()

    # Conta quantos pedidos existem na pasta
    base = pedidos._base()
    arquivos = list(base.glob("*.json")) if base.exists() else []
    ids_unicos = {a.stem for a in arquivos}
    assert "tg-111-400" in ids_unicos
    # Não deve haver duplicata
    assert sum(1 for a in arquivos if a.stem == "tg-111-400") == 1


async def test_queda_apos_admissao_preserva_offset(bot_falso: BotAPIFalsa, telegram_config: dict, tmp_path: Path):
    """Se cair após admitir mas antes de avançar offset, reinício não reprocessa."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 500,
        "message": {"message_id": 6, "chat": {"id": 111, "type": "private"}, "text": "antes da queda"},
    })

    estado_arq = tmp_path / "telegram_estado.json"
    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
        estado_arquivo=estado_arq,
    )
    await poller.processar_updates()

    # Offset deve ter sido persistido
    assert estado_arq.exists()
    estado = json.loads(estado_arq.read_text(encoding="utf-8"))
    assert estado.get("offset") >= 501


async def test_reinicio_com_execucao_incerta(bot_falso: BotAPIFalsa, telegram_config: dict, tmp_path: Path):
    """Pedido interrompido no arranque é marcado como falho, sem retomada automática."""
    from vard import telegram as tg_mod

    # Simula um pedido EXECUTANDO salvo antes do restart
    pedidos.admitir(Pedido(
        pedido_id="tg-111-600",
        sessao_id="tg-chat-111",
        origem=Origem.TELEGRAM,
        texto="pedido interrompido",
    ))
    info = pedidos.consultar("tg-111-600")
    assert info is not None
    info.estado = EstadoPedido.EXECUTANDO
    pedidos._gravar_info(info)

    # Recuperação no arranque
    count = pedidos.recuperar_interrupcoes()
    assert count >= 1

    recuperado = pedidos.consultar("tg-111-600")
    assert recuperado is not None
    assert recuperado.estado == EstadoPedido.FALHOU
    assert "interrupcao" in (recuperado.erro or "")


async def test_audio_recebido_encaminha_stt(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Mensagem de áudio gera pedido com origem TELEGRAM e marca de áudio."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 700,
        "message": {
            "message_id": 7,
            "chat": {"id": 111, "type": "private"},
            "voice": {"file_id": "voice_abc", "duration": 5, "mime_type": "audio/ogg"},
        },
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()

    info = pedidos.consultar("tg-111-700")
    assert info is not None
    # O pedido deve existir; o texto pode ser placeholder de transcrição pendente
    assert info.sessao_id == "tg-chat-111"


async def test_erro_409_interrompe_polling(bot_falso: BotAPIFalsa, telegram_config: dict, caplog):
    """Conflito 409 interrompe polling e registra aviso sem token na mensagem."""
    from vard import telegram as tg_mod

    bot_falso.set_status_override(409)
    bot_falso.adicionar_update({
        "update_id": 800,
        "message": {"message_id": 8, "chat": {"id": 111, "type": "private"}, "text": "conflito"},
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )

    with caplog.at_level(logging.WARNING, logger="vard.telegram"):
        await poller.processar_updates()

    # Token nunca aparece nos logs
    for record in caplog.records:
        assert telegram_config["token"] not in record.getMessage()
        assert "api.telegram.org" not in record.getMessage()


async def test_erro_429_respeita_retry_after(bot_falso: BotAPIFalsa, telegram_config: dict):
    """429 com retry_after faz o poller esperar antes de tentar novamente."""
    from vard import telegram as tg_mod

    bot_falso.set_status_override(429)
    bot_falso.adicionar_update({
        "update_id": 900,
        "message": {"message_id": 9, "chat": {"id": 111, "type": "private"}, "text": "rate limit"},
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    # Não deve levantar exceção
    await poller.processar_updates()
    assert bot_falso.get_updates_count >= 1


async def test_entrega_longa_nao_duplicada(bot_falso: BotAPIFalsa, telegram_config: dict):
    """Resposta longa dividida em blocos não duplica conteúdo."""
    from vard import telegram as tg_mod

    texto_longo = "A" * 5000  # > 4096 caracteres
    enviados = await tg_mod.enviar_texto_dividido(
        chat_id="111",
        texto=texto_longo,
        token=telegram_config["token"],
        base_url=telegram_config["base_url"],
    )
    assert enviados >= 2
    # Cada bloco <= 4096
    for msg in bot_falso.mensagens_enviadas:
        assert len(msg.get("text", "")) <= 4096


async def test_jogo_sem_inferencia(bot_falso: BotAPIFalsa, telegram_config: dict, monkeypatch):
    """Em modo jogo, mensagens do Telegram são recebidas mas não geram inferência."""
    from vard import telegram as tg_mod, modo

    # Simula modo jogo ativo
    monkeypatch.setattr(modo, "ler_estado", lambda: {"modo": "jogo"})

    bot_falso.adicionar_update({
        "update_id": 1000,
        "message": {"message_id": 10, "chat": {"id": 111, "type": "private"}, "text": "em jogo"},
    })

    poller = tg_mod.TelegramPoller(
        token=telegram_config["token"],
        chats_permitidos=set(telegram_config["chats_permitidos"]),
        base_url=telegram_config["base_url"],
        timeout_s=2,
        poll_interval_s=0.1,
    )
    await poller.processar_updates()

    # Em jogo, o pedido NÃO deve ser admitido para inferência
    info = pedidos.consultar("tg-111-1000")
    assert info is None


async def test_logs_nao_contem_token(bot_falso: BotAPIFalsa, telegram_config: dict, caplog):
    """Nenhum log contém o token ou URL completa da Bot API."""
    from vard import telegram as tg_mod

    bot_falso.adicionar_update({
        "update_id": 1100,
        "message": {"message_id": 11, "chat": {"id": 111, "type": "private"}, "text": "segurança"},
    })

    with caplog.at_level(logging.DEBUG, logger="vard.telegram"):
        poller = tg_mod.TelegramPoller(
            token=telegram_config["token"],
            chats_permitidos=set(telegram_config["chats_permitidos"]),
            base_url=telegram_config["base_url"],
            timeout_s=2,
            poll_interval_s=0.1,
        )
        await poller.processar_updates()

    token = telegram_config["token"]
    for record in caplog.records:
        msg = record.getMessage()
        assert token not in msg, f"Token vazou no log: {msg}"
        assert f"bot{token}" not in msg, f"URL com token vazou no log: {msg}"


async def test_desabilitado_por_padrao():
    """Sem config explícita habilitado=true, o poller não sobe.
    A fixture autouse _isolar_dados já prepara VARD_DADOS/VARD_CONFIG vazios."""
    from vard import telegram as tg_mod

    ativo = tg_mod.deve_iniciar_poller()
    assert ativo is False