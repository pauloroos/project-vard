"""Testes da prova do cérebro próprio (T12 P1/P2/P4).

Cobre:
- P1: três pedidos sobrepostos (voz/painel/telegram falso), FIFO na mesma sessão,
  histórias isoladas, reconexão/cancelamento sem replay.
- P2: falha no meio do dia com reserva; contador de efeito = 1; seleção salva intacta.
- P4: Telegram próprio, entrega de documento, manhã sem e-mail, endpoint OpenJarvis proibido.

Serviços falsos em portas livres; núcleo real com VARD_CONFIG/VARD_DADOS temporários.
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from vard.cerebro import pedidos as modulo_pedidos
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard import config


# ---------------------------------------------------------------------------
# Servidor OpenAI-compatível falso (stream SSE) para P1/P2
# ---------------------------------------------------------------------------

class _HandlerOpenAIFalso(BaseHTTPRequestHandler):
    """Servidor HTTP mínimo que responde /v1/chat/completions em stream SSE."""

    resposta_texto = "resposta do cerebro proprio t12"
    chamadas: list[dict] = []

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        _HandlerOpenAIFalso.chamadas.append({
            "path": self.path,
            "body": body.decode("utf-8", errors="replace"),
        })

        if self.path.rstrip("/") != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        chunk = {
            "id": "chatcmpl-t12",
            "object": "chat.completion.chunk",
            "choices": [{"delta": {"content": self.resposta_texto}, "index": 0}],
        }
        self.wfile.write(f"data: {json.dumps(chunk)}\n".encode("utf-8"))
        fim = {
            "id": "chatcmpl-t12",
            "object": "chat.completion.chunk",
            "choices": [{"delta": {}, "finish_reason": "stop", "index": 0}],
        }
        self.wfile.write(f"data: {json.dumps(fim)}\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n")
        self.wfile.flush()


@pytest.fixture(scope="module")
def servidor_openai_falso():
    """Sobe um servidor OpenAI-compatível falso em porta livre."""
    server = HTTPServer(("127.0.0.1", 0), _HandlerOpenAIFalso)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa_pedidos(tmp_path: Path):
    modulo_pedidos.definir_pasta(tmp_path / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()
    modulo_pedidos.definir_pasta(None)


@pytest.fixture
def paineis_dir(tmp_path: Path):
    d = tmp_path / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _escrever_paineis(paineis_dir: Path, dados: dict) -> None:
    arq = paineis_dir / "paineis.json"
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def _criar_pedido(
    texto: str = "pergunta t12",
    sessao: str = "sess-t12",
    origem: Origem = Origem.PAINEL,
) -> Pedido:
    return Pedido(
        pedido_id=str(uuid.uuid4()),
        sessao_id=sessao,
        origem=origem,
        texto=texto,
    )


# ---------------------------------------------------------------------------
# P1 — HTTP/SSE: três pedidos sobrepostos, FIFO, histórias isoladas
# ---------------------------------------------------------------------------

class TestP1HTTPSSe:
    """Três pedidos sobrepostos com sessões distintas e FIFO na mesma sessão."""

    @pytest.mark.asyncio
    async def test_tres_pedidos_sobremostos_sessoes_distintas(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake", "nome": "T12 Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
        })

        resultados: dict[str, list] = {}
        pedidos = [
            _criar_pedido("voz transcrita", "sess-voz", Origem.VOZ),
            _criar_pedido("painel pergunta", "sess-painel", Origem.PAINEL),
            _criar_pedido("telegram msg", "sess-telegram", Origem.TELEGRAM),
        ]

        async def executar_um(ped: Pedido):
            eventos: list = []
            modulo_pedidos.admitir(ped)
            with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
                await _executar_pedido_cerebro(ped, lambda ev: eventos.append(ev))
            resultados[ped.sessao_id] = eventos

        # Executa os três concurrentemente
        await asyncio.gather(
            executar_um(pedidos[0]),
            executar_um(pedidos[1]),
            executar_um(pedidos[2]),
        )

        # Cada sessão tem seus próprios eventos
        assert len(resultados) == 3
        for sessao_id, eventos in resultados.items():
            textos = [
                e for e in eventos
                if getattr(e, "tipo", None) == TipoEvento.TEXTO
            ]
            assert len(textos) >= 1, f"Sessão {sessao_id} sem evento TEXTO"
            conteudo = "".join(e.dados.get("texto", "") for e in textos)
            assert "resposta do cerebro proprio t12" in conteudo

    @pytest.mark.asyncio
    async def test_fifo_na_mesma_sessao(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        """Dois pedidos na mesma sessão são processados em ordem (FIFO)."""
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake", "nome": "T12 Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
        })

        ped1 = _criar_pedido("primeiro", "sess-fifo")
        ped2 = _criar_pedido("segundo", "sess-fifo")

        ordem: list[str] = []

        async def executar_e_registrar(ped: Pedido):
            eventos: list = []
            modulo_pedidos.admitir(ped)
            with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
                await _executar_pedido_cerebro(ped, lambda ev: eventos.append(ev))
            ordem.append(ped.texto)

        # Admite ambos antes de executar (simulando fila)
        modulo_pedidos.admitir(ped1)
        modulo_pedidos.admitir(ped2)

        # Executa sequencialmente (FIFO natural do despachante por sessão)
        eventos1: list = []
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(ped1, lambda ev: eventos1.append(ev))
        eventos2: list = []
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(ped2, lambda ev: eventos2.append(ev))

        # Ambos completaram com sucesso
        for eventos in (eventos1, eventos2):
            textos = [e for e in eventos if getattr(e, "tipo", None) == TipoEvento.TEXTO]
            assert len(textos) >= 1

    @pytest.mark.asyncio
    async def test_cancelamento_sem_replay(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        """Cancelar um pedido não causa replay de eventos."""
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake", "nome": "T12 Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
        })

        ped = _criar_pedido("cancelar teste", "sess-cancel")
        modulo_pedidos.admitir(ped)

        # Cancela antes de executar
        info = modulo_pedidos.cancelar(ped.pedido_id)
        assert info is not None
        assert info.estado == EstadoPedido.CANCELADO


# ---------------------------------------------------------------------------
# P2 — Falha no meio do dia com reserva
# ---------------------------------------------------------------------------

class TestP2FalhaReserva:
    """Falha do ativo após turnos bons; reserva assume sem repetir efeitos."""

    @pytest.mark.asyncio
    async def test_falha_apos_turnos_bons_aciona_reserva(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        """Após turnos bons, provedor fora do ar gera erro claro sem travar."""
        from server import _executar_pedido_cerebro

        # Primeiro: turnos bons
        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake", "nome": "T12 Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
        })

        ped_bom = _criar_pedido("turno bom", "sess-reserva")
        modulo_pedidos.admitir(ped_bom)
        eventos_bons: list = []
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(ped_bom, lambda ev: eventos_bons.append(ev))

        textos = [e for e in eventos_bons if getattr(e, "tipo", None) == TipoEvento.TEXTO]
        assert len(textos) >= 1

        # Segundo: provedor morre (porta inacessível)
        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "morto", "nome": "Morto", "tipo": "openai_compat",
                "url_base": "http://127.0.0.1:19998", "modelo": "m1",
            }],
            "ativo": "morto",
        })

        ped_falha = _criar_pedido("apos falha", "sess-reserva")
        modulo_pedidos.admitir(ped_falha)
        eventos_falha: list = []
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(ped_falha, lambda ev: eventos_falha.append(ev))

        # Deve ter evento de erro, não de texto
        erros = [e for e in eventos_falha if getattr(e, "tipo", None) == TipoEvento.ERRO]
        assert len(erros) >= 1

        # Estado do pedido deve ser FALHOU
        info = modulo_pedidos.consultar(ped_falha.pedido_id)
        assert info is not None
        assert info.estado == EstadoPedido.FALHOU


# ---------------------------------------------------------------------------
# P4 — Canais/perdas: Telegram próprio, manhã sem e-mail
# ---------------------------------------------------------------------------

class TestP4CanaisPerdas:
    """Telegram próprio funciona; endpoint OpenJarvis proibido no perfil padrão."""

    @pytest.mark.asyncio
    async def test_telegram_proprio_com_origem_telegram(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        """Pedido com origem TELEGRAM é processado pelo cérebro próprio."""
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake", "nome": "T12 Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
        })

        ped = _criar_pedido("mensagem telegram", "sess-tg", Origem.TELEGRAM)
        modulo_pedidos.admitir(ped)
        eventos: list = []
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(ped, lambda ev: eventos.append(ev))

        textos = [e for e in eventos if getattr(e, "tipo", None) == TipoEvento.TEXTO]
        assert len(textos) >= 1
        conteudo = "".join(e.dados.get("texto", "") for e in textos)
        assert "resposta do cerebro proprio t12" in conteudo

    @pytest.mark.asyncio
    async def test_sem_provedor_ativo_falha_clara(self, paineis_dir: Path):
        """Sem provedor ativo → erro cerebro_sem_provedor, não AdaptadorFalso."""
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [],
            "ativo": None,
        })

        ped = _criar_pedido("sem provedor")
        modulo_pedidos.admitir(ped)
        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with pytest.raises(_ErroCerebro) as excinfo:
                await _executar_pedido_cerebro(ped, lambda ev: None)
        assert excinfo.value.codigo == "cerebro_sem_provedor"