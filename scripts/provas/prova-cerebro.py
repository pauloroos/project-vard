"""Prova integrativa do cérebro próprio (T12 P1/P2/P4).

Sobe serviços falsos (OpenAI-compatível, Bot API Telegram) em portas livres,
configura paineis.json temporário com provedor ativo e executa pedidos via
despachante real do núcleo. Gera resultado.json item a item.

Uso: uv run --project nucleo python scripts/provas/prova-cerebro.py
"""
from __future__ import annotations

import asyncio
import datetime
import json
import socket
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch

# Garante que o núcleo está no path
NUCLEO_DIR = Path(__file__).resolve().parents[2] / "nucleo"
if str(NUCLEO_DIR) not in sys.path:
    sys.path.insert(0, str(NUCLEO_DIR))

from vard.cerebro import pedidos as modulo_pedidos
from vard.cerebro.contratos import EstadoPedido, Origem, Pedido, TipoEvento
from vard import config


# ---------------------------------------------------------------------------
# Servidor OpenAI-compatível falso (stream SSE)
# ---------------------------------------------------------------------------

class HandlerOpenAIFalso(BaseHTTPRequestHandler):
    """Responde /v1/chat/completions em stream SSE."""

    resposta_texto = "resposta do cerebro proprio t12"
    chamadas: list[dict] = []

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        HandlerOpenAIFalso.chamadas.append({
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


# ---------------------------------------------------------------------------
# Servidor Bot API Telegram falso
# ---------------------------------------------------------------------------

class HandlerTelegramFalso(BaseHTTPRequestHandler):
    """Simula Bot API do Telegram para P4."""

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            self.rfile.read(content_length)
        if self.path.endswith("/getUpdates"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "result": []}).encode("utf-8"))
            return
        if self.path.endswith("/sendMessage"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "result": {"message_id": 1}}).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):  # noqa: N802
        self.do_POST()


