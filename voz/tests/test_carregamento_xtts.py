"""Carregamento condicional do motor XTTS (T5b) e serviço de pé sem ele (D12).

- Sem XTTS disponível, um motor vazio ocupa o lugar: /saude e /vozes respondem (antes, motor=None
  fazia /saude dar 500 e o app nem abria).
- O XTTS é detectado mesmo sem o núcleo importável (o serviço de voz roda no próprio ambiente).
- Falha ao instanciar o Motor é capturada e logada.
"""
from __future__ import annotations

import builtins
import logging

import pytest
from fastapi.testclient import TestClient

from vard_voz import servidor


@pytest.fixture
def sem_motores_opcionais():
    return dict(motor_kokoro=None, motor_edge=None, motor_piper=None, carregar_em_thread=False)


def test_saude_responde_sem_xtts(monkeypatch, sem_motores_opcionais):
    monkeypatch.setattr(servidor, "_xtts_disponivel", lambda: False)
    app = servidor.criar_app(**sem_motores_opcionais)
    with TestClient(app) as c:
        r = c.get("/saude", headers={"host": "127.0.0.1"})
        assert r.status_code == 200
        assert r.json()["xtts"] is False and r.json()["pronta"] is False
        assert c.get("/vozes", headers={"host": "127.0.0.1"}).status_code in (200, 503)


def test_xtts_detectado_sem_o_nucleo(monkeypatch):
    """Sem o pacote `nucleo` importável, vale o pacote TTS (XTTS) presente neste ambiente."""
    import importlib.util

    original_import = builtins.__import__

    def import_sem_nucleo(nome, *args, **kwargs):
        if nome.startswith("nucleo"):
            raise ModuleNotFoundError("No module named 'nucleo'")
        return original_import(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_sem_nucleo)
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome: object() if nome == "TTS" else None)
    assert servidor._xtts_disponivel() is True
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome: None)
    assert servidor._xtts_disponivel() is False


def test_falha_ao_criar_motor_vira_motor_vazio_com_aviso(monkeypatch, caplog, sem_motores_opcionais):
    monkeypatch.setattr(servidor, "_xtts_disponivel", lambda: True)
    import vard_voz.motor as mod_motor

    def explode(*_a, **_k):
        raise RuntimeError("sem GPU")

    monkeypatch.setattr(mod_motor, "Motor", explode)
    with caplog.at_level(logging.WARNING, logger="vard_voz"):
        app = servidor.criar_app(**sem_motores_opcionais)
    assert "motor falhou ao iniciar" in caplog.text
    with TestClient(app) as c:
        assert c.get("/saude", headers={"host": "127.0.0.1"}).status_code == 200
