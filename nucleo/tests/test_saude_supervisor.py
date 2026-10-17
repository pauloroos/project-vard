"""A entrada uvicorn server:app também precisa provar a identidade ao supervisor."""
import os

from fastapi.testclient import TestClient


def test_entrada_do_script_expoe_saude_com_pid():
    from server import app

    resposta = TestClient(app, base_url="http://127.0.0.1").get("/saude")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["pid"] == os.getpid()
    assert isinstance(corpo["versao"], str) and corpo["versao"]
