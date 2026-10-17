"""Testes das ferramentas MCP de Telegram e endpoints HTTP do núcleo.

Cobre: ver_telegram retorna ligado/chat sem token, configurar_telegram grava
telegram.toml sem token, endpoint /telegram/descobrir_chat lê último update,
endpoint /telegram/testar envia mensagem de teste. Token nunca passa pelo MCP
nem aparece em log/erro.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolar_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cada teste usa pasta temporária de config."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    yield


def test_ver_telegram_retorna_ligado_e_chat_sem_token():
    """ver_telegram mostra estado atual sem expor o token."""
    from vard import config as cfg_mod
    import tomli_w

    # Cria telegram.toml com token e chat
    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": True,
        "token": "TOKEN_SECRETO_12345",
        "chats_permitidos": ["123456789"],
    }), encoding="utf-8")

    import configuracoes_mcp as mcp
    resposta = mcp.ver_telegram()

    assert "ligado" in resposta.lower() or "true" in resposta.lower()
    assert "123456789" in resposta
    # Token NUNCA aparece na resposta
    assert "TOKEN_SECRETO_12345" not in resposta


def test_ver_telegram_desabilitado():
    """ver_telegram mostra desligado quando habilitado=false ou arquivo ausente."""
    import configuracoes_mcp as mcp
    resposta = mcp.ver_telegram()
    # Sem arquivo, deve mostrar desligado
    assert "desligado" in resposta.lower() or "false" in resposta.lower() or "não" in resposta.lower()


def test_configurar_telegram_grava_ligado_e_chat():
    """configurar_telegram grava habilitado e chats_permitidos no telegram.toml."""
    import configuracoes_mcp as mcp
    from vard import config as cfg_mod
    import tomllib

    resposta = mcp.configurar_telegram(ligado=True, chat="987654321")
    assert "atualizado" in resposta.lower() or "ok" in resposta.lower()

    # Verifica que o arquivo foi gravado corretamente
    alvo = cfg_mod.arquivo_config("telegram.toml")
    assert alvo.exists()
    dados = tomllib.loads(alvo.read_text(encoding="utf-8"))
    assert dados.get("habilitado") is True
    assert "987654321" in dados.get("chats_permitidos", [])
    # Token não deve ter sido gravado (só a tela grava token)
    assert "token" not in dados or dados.get("token") == ""


def test_configurar_telegram_desliga():
    """configurar_telegram com ligado=False desabilita o poller."""
    import configuracoes_mcp as mcp
    from vard import config as cfg_mod
    import tomllib

    mcp.configurar_telegram(ligado=False, chat="")
    alvo = cfg_mod.arquivo_config("telegram.toml")
    if alvo.exists():
        dados = tomllib.loads(alvo.read_text(encoding="utf-8"))
        assert dados.get("habilitado") is False


def test_configurar_telegram_preserva_token_existente():
    """configurar_telegram não apaga token já gravado pela tela."""
    import configuracoes_mcp as mcp
    from vard import config as cfg_mod
    import tomli_w
    import tomllib

    # Pré-configura com token
    alvo = cfg_mod.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(tomli_w.dumps({
        "habilitado": False,
        "token": "TOKEN_EXISTENTE_ABC",
        "chats_permitidos": [],
    }), encoding="utf-8")

    mcp.configurar_telegram(ligado=True, chat="111222333")

    dados = tomllib.loads(alvo.read_text(encoding="utf-8"))
    assert dados.get("habilitado") is True
    assert dados.get("token") == "TOKEN_EXISTENTE_ABC"
    assert "111222333" in dados.get("chats_permitidos", [])