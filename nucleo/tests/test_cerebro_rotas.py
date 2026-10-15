"""Testes da T6: rotas do cérebro próprio (/pedidos) e integração lado a lado com /ask.

O cérebro próprio só atende quando explicitamente escolhido (flag de teste);
/ask continua devolvendo {resposta} via OpenJarvis como padrão.
"""
from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import server
from vard.cerebro import contratos, pedidos, sessoes


@pytest.fixture(autouse=True)
def _limpa_pedidos(tmp_path):
    """Isola pedidos e sessões em pasta temporária para cada teste."""
    pedidos.definir_pasta(tmp_path / "pedidos")
    yield
    pedidos.limpar_tudo()


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    server.HISTORICO.clear()
    monkeypatch.setattr(server, "_reuniao_ativa", lambda: False)
    return TestClient(server.app, base_url="http://127.0.0.1:4700")


def _novo_pedido(texto: str = "oi", sessao_id: str | None = None, origem: str = "painel") -> contratos.Pedido:
    return contratos.Pedido(
        pedido_id=str(uuid.uuid4()),
        sessao_id=sessao_id or str(uuid.uuid4()),
        origem=contratos.Origem(origem),
        texto=texto,
    )


@respx.mock
def test_ask_sem_flag_continua_via_openjarvis(cliente, monkeypatch):
    """/ask sem escolha explícita do cérebro continua usando OpenJarvis (caminho padrão)."""
    rota = respx.post("http://127.0.0.1:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Resposta OJ."}}]})
    )
    r = cliente.post("/ask", json={"texto": "oi"})
    assert r.status_code == 200
    assert r.json()["resposta"] == "Resposta OJ."
    assert rota.called


def test_pedidos_admite_e_consulta(cliente):
    """POST /pedidos admite pedido e devolve 202; GET /pedidos/{id} consulta estado."""
    p = _novo_pedido("teste admissao")
    r = cliente.post("/pedidos", json={
        "pedido_id": p.pedido_id,
        "sessao_id": p.sessao_id,
        "origem": p.origem.value,
        "texto": p.texto,
    })
    assert r.status_code == 202
    corpo = r.json()
    assert corpo["pedido_id"] == p.pedido_id
    assert corpo["estado"] in ("na_fila", "executando", "concluido")

    r2 = cliente.get(f"/pedidos/{p.pedido_id}")
    assert r2.status_code == 200
    assert r2.json()["pedido_id"] == p.pedido_id


def test_pedidos_mesmo_id_reutiliza(cliente):
    """Mesmo pedido_id com mesmo corpo reutiliza; corpo diferente dá 409."""
    p = _novo_pedido("texto original")
    payload = {
        "pedido_id": p.pedido_id,
        "sessao_id": p.sessao_id,
        "origem": p.origem.value,
        "texto": p.texto,
    }
    r1 = cliente.post("/pedidos", json=payload)
    assert r1.status_code == 202

    # Mesmo ID + mesmo corpo → reutiliza
    r2 = cliente.post("/pedidos", json=payload)
    assert r2.status_code == 202

    # Mesmo ID + corpo diferente → conflito
    payload["texto"] = "texto diferente"
    r3 = cliente.post("/pedidos", json=payload)
    assert r3.status_code == 409


def test_pedidos_consulta_inexistente_404(cliente):
    """GET /pedidos/{id} devolve 404 para ID ausente."""
    r = cliente.get(f"/pedidos/{uuid.uuid4()}")
    assert r.status_code == 404


def test_pedidos_cancelar(cliente):
    """POST /pedidos/{id}/cancelar cancela pedido existente."""
    p = _novo_pedido("para cancelar")
    cliente.post("/pedidos", json={
        "pedido_id": p.pedido_id,
        "sessao_id": p.sessao_id,
        "origem": p.origem.value,
        "texto": p.texto,
    })
    r = cliente.post(f"/pedidos/{p.pedido_id}/cancelar")
    assert r.status_code == 200
    info = r.json()
    assert info["estado"] in ("cancelado", "concluido", "falhou")


def test_pedidos_cancelar_inexistente_404(cliente):
    """Cancelar pedido inexistente devolve 404."""
    r = cliente.post(f"/pedidos/{uuid.uuid4()}/cancelar")
    assert r.status_code == 404


def test_pedidos_lista_filtra_por_sessao(cliente):
    """GET /pedidos lista pedidos; filtro por sessao_id funciona."""
    s1 = str(uuid.uuid4())
    s2 = str(uuid.uuid4())
    for sessao in (s1, s1, s2):
        p = _novo_pedido("msg", sessao_id=sessao)
        cliente.post("/pedidos", json={
            "pedido_id": p.pedido_id,
            "sessao_id": p.sessao_id,
            "origem": p.origem.value,
            "texto": p.texto,
        })

    r = cliente.get("/pedidos", params={"sessao_id": s1})
    assert r.status_code == 200
    itens = r.json().get("pedidos", [])
    assert len(itens) >= 2
    assert all(i["sessao_id"] == s1 for i in itens)


def test_status_inclui_cerebro(cliente, monkeypatch, tmp_path):
    """/status informa campo 'cerebro' sem exigir serviços reais."""
    import respx, httpx

    monkeypatch.setattr(server.modo, "ARQUIVO_ESTADO", tmp_path / "nao-existe.json")
    monkeypatch.setattr(server, "_tarefas_abertas", lambda: 0)
    with respx.mock:
        respx.get("http://127.0.0.1:8000/health").mock(side_effect=httpx.ConnectError("x"))
        respx.get("http://127.0.0.1:1234/v1/models").mock(side_effect=httpx.ConnectError("x"))
        respx.get("http://127.0.0.1:4720/status").mock(side_effect=httpx.ConnectError("x"))
        r = cliente.get("/status")
    assert r.status_code == 200
    corpo = r.json()
    assert "cerebro" in corpo
    assert isinstance(corpo["cerebro"], dict)