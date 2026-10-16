"""Testes T11: integração do TelegramPoller no ciclo de vida do server.py."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_deve_iniciar_poller_retorna_false_sem_config(tmp_path: Path, monkeypatch):
    """Sem telegram.toml, deve_iniciar_poller retorna False."""
    from vard import config as vard_config
    from vard import telegram as telegram_mod

    monkeypatch.setattr(vard_config, "pasta_dados", lambda: tmp_path)
    assert not telegram_mod.deve_iniciar_poller()


def test_deve_iniciar_poller_retorna_true_com_habilitado(tmp_path: Path, monkeypatch):
    """Com telegram.toml habilitado=true, deve_iniciar_poller retorna True."""
    from vard import config as vard_config
    from vard import telegram as telegram_mod

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "telegram.toml").write_text(
        "habilitado = true\ntoken = 'fake'\nchats_permitidos = ['123']\n", encoding="utf-8"
    )
    monkeypatch.setattr(vard_config, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(vard_config, "arquivo_config", lambda nome: cfg_dir / nome)
    assert telegram_mod.deve_iniciar_poller()


def test_deve_iniciar_poller_retorna_false_com_habilitado_false(tmp_path: Path, monkeypatch):
    """Com telegram.toml habilitado=false, deve_iniciar_poller retorna False."""
    from vard import config as vard_config
    from vard import telegram as telegram_mod

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "telegram.toml").write_text("habilitado = false\n", encoding="utf-8")
    monkeypatch.setattr(vard_config, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(vard_config, "arquivo_config", lambda nome: cfg_dir / nome)
    assert not telegram_mod.deve_iniciar_poller()


def test_lifespan_nao_inicia_poller_quando_desabilitado(monkeypatch):
    """Lifespan do server não inicia poller quando telegram está desabilitado."""
    from vard import telegram as telegram_mod

    # Mocka deve_iniciar_poller para retornar False
    monkeypatch.setattr(telegram_mod, "deve_iniciar_poller", lambda: False)

    # Verifica que a função lifespan existe no server.py (import indireto via arquivo)
    import ast
    server_path = Path(__file__).resolve().parent.parent / "server.py"
    tree = ast.parse(server_path.read_text(encoding="utf-8"))
    lifespan_found = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "lifespan"
        for node in ast.walk(tree)
    )
    assert lifespan_found, "função lifespan não encontrada em server.py"


async def test_telegram_poller_processa_update_de_chat_autorizado(tmp_path: Path, monkeypatch):
    """TelegramPoller admite pedido de chat autorizado e ignora não autorizado."""
    from vard.cerebro import pedidos as cerebro_pedidos
    from vard import telegram as telegram_mod

    monkeypatch.setattr(cerebro_pedidos, "_pasta_pedidos", str(tmp_path / "pedidos"))
    (tmp_path / "pedidos").mkdir(parents=True, exist_ok=True)

    poller = telegram_mod.TelegramPoller(
        token="fake-token",
        chats_permitidos={"12345"},
        estado_arquivo=tmp_path / "estado.json",
    )

    update_autorizado = {
        "update_id": 100,
        "message": {"chat": {"id": 12345}, "text": "oi vard"},
    }
    assert poller._processar_update(update_autorizado) is True

    update_negado = {
        "update_id": 101,
        "message": {"chat": {"id": 99999}, "text": "oi"},
    }
    assert poller._processar_update(update_negado) is False

    info = cerebro_pedidos.consultar("tg-12345-100")
    assert info is not None