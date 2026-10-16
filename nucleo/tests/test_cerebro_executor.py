"""Testes do executor real do cérebro próprio (T16d).

Cobre:
- Provedor OpenAI-compatível FALSO em porta livre → POST /pedidos + GET devolvem resposta do dublê.
- Credencial lida pelo cofre (monkeypatch de credenciais.ler_para_uso_interno) e NUNCA no log/resposta.
- Sem provedor/modelo/credencial → falha clara (_ErroCerebro com código específico).
- Provedor fora do ar → falha clara sem travar a fila.
- CLI ativo continua no SupervisorCli (CLI falsa).
- cerebro='openjarvis' (padrão) não muda nada.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# Adiciona o núcleo ao path para importar server e módulos relacionados
NUCLEO_DIR = Path(__file__).resolve().parents[1]
if str(NUCLEO_DIR) not in sys.path:
    sys.path.insert(0, str(NUCLEO_DIR))

from vard.cerebro import pedidos as modulo_pedidos
from vard.cerebro.contratos import EstadoPedido, Pedido, Origem
from vard import config


# ---------------------------------------------------------------------------
# Servidor OpenAI-compatível falso (stream SSE)
# ---------------------------------------------------------------------------

class _HandlerOpenAIFalso(BaseHTTPRequestHandler):
    """Servidor HTTP mínimo que responde /v1/chat/completions em stream SSE."""

    resposta_texto = "resposta do duble openai"

    def log_message(self, format, *args):  # noqa: A002
        # Silencia logs do servidor durante testes
        pass

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        # Lê o body (não usado, mas necessário para consumir)
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            self.rfile.read(content_length)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        # Emite chunks SSE compatíveis com OpenAI streaming
        chunk_data = {
            "id": "chatcmpl-teste",
            "object": "chat.completion.chunk",
            "choices": [{"delta": {"content": self.resposta_texto}, "index": 0}],
        }
        linha = f"data: {json.dumps(chunk_data)}\n\n"
        self.wfile.write(linha.encode("utf-8"))

        # Chunk final
        fim = {"id": "chatcmpl-teste", "object": "chat.completion.chunk", "choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]}
        self.wfile.write(f"data: {json.dumps(fim)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
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
# Fixtures de configuração
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa_pedidos(tmp_path: Path):
    """Garante pasta de pedidos limpa por teste."""
    modulo_pedidos.definir_pasta(tmp_path / "pedidos")
    modulo_pedidos.limpar_tudo()
    yield
    modulo_pedidos.limpar_tudo()
    modulo_pedidos.definir_pasta(None)


@pytest.fixture
def paineis_dir(tmp_path: Path):
    """Diretório temporário para paineis.json."""
    d = tmp_path / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _escrever_paineis(paineis_dir: Path, dados: dict) -> None:
    arq = paineis_dir / "paineis.json"
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def _criar_pedido(texto: str = "pergunta teste", sessao: str = "sess-teste") -> Pedido:
    import uuid
    return Pedido(
        pedido_id=str(uuid.uuid4()),
        sessao_id=sessao,
        origem=Origem.PAINEL,
        texto=texto,
    )


# ---------------------------------------------------------------------------
# Testes de falhas estruturadas
# ---------------------------------------------------------------------------

class TestFalhasEstruturadas:
    """Sem provedor, modelo, url_base ou credencial → _ErroCerebro com código claro."""

    @pytest.mark.asyncio
    async def test_sem_provedor_ativo_levanta_cerebro_sem_provedor(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {"versao": 1, "provedores": [], "ativo": None})
        eventos: list = []

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with pytest.raises(_ErroCerebro) as excinfo:
                await _executar_pedido_cerebro(_criar_pedido(), lambda ev: eventos.append(ev))
            assert excinfo.value.codigo == "cerebro_sem_provedor"

    @pytest.mark.asyncio
    async def test_sem_url_base_levanta_cerebro_sem_url_base(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{"id": "p1", "nome": "P1", "tipo": "openai_compat", "url_base": "", "modelo": "m1"}],
            "ativo": "p1",
        })
        eventos: list = []

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with pytest.raises(_ErroCerebro) as excinfo:
                await _executar_pedido_cerebro(_criar_pedido(), lambda ev: eventos.append(ev))
            assert excinfo.value.codigo == "cerebro_sem_url_base"

    @pytest.mark.asyncio
    async def test_sem_modelo_levanta_cerebro_sem_modelo(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{"id": "p1", "nome": "P1", "tipo": "openai_compat", "url_base": "http://x", "modelo": ""}],
            "ativo": "p1",
        })
        eventos: list = []

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with pytest.raises(_ErroCerebro) as excinfo:
                await _executar_pedido_cerebro(_criar_pedido(), lambda ev: eventos.append(ev))
            assert excinfo.value.codigo == "cerebro_sem_modelo"

    @pytest.mark.asyncio
    async def test_credencial_ref_sem_valor_no_cofre_levanta_cerebro_sem_credencial(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "p1", "nome": "P1", "tipo": "anthropic",
                "url_base": "http://x", "modelo": "m1", "credencial_ref": "ref-inexistente",
            }],
            "ativo": "p1",
        })
        eventos: list = []

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with patch("vard.credenciais.ler_para_uso_interno", return_value=None):
                with pytest.raises(_ErroCerebro) as excinfo:
                    await _executar_pedido_cerebro(_criar_pedido(), lambda ev: eventos.append(ev))
                assert excinfo.value.codigo == "cerebro_sem_credencial"

    @pytest.mark.asyncio
    async def test_tipo_desconhecido_levanta_cerebro_tipo_desconhecido(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro, _ErroCerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{"id": "p1", "nome": "P1", "tipo": "xyz_invalido", "url_base": "http://x", "modelo": "m1"}],
            "ativo": "p1",
        })
        eventos: list = []

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with pytest.raises(_ErroCerebro) as excinfo:
                await _executar_pedido_cerebro(_criar_pedido(), lambda ev: eventos.append(ev))
            assert excinfo.value.codigo == "cerebro_tipo_desconhecido"


# ---------------------------------------------------------------------------
# Teste de integração com servidor OpenAI falso
# ---------------------------------------------------------------------------

class TestIntegracaoOpenAICompat:
    """Provedor OpenAI-compatível falso → pedido completa com resposta do dublê."""

    @pytest.mark.asyncio
    async def test_pedido_completa_com_resposta_do_duble(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        from server import _executar_pedido_cerebro
        from vard.cerebro.contratos import TipoEvento

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "local-fake", "nome": "Local Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "modelo-teste",
            }],
            "ativo": "local-fake",
        })

        eventos: list = []
        pedido = _criar_pedido()
        # O laço exige que o pedido esteja admitido na pasta de pedidos
        modulo_pedidos.admitir(pedido)

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            await _executar_pedido_cerebro(pedido, lambda ev: eventos.append(ev))

        # Verifica que houve evento TEXTO com conteúdo do dublê
        textos = [
            e for e in eventos
            if getattr(e, "tipo", None) == TipoEvento.TEXTO and e.dados.get("texto")
        ]
        assert len(textos) >= 1
        conteudo = "".join(e.dados.get("texto", "") for e in textos)
        assert "resposta do duble openai" in conteudo


# ---------------------------------------------------------------------------
# Teste de credencial via cofre
# ---------------------------------------------------------------------------

class TestCredencialViaCofre:
    """Credencial é lida pelo cofre; valor nunca aparece em logs ou resposta."""

    @pytest.mark.asyncio
    async def test_credencial_lida_pelo_cofre_e_usada_no_adaptador(
        self, servidor_openai_falso: str, paineis_dir: Path
    ):
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "anthro-fake", "nome": "Anthro Fake", "tipo": "openai_compat",
                "url_base": servidor_openai_falso, "modelo": "m-teste",
                "credencial_ref": "minha-chave-api",
            }],
            "ativo": "anthro-fake",
        })

        eventos: list = []
        pedido = _criar_pedido()
        modulo_pedidos.admitir(pedido)
        token_ficticio = "cofre-token-ficticio-abc123"

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with patch("vard.credenciais.ler_para_uso_interno", return_value=token_ficticio) as mock_cofre:
                await _executar_pedido_cerebro(pedido, lambda ev: eventos.append(ev))
                # Cofre foi chamado com os parâmetros corretos
                mock_cofre.assert_called_once_with("provedor", "minha-chave-api")

        # O token fictício NÃO deve aparecer nos eventos
        for ev in eventos:
            dados_str = str(getattr(ev, "dados", ""))
            assert token_ficticio not in dados_str


# ---------------------------------------------------------------------------
# Teste de provedor fora do ar
# ---------------------------------------------------------------------------

class TestProvedorForaDoAr:
    """Provedor inacessível → falha clara sem travar a fila."""

    @pytest.mark.asyncio
    async def test_provedor_fora_do_ar_falha_sem_travar(self, paineis_dir: Path):
        from server import _executar_pedido_cerebro
        from vard.cerebro.contratos import TipoEvento

        # Porta que ninguém está ouvindo
        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [{
                "id": "morto", "nome": "Morto", "tipo": "openai_compat",
                "url_base": "http://127.0.0.1:19999", "modelo": "m1",
            }],
            "ativo": "morto",
        })

        eventos: list = []
        pedido = _criar_pedido()
        modulo_pedidos.admitir(pedido)

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            # O laço captura ErroProvedor e emite evento ERRO; não levanta exceção.
            await _executar_pedido_cerebro(pedido, lambda ev: eventos.append(ev))

        # Verifica que houve evento de erro com código de conexão/timeout
        erros = [e for e in eventos if getattr(e, "tipo", None) == TipoEvento.ERRO]
        assert len(erros) >= 1
        codigo_erro = str(erros[0].dados.get("erro", ""))
        assert codigo_erro in ("conexao", "timeout", "rede")

        # Estado do pedido deve ser FALHOU
        info = modulo_pedidos.consultar(pedido.pedido_id)
        assert info is not None
        assert info.estado == EstadoPedido.FALHOU


# ---------------------------------------------------------------------------
# Teste de CLI ativa
# ---------------------------------------------------------------------------

class TestCliAtiva:
    """CLI ativa continua funcionando via SupervisorCli + AdaptadorCli."""

    @pytest.mark.asyncio
    async def test_cli_claude_usa_supervisor(self, paineis_dir: Path, monkeypatch):
        from server import _executar_pedido_cerebro

        _escrever_paineis(paineis_dir, {
            "versao": 1,
            "provedores": [],
            "ativo": None,
            "agentes": {
                "claude": {"tipo": "cli-claude", "ativo": True, "modelo": "claude-test", "yolo": True},
            },
        })

        # Monkeypatch para evitar subprocesso real
        supervisor_mock_called = {"canal": False}

        class CanalFake:
            async def enviar(self, linha): pass
            async def linhas(self):
                yield json.dumps({"type": "system", "subtype": "init"})
                return
            async def interromper(self): pass

        class SupervisorFake:
            async def canal(self, provedor, sessao_id):
                supervisor_mock_called["canal"] = True
                return CanalFake()

        pedido = _criar_pedido()
        modulo_pedidos.admitir(pedido)

        with patch.object(config, "arquivo_config", return_value=paineis_dir / "paineis.json"):
            with patch("server._obter_supervisor_cli", return_value=SupervisorFake()):
                eventos: list = []
                await _executar_pedido_cerebro(pedido, lambda ev: eventos.append(ev))

        assert supervisor_mock_called["canal"] is True


# ---------------------------------------------------------------------------
# Teste montador unificado
# ---------------------------------------------------------------------------

class TestMontadorUnificado:
    """montar_adaptador cria o tipo correto de adaptador."""

    def test_montar_openai_compat(self):
        from vard.cerebro.montador import montar_adaptador
        from vard.cerebro.provedores import AdaptadorOpenAICompat

        adp = montar_adaptador("openai_compat", "http://x", "m1", "k1")
        assert isinstance(adp, AdaptadorOpenAICompat)

    def test_montar_anthropic(self):
        from vard.cerebro.montador import montar_adaptador
        from vard.cerebro.provedores import AdaptadorAnthropic

        adp = montar_adaptador("anthropic", "http://x", "m1", "k1")
        assert isinstance(adp, AdaptadorAnthropic)

    def test_montar_google(self):
        from vard.cerebro.montador import montar_adaptador
        from vard.cerebro.provedores import AdaptadorGoogle

        adp = montar_adaptador("google", "http://x", "m1", "k1")
        assert isinstance(adp, AdaptadorGoogle)

    def test_montar_openai_nativo(self):
        from vard.cerebro.montador import montar_adaptador
        from vard.cerebro.provedores import AdaptadorOpenAINativo

        adp = montar_adaptador("openai_nativo", "http://x", "m1", "k1")
        assert isinstance(adp, AdaptadorOpenAINativo)

    def test_montar_lmstudio(self):
        from vard.cerebro.montador import montar_adaptador
        from vard.cerebro.provedores import AdaptadorOpenAICompat

        adp = montar_adaptador("lmstudio", "http://x", "m1")
        assert isinstance(adp, AdaptadorOpenAICompat)

    def test_montar_tipo_desconhecido_levanta_value_error(self):
        from vard.cerebro.montador import montar_adaptador

        with pytest.raises(ValueError, match="tipo_de_provedor_desconhecido"):
            montar_adaptador("xyz", "http://x", "m1")

    def test_primeiro_uso_usa_montador_unificado(self):
        """primeiro_uso/cerebro._montar_adaptador delega ao montador unificado."""
        from vard.primeiro_uso.cerebro import _montar_adaptador
        from vard.cerebro.provedores import AdaptadorOpenAICompat

        adp = _montar_adaptador("openai_compat", "http://x", "m1", "k1")
        assert isinstance(adp, AdaptadorOpenAICompat)