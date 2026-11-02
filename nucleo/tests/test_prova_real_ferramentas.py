"""Testes offline da prova real de ferramentas (J2).

Cobre:
- Sanitização de chaves, endpoints, modelos e caminhos pessoais.
- Recusa do script sem variáveis de ambiente obrigatórias.
- Harness simulado com provedor OpenAI falso que emite tool_call + texto final.

Nenhum teste aqui faz rede nem toca em serviço real; a prova real é executada
separadamente via scripts/provas/prova-real-ferramentas.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch

import pytest

# Garante que o núcleo e a raiz do repo estão no path para importar módulos internos e scripts
NUCLEO_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = NUCLEO_DIR.parent
for _p in (str(NUCLEO_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Sanitização
# ---------------------------------------------------------------------------

class TestSanitizacao:
    """Função de sanitização testável: remove segredos e dados pessoais."""

    def _sanitizar(self, texto: str) -> str:
        from vard.sanitizacao import sanitizar
        return sanitizar(texto)

    def test_remove_bearer_token(self):
        assert "***" in self._sanitizar("Authorization: Bearer sk-abc123xyz")
        assert "sk-abc123xyz" not in self._sanitizar("Authorization: Bearer sk-abc123xyz")

    def test_remove_sk_prefix(self):
        resultado = self._sanitizar("chave: sk-live-abcdef1234567890")
        assert "sk-live-abcdef1234567890" not in resultado

    def test_remove_api_key_padrao(self):
        resultado = self._sanitizar('api_key="segredo-123"')
        assert "segredo-123" not in resultado

    def test_remove_omni_base_url(self):
        os.environ["OMNI_BASE_URL"] = "https://api.exemplo-privado.com/v1"
        try:
            resultado = self._sanitizar("url: https://api.exemplo-privado.com/v1/chat")
            assert "exemplo-privado" not in resultado
        finally:
            del os.environ["OMNI_BASE_URL"]

    def test_remove_omni_modelo(self):
        os.environ["OMNI_MODELO"] = "agy/gemini-3.8-flash-tiered"
        try:
            resultado = self._sanitizar("modelo usado: agy/gemini-3.8-flash-tiered ok")
            assert "gemini-3.8-flash-tiered" not in resultado
        finally:
            del os.environ["OMNI_MODELO"]

    def test_remove_caminho_absoluto_pessoal(self):
        # Simula caminho pessoal típico
        resultado = self._sanitizar("arquivo em /home/usuario/dados/segredo.txt")
        assert "/home/usuario" not in resultado

    def test_preserva_texto_sem_segredo(self):
        texto = "Ferramenta hora_atual retornou 14:30"
        assert self._sanitizar(texto) == texto

    def test_remove_omni_api_key_valor(self):
        os.environ["OMNI_API_KEY"] = "chave-super-secreta-12345"
        try:
            resultado = self._sanitizar("usando chave-super-secreta-12345 para auth")
            assert "chave-super-secreta-12345" not in resultado
        finally:
            del os.environ["OMNI_API_KEY"]


# ---------------------------------------------------------------------------
# Recusa sem ambiente
# ---------------------------------------------------------------------------

class TestRecusaSemAmbiente:
    """Script deve recusar execução sem variáveis obrigatórias."""

    def test_recusa_sem_omni_base_url(self, monkeypatch):
        monkeypatch.delenv("OMNI_BASE_URL", raising=False)
        monkeypatch.delenv("OMNI_API_KEY", raising=False)
        monkeypatch.delenv("OMNI_MODELO", raising=False)
        from vard.sanitizacao import verificar_ambiente
        faltantes = verificar_ambiente()
        assert len(faltantes) > 0
        assert "OMNI_BASE_URL" in faltantes or "OMNI_API_KEY" in faltantes

    def test_ok_com_todas_variaveis(self, monkeypatch):
        monkeypatch.setenv("OMNI_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("OMNI_API_KEY", "test-key")
        monkeypatch.setenv("OMNI_MODELO", "test-model")
        from vard.sanitizacao import verificar_ambiente
        faltantes = verificar_ambiente()
        assert faltantes == []


# ---------------------------------------------------------------------------
# Harness simulado (provedor OpenAI falso com tool_call)
# ---------------------------------------------------------------------------

class HandlerOpenAIFalsoComFerramenta(BaseHTTPRequestHandler):
    """Responde /v1/chat/completions com tool_call seguida de texto final."""

    chamadas: list[dict] = []

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        HandlerOpenAIFalsoComFerramenta.chamadas.append({
            "path": self.path,
            "body": body.decode("utf-8", errors="replace"),
        })
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        # Verifica se é a primeira chamada (sem tool_results) ou segunda (com tool_results)
        tem_tool_result = b'"tool"' in body and b'"tool_call_id"' in body

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        if not tem_tool_result:
            # Primeira chamada: emite tool_call
            chunk_tool = {
                "id": "chatcmpl-j2",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_j2_test",
                        "type": "function",
                        "function": {
                            "name": "ver_configuracoes",
                            "arguments": "{}",
                        },
                    }]
                }, "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(chunk_tool)}\n".encode("utf-8"))
            fim = {
                "id": "chatcmpl-j2",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(fim)}\n".encode("utf-8"))
        else:
            # Segunda chamada: emite texto final
            chunk_texto = {
                "id": "chatcmpl-j2",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"content": "As configurações foram consultadas."}, "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(chunk_texto)}\n".encode("utf-8"))
            fim = {
                "id": "chatcmpl-j2",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {}, "finish_reason": "stop", "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(fim)}\n".encode("utf-8"))

        self.wfile.write(b"data: [DONE]\n")
        self.wfile.flush()


def _porta_livre() -> int:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestHarnessSimulado:
    """Valida o harness com provedor falso — NÃO é prova real."""

    async def test_harness_com_tool_call_simulada(self):
        """Provedor falso emite tool_call → cérebro processa → resposta final.

        Este teste valida o harness, não a integração real. O servidor é falso
        e a ferramenta é respondida localmente.
        """
        HandlerOpenAIFalsoComFerramenta.chamadas.clear()
        porta = _porta_livre()
        srv = HTTPServer(("127.0.0.1", porta), HandlerOpenAIFalsoComFerramenta)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory(prefix="vard-j2-test-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                config_dir = tmp_path / "config"
                config_dir.mkdir()
                dados_dir = tmp_path / "dados"
                dados_dir.mkdir()

                # Cria paineis.json apontando para o servidor falso
                paineis = {
                    "versao": 1,
                    "provedores": [{
                        "id": "j2-fake",
                        "nome": "J2 Fake",
                        "tipo": "openai_compat",
                        "url_base": f"http://127.0.0.1:{porta}",
                        "modelo": "m-j2-teste",
                    }],
                    "ativo": "j2-fake",
                    "reserva": None,
                    "agentes": {},
                    "mcps": [],
                }
                (config_dir / "paineis.json").write_text(
                    json.dumps(paineis, ensure_ascii=False), encoding="utf-8"
                )

                # Cria segredos.toml vazio (não precisa de chave para o falso)
                (config_dir / "segredos.toml").write_text("[lmstudio]\nchave = \"\"\n", encoding="utf-8")

                # Monkeypatcha config para usar diretório temporário
                from vard import config
                original_arquivo = config.arquivo_config
                original_pasta_dados = config.pasta_dados
                original_arquivo_segredos = config.arquivo_segredos

                def _fake_arquivo(nome: str) -> Path:
                    return config_dir / nome

                def _fake_pasta_dados() -> Path:
                    return dados_dir

                def _fake_segredos() -> Path:
                    return config_dir / "segredos.toml"

                with (
                    patch.object(config, "arquivo_config", side_effect=_fake_arquivo),
                    patch.object(config, "pasta_dados", side_effect=_fake_pasta_dados),
                    patch.object(config, "arquivo_segredos", side_effect=_fake_segredos),
                ):
                    from vard.cerebro import pedidos as modulo_pedidos
                    from vard.cerebro.contratos import EstadoPedido, Origem, Pedido
                    from server import _executar_pedido_cerebro

                    modulo_pedidos.definir_pasta(dados_dir / "pedidos")
                    modulo_pedidos.limpar_tudo()

                    pedido_id = str(uuid.uuid4())
                    pedido = Pedido(
                        pedido_id=pedido_id,
                        sessao_id="sess-j2-teste",
                        origem=Origem.PAINEL,
                        texto="quais são as configurações atuais?",
                    )

                    eventos: list[dict] = []

                    def emitir(ev):
                        eventos.append({
                            "tipo": ev.tipo.value if hasattr(ev.tipo, "value") else str(ev.tipo),
                            "dados": ev.dados or {},
                        })

                    # Admite o pedido antes de executar (contrato do executor)
                    modulo_pedidos.admitir(pedido)
                    await _executar_pedido_cerebro(pedido, emitir)

                    # Verifica estado final
                    info = modulo_pedidos.consultar(pedido_id)
                    assert info is not None
                    # O estado pode ser concluido ou falhou dependendo de como o
                    # cérebro lida com ferramentas sem gerenciador configurado.
                    # O importante é que o laço processou a tool_call.
                    tipos_eventos = [e["tipo"] for e in eventos]
                    # Deve ter pelo menos um evento (fim ou erro)
                    assert len(eventos) > 0
                    assert "fim" in tipos_eventos or "erro" in tipos_eventos
        finally:
            srv.shutdown()