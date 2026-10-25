"""/status e /saude rápidos (0.9.7): o widget sonda a saúde a cada 5 s e a aba Núcleo lê o /status.

No Windows, conectar numa porta fechada do 127.0.0.1 leva ~2 s (o SYN é repetido depois do RST).
Com o OpenJarvis desligado, isso fazia o /status levar o prazo inteiro da sonda.
"""
from __future__ import annotations

import socket
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import server
from vard import central


def _porta_fechada() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setattr(central, "ARQUIVO", tmp_path / "avisos.jsonl")
    monkeypatch.setattr(server, "_tarefas_abertas", lambda: 0)
    monkeypatch.setattr(server, "_ler_provedor_ativo", lambda: {})
    monkeypatch.setattr(server, "_supervisor_cli", None)
    monkeypatch.setattr(server.modo, "ARQUIVO_ESTADO", tmp_path / "nao-existe.json")
    return TestClient(server.app, base_url="http://127.0.0.1:4700")


def test_prazo_de_conexao_curto_no_loopback_e_maior_no_remoto():
    local = server._prazo_sonda("http://127.0.0.1:8000")
    assert local.connect is not None and local.connect <= 0.5
    assert server._prazo_sonda("http://localhost:1234").connect == local.connect
    remoto = server._prazo_sonda("http://192.0.2.10:1234")
    assert remoto.connect is not None and local.connect < remoto.connect <= 1.0
    assert local.read == remoto.read == 2   # a leitura de quem já conectou continua com o prazo antigo


def test_status_responde_rapido_com_servicos_desligados_no_loopback(cliente, monkeypatch):
    """OpenJarvis, LM Studio e reunião desligados (portas fechadas): /status bem abaixo dos 2 s antigos."""
    monkeypatch.setattr(server, "OPENJARVIS", f"http://127.0.0.1:{_porta_fechada()}")
    monkeypatch.setattr(server, "LMSTUDIO", f"http://127.0.0.1:{_porta_fechada()}")
    monkeypatch.setattr(server, "REUNIAO", f"http://127.0.0.1:{_porta_fechada()}")
    t0 = time.monotonic()
    r = cliente.get("/status")
    duracao = time.monotonic() - t0
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["openjarvis"] is False and corpo["lmstudio"] is False and corpo["reuniao"] == "ausente"
    assert duracao < 1.2, f"/status levou {duracao:.2f}s"


def test_saude_nao_depende_do_pool_de_threads():
    """/saude é assíncrona: responde no laço de eventos mesmo com as threads ocupadas por rotas síncronas lentas."""
    import inspect
    rota = next(r for r in server.app.routes if getattr(r, "path", None) == "/saude")
    assert inspect.iscoroutinefunction(rota.endpoint)


def test_saude_responde_ok(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200 and r.json()["ok"] is True