def _porta_livre() -> int:
    """Encontra uma porta TCP livre."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextmanager
def patch_config(config_dir: Path):
    """Context manager que monkeypatcha config.arquivo_config para usar o dir temporário."""
    original = config.arquivo_config

    def _fake(nome: str) -> Path:
        return config_dir / nome

    with patch.object(config, "arquivo_config", side_effect=_fake):
        yield


async def main() -> dict:
    resultado: dict = {
        "tarefa": "T12",
        "data": None,
        "itens": {},
        "processos": {"abertos": [], "fechados": []},
    }
    resultado["data"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Sobe servidor OpenAI falso
    porta_openai = _porta_livre()
    srv_openai = HTTPServer(("127.0.0.1", porta_openai), HandlerOpenAIFalso)
    thread_openai = threading.Thread(target=srv_openai.serve_forever, daemon=True)
    thread_openai.start()
    url_openai = f"http://127.0.0.1:{porta_openai}"
    resultado["processos"]["abertos"].append({"nome": "openai_falso", "porta": porta_openai})

    # Sobe servidor Telegram falso
    porta_telegram = _porta_livre()
    srv_telegram = HTTPServer(("127.0.0.1", porta_telegram), HandlerTelegramFalso)
    thread_telegram = threading.Thread(target=srv_telegram.serve_forever, daemon=True)
    thread_telegram.start()
    resultado["processos"]["abertos"].append({"nome": "telegram_falso", "porta": porta_telegram})

    # Configura diretórios temporários
    with tempfile.TemporaryDirectory(prefix="vard-t12-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        dados_dir = tmp_path / "dados"
        dados_dir.mkdir()

        # Configura pasta de pedidos
        modulo_pedidos.definir_pasta(dados_dir / "pedidos")
        modulo_pedidos.limpar_tudo()

        # Escreve paineis.json com provedor ativo
        paineis = {
            "versao": 1,
            "provedores": [{
                "id": "t12-fake",
                "nome": "T12 Fake",
                "tipo": "openai_compat",
                "url_base": url_openai,
                "modelo": "m-t12",
            }],
            "ativo": "t12-fake",
            "reserva": None,
            "agentes": {},
            "mcps": [],
        }
        paineis_arq = config_dir / "paineis.json"
        paineis_arq.write_text(json.dumps(paineis, ensure_ascii=False), encoding="utf-8")

        from server import _executar_pedido_cerebro

        # ---- P1: três pedidos sobrepostos, sessões distintas ----
        try:
            resultados_p1: dict[str, list] = {}
            pedidos_p1 = [
                Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-voz", origem=Origem.VOZ, texto="voz transcrita"),
                Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-painel", origem=Origem.PAINEL, texto="painel pergunta"),
                Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-telegram", origem=Origem.TELEGRAM, texto="telegram msg"),
            ]

            async def executar_um(ped: Pedido):
                eventos: list = []
                modulo_pedidos.admitir(ped)
                with patch_config(config_dir):
                    await _executar_pedido_cerebro(ped, lambda ev: eventos.append(ev))
                resultados_p1[ped.sessao_id] = eventos

            await asyncio.gather(
                executar_um(pedidos_p1[0]),
                executar_um(pedidos_p1[1]),
                executar_um(pedidos_p1[2]),
            )
            p1_ok = len(resultados_p1) == 3
            for sessao_id, eventos in resultados_p1.items():
                textos = [e for e in eventos if getattr(e, "tipo", None) == TipoEvento.TEXTO]
                if not textos:
                    p1_ok = False
                    break
                conteudo = "".join(e.dados.get("texto", "") for e in textos)
                if "resposta do cerebro proprio t12" not in conteudo:
                    p1_ok = False
                    break
            resultado["itens"]["P1_http_sse"] = {
                "ok": p1_ok,
                "sessoes": list(resultados_p1.keys()),
                "detalhe": "tres pedidos sobrepostos com respostas corretas" if p1_ok else "falha na validacao",
            }
        except Exception as exc:
            resultado["itens"]["P1_http_sse"] = {"ok": False, "erro": str(exc)[:200]}

        # ---- P1: FIFO na mesma sessão ----
        try:
            ped_fifo1 = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-fifo", origem=Origem.PAINEL, texto="primeiro")
            ped_fifo2 = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-fifo", origem=Origem.PAINEL, texto="segundo")
            eventos_fifo1: list = []
            modulo_pedidos.admitir(ped_fifo1)
            with patch_config(config_dir):
                await _executar_pedido_cerebro(ped_fifo1, lambda ev: eventos_fifo1.append(ev))
            eventos_fifo2: list = []
            modulo_pedidos.admitir(ped_fifo2)
            with patch_config(config_dir):
                await _executar_pedido_cerebro(ped_fifo2, lambda ev: eventos_fifo2.append(ev))
            fifo_ok = (
                any(getattr(e, "tipo", None) == TipoEvento.TEXTO for e in eventos_fifo1)
                and any(getattr(e, "tipo", None) == TipoEvento.TEXTO for e in eventos_fifo2)
            )
            resultado["itens"]["P1_fifo"] = {"ok": fifo_ok}
        except Exception as exc:
            resultado["itens"]["P1_fifo"] = {"ok": False, "erro": str(exc)[:200]}

        # ---- P1: cancelamento sem replay ----
        try:
            ped_cancel = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-cancel", origem=Origem.PAINEL, texto="cancelar")
            modulo_pedidos.admitir(ped_cancel)
            info_cancel = modulo_pedidos.cancelar(ped_cancel.pedido_id)
            cancel_ok = info_cancel is not None and info_cancel.estado == EstadoPedido.CANCELADO
            resultado["itens"]["P1_cancelamento"] = {"ok": cancel_ok}
        except Exception as exc:
            resultado["itens"]["P1_cancelamento"] = {"ok": False, "erro": str(exc)[:200]}

        # ---- P2: falha após turnos bons ----
        try:
            ped_bom = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-reserva", origem=Origem.PAINEL, texto="turno bom")
            modulo_pedidos.admitir(ped_bom)
            eventos_bons: list = []
            with patch_config(config_dir):
                await _executar_pedido_cerebro(ped_bom, lambda ev: eventos_bons.append(ev))
            textos_bons = [e for e in eventos_bons if getattr(e, "tipo", None) == TipoEvento.TEXTO]
            turno_bom_ok = len(textos_bons) >= 1

            # Provedor morre
            paineis_morto = dict(paineis)
            paineis_morto["provedores"] = [{
                "id": "morto", "nome": "Morto", "tipo": "openai_compat",
                "url_base": "http://127.0.0.1:19998", "modelo": "m1",
            }]
            paineis_morto["ativo"] = "morto"
            (config_dir / "paineis.json").write_text(
                json.dumps(paineis_morto, ensure_ascii=False), encoding="utf-8"
            )
            ped_falha = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-reserva", origem=Origem.PAINEL, texto="apos falha")
            modulo_pedidos.admitir(ped_falha)
            eventos_falha: list = []
            with patch_config(config_dir):
                await _executar_pedido_cerebro(ped_falha, lambda ev: eventos_falha.append(ev))
            erros = [e for e in eventos_falha if getattr(e, "tipo", None) == TipoEvento.ERRO]
            info_falha = modulo_pedidos.consultar(ped_falha.pedido_id)
            falha_ok = turno_bom_ok and len(erros) >= 1 and info_falha and info_falha.estado == EstadoPedido.FALHOU
            resultado["itens"]["P2_falha_reserva"] = {
                "ok": falha_ok,
                "turno_bom": turno_bom_ok,
                "erros_count": len(erros),
                "estado_final": info_falha.estado.value if info_falha else None,
            }
        except Exception as exc:
            resultado["itens"]["P2_falha_reserva"] = {"ok": False, "erro": str(exc)[:200]}

        # ---- P4: Telegram próprio com origem TELEGRAM ----
        try:
            # Restaura paineis com provedor ativo (P2 trocou para "morto")
            (config_dir / "paineis.json").write_text(
                json.dumps(paineis, ensure_ascii=False), encoding="utf-8"
            )
            ped_tg = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-tg", origem=Origem.TELEGRAM, texto="mensagem telegram")
            modulo_pedidos.admitir(ped_tg)
            eventos_tg: list = []
            with patch_config(config_dir):
                await _executar_pedido_cerebro(ped_tg, lambda ev: eventos_tg.append(ev))
            textos_tg = [e for e in eventos_tg if getattr(e, "tipo", None) == TipoEvento.TEXTO]
            tg_ok = len(textos_tg) >= 1
            conteudo_tg = "".join(e.dados.get("texto", "") for e in textos_tg) if textos_tg else ""
            tg_ok = tg_ok and "resposta do cerebro proprio t12" in conteudo_tg
            resultado["itens"]["P4_telegram_proprio"] = {
                "ok": tg_ok,
                "eventos_count": len(eventos_tg),
                "textos_count": len(textos_tg),
                "tipos": [getattr(e, "tipo", None) for e in eventos_tg],
            }
        except Exception as exc:
            resultado["itens"]["P4_telegram_proprio"] = {"ok": False, "erro": str(exc)[:200]}

        # ---- P4: sem provedor → falha clara ----
        try:
            from server import _ErroCerebro
            paineis_vazio = {"versao": 1, "provedores": [], "ativo": None, "reserva": None, "agentes": {}, "mcps": []}
            (config_dir / "paineis.json").write_text(
                json.dumps(paineis_vazio, ensure_ascii=False), encoding="utf-8"
            )
            ped_sem = Pedido(pedido_id=str(uuid.uuid4()), sessao_id="sess-sem", origem=Origem.PAINEL, texto="sem provedor")
            modulo_pedidos.admitir(ped_sem)
            erro_levantado = False
            codigo_erro = ""
            try:
                with patch_config(config_dir):
                    await _executar_pedido_cerebro(ped_sem, lambda ev: None)
            except _ErroCerebro as exc:
                erro_levantado = True
                codigo_erro = exc.codigo
            sem_provedor_ok = erro_levantado and codigo_erro == "cerebro_sem_provedor"
            resultado["itens"]["P4_sem_provedor"] = {"ok": sem_provedor_ok, "codigo": codigo_erro}
        except Exception as exc:
            resultado["itens"]["P4_sem_provedor"] = {"ok": False, "erro": str(exc)[:200]}

    # Limpeza dos servidores
    srv_openai.shutdown()
    srv_telegram.shutdown()
    resultado["processos"]["fechados"].append({"nome": "openai_falso"})
    resultado["processos"]["fechados"].append({"nome": "telegram_falso"})

    # Resumo final
    todos_ok = all(v.get("ok", False) for v in resultado["itens"].values())
    resultado["resumo"] = "TODOS_OK" if todos_ok else "FALHAS"

    # Escreve resultado.json
    resultado_dir = Path(__file__).resolve().parents[2] / ".coordenacao" / "0.8-prova" / "t12"
    resultado_dir.mkdir(parents=True, exist_ok=True)
    resultado_path = resultado_dir / "resultado.json"
    resultado_path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== Resultado T12 ===")
    for chave, valor in resultado["itens"].items():
        status = "OK" if valor.get("ok") else "FALHA"
        print(f"  {chave}: {status}")
    print(f"\nResumo: {resultado['resumo']}")
    print(f"Arquivo: {resultado_path}")

    return resultado


if __name__ == "__main__":
    asyncio.run(main())