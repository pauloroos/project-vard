"""Testes de integração do cérebro próprio via FastAPI TestClient (D2 — conserto 0.9.2).

Cobre o fluxo completo POST /pedidos → processamento → GET /pedidos/{id},
usando executor falso injetado via configurar_executor. Estes testes FALHAM antes
do conserto porque:
1. POST /pedidos só chama admitir(); processar_fila nunca é disparada no server.
2. processar_fila passa Pedido(..., texto="") ao executor — perde o texto real.
3. Eventos do executor são jogados fora (lambda ev: None).
4. _executores nunca recebe a task — cancelar não interrompe execução.

NOTA: testes de SSE removidos nesta versão para evitar bloqueio no TestClient;
a prova HTTP real no relatório cobre SSE com servidor uvicorn de verdade.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vard.cerebro import pedidos
from vard.cerebro.contratos import EstadoPedido, EventoPedido, Origem, Pedido, TipoEvento


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


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient com lifespan real; executor falso configurado via monkeypatch
    para sobreviver à reconfiguração do lifespan."""
    import server as srv

    async def _executor_falso(ped: Pedido, emitir):
        # Verifica que o texto chegou (D2 item 2)
        assert ped.texto, f"executor recebeu texto vazio para {ped.pedido_id}"
        emitir(EventoPedido(
            pedido_id=ped.pedido_id,
            sessao_id=ped.sessao_id,
            seq=1,
            tipo=TipoEvento.ESTADO,
            dados={"estado": "executando"},
        ))
        await asyncio.sleep(0.01)
        info = pedidos.consultar(ped.pedido_id)
        if info:
            info.resposta = f"eco: {ped.texto}"
            info.estado = EstadoPedido.CONCLUIDO
            pedidos._gravar_info(info)
        emitir(EventoPedido(
            pedido_id=ped.pedido_id,
            sessao_id=ped.sessao_id,
            seq=2,
            tipo=TipoEvento.FIM,
            dados={"resposta": f"eco: {ped.texto}"},
        ))

    # Monkeypatcha a função que o lifespan usa como executor, assim mesmo
    # após o lifespan reconfigurar, ele aponta para nosso executor falso.
    monkeypatch.setattr(srv, "_executar_pedido_cerebro", _executor_falso)

    with TestClient(srv.app, base_url="http://127.0.0.1:4700") as client:
        yield client


def _esperar_estado(client: TestClient, pedido_id: str, alvo: str, timeout: float = 5.0) -> dict:
    """Polling simples até atingir o estado alvo ou timeout."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout:
        r = client.get(f"/pedidos/{pedido_id}")
        assert r.status_code == 200
        dados = r.json()
        if dados["estado"] == alvo:
            return dados
        time.sleep(0.05)
    r = client.get(f"/pedidos/{pedido_id}")
    return r.json()


class TestPostPedidosProcessaEAtingeConcluido:
    """POST /pedidos deve disparar processamento e atingir concluido com resposta."""

    def test_pedido_atinge_concluido_com_resposta(self, app_client: TestClient):
        r = app_client.post("/pedidos", json={
            "pedido_id": "p-int-1",
            "sessao_id": "s-int",
            "origem": "painel",
            "texto": "ola mundo",
        })
        assert r.status_code == 202

        dados = _esperar_estado(app_client, "p-int-1", "concluido")
        assert dados["estado"] == "concluido", f"esperado concluido, got {dados['estado']}"
        assert dados["resposta"] is not None
        assert "ola mundo" in dados["resposta"]

    def test_executor_recebe_texto_enviado(self, app_client: TestClient):
        """O executor falso asserts ped.texto != ''; se perder texto, o teste falha."""
        r = app_client.post("/pedidos", json={
            "pedido_id": "p-texto",
            "sessao_id": "s-texto",
            "origem": "voz",
            "texto": "pergunta importante",
        })
        assert r.status_code == 202

        dados = _esperar_estado(app_client, "p-texto", "concluido")
        assert dados["estado"] == "concluido"
        assert "pergunta importante" in (dados["resposta"] or "")


class TestFIFOMesmaSessao:
    """Dois pedidos na mesma sessão rodam em ordem."""

    def test_dois_pedidos_mesma_sessao_fifo(self, app_client: TestClient):
        app_client.post("/pedidos", json={
            "pedido_id": "fifo-1", "sessao_id": "s-fifo",
            "origem": "painel", "texto": "primeiro",
        })
        app_client.post("/pedidos", json={
            "pedido_id": "fifo-2", "sessao_id": "s-fifo",
            "origem": "painel", "texto": "segundo",
        })

        d1 = _esperar_estado(app_client, "fifo-1", "concluido")
        d2 = _esperar_estado(app_client, "fifo-2", "concluido")
        assert d1["estado"] == "concluido"
        assert d2["estado"] == "concluido"


class TestCancelarDuranteExecucao:
    """Cancelar durante execução deve interromper o pedido."""

    def test_cancelar_interrompe_execucao(self, app_client: TestClient):
        # Configura executor lento para dar tempo de cancelar
        async def _executor_lento(ped: Pedido, emitir):
            await asyncio.sleep(10)  # longo o suficiente para cancelar
            info = pedidos.consultar(ped.pedido_id)
            if info:
                info.estado = EstadoPedido.CONCLUIDO
                pedidos._gravar_info(info)

        pedidos.configurar_executor(_executor_lento)

        r = app_client.post("/pedidos", json={
            "pedido_id": "p-cancel",
            "sessao_id": "s-cancel",
            "origem": "painel",
            "texto": "vai ser cancelado",
        })
        assert r.status_code == 202

        # Espera entrar em execução
        dados = _esperar_estado(app_client, "p-cancel", "executando", timeout=5.0)
        assert dados["estado"] == "executando", f"esperado executando, got {dados['estado']}"

        # Cancela
        rc = app_client.post("/pedidos/p-cancel/cancelar")
        assert rc.status_code == 200
        assert rc.json()["estado"] == "cancelado"

        # Confirma que não voltou a executar
        time.sleep(0.2)
        rf = app_client.get("/pedidos/p-cancel")
        assert rf.json()["estado"] == "cancelado"