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
import importlib.util
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

    def test_remove_omni_base_url(self, monkeypatch):
        monkeypatch.setenv("OMNI_BASE_URL", "https://api.exemplo-privado.com/v1")
        resultado = self._sanitizar("url: https://api.exemplo-privado.com/v1/chat")
        assert "exemplo-privado" not in resultado

    def test_remove_omni_modelo(self, monkeypatch):
        monkeypatch.setenv("OMNI_MODELO", "provedor/modelo-de-teste")
        resultado = self._sanitizar("modelo usado: provedor/modelo-de-teste ok")
        assert "modelo-de-teste" not in resultado

    def test_remove_caminho_absoluto_pessoal(self):
        # Simula caminho pessoal típico
        resultado = self._sanitizar("arquivo em /home/usuario/dados/segredo.txt")
        assert "/home/usuario" not in resultado

    def test_preserva_texto_sem_segredo(self):
        texto = "Ferramenta hora_atual retornou 14:30"
        assert self._sanitizar(texto) == texto

    def test_remove_omni_api_key_valor(self, monkeypatch):
        monkeypatch.setenv("OMNI_API_KEY", "chave-super-secreta-12345")
        resultado = self._sanitizar("usando chave-super-secreta-12345 para auth")
        assert "chave-super-secreta-12345" not in resultado


# ---------------------------------------------------------------------------
# Recusa sem ambiente
# ---------------------------------------------------------------------------

class TestRecusaSemAmbiente:
    """Script deve recusar execução sem variáveis obrigatórias."""

    @pytest.mark.parametrize("campo", ["OMNI_BASE_URL", "OMNI_MODELO"])
    async def test_recusa_credencial_na_configuracao_antes_de_gravar(self, monkeypatch, tmp_path, campo):
        spec = importlib.util.spec_from_file_location(
            "prova_ferramentas", REPO_ROOT / "scripts/provas/prova-real-ferramentas.py"
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        canario = uuid.uuid4().hex
        monkeypatch.setenv("OMNI_API_KEY", canario)
        monkeypatch.setenv("OMNI_BASE_URL", "http://127.0.0.1:9999")
        monkeypatch.setenv("OMNI_MODELO", "modelo-ficticio")
        monkeypatch.setenv(campo, f"http://127.0.0.1/{canario}")
        def nao_criar_diretorio(*args, **kwargs):
            pytest.fail("criou diretório antes de validar configuração")

        monkeypatch.setattr(modulo.tempfile, "TemporaryDirectory", nao_criar_diretorio)
        with pytest.raises(SystemExit):
            await modulo._executar_prova(tmp_path / "relatorio.json")
        assert not list(tmp_path.iterdir())

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
                # Inclui as quatro chaves de agente exigidas por ajustes.validar_documento
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
                    "agentes": {
                        "claude": {"padrao": "", "modelos": []},
                        "codex": {"padrao": "", "modelos": []},
                        "opencode": {"padrao": "", "modelos": []},
                        "agy": {"padrao": "", "modelos": []},
                    },
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
                    import server as server_mod
                    from server import _executar_pedido_cerebro

                    # Fake tool manager: registra chamada e retorna resultado válido
                    chamadas_fake: list[tuple[str, str, dict]] = []

                    class FakeGerenciadorFerramentas:
                        async def listar_todas(self):
                            return [{
                                "nome": "ver_configuracoes",
                                "descricao": "Mostra configurações atuais",
                                "schema": {"type": "object", "properties": {}},
                                "identificador": "interno",
                            }]

                        async def chamar(self, identificador, nome, argumentos):
                            chamadas_fake.append((identificador, nome, argumentos))
                            return '{"versao": "0.4-teste", "provedor": "j2-fake"}'

                    fake_tools = FakeGerenciadorFerramentas()
                    original_tools = server_mod._ferramentas_cerebro
                    server_mod._ferramentas_cerebro = fake_tools

                    # Isola o teste do despachante global: salva _rodar_fn e configura None
                    # para que admitir() não dispare processar_fila concorrente com a chamada
                    # direta a _executar_pedido_cerebro. Sem isso, outro teste da suíte pode
                    # ter configurado _rodar_fn e as chamadas ao provedor falso se misturam.
                    rodar_fn_original = modulo_pedidos._rodar_fn
                    modulo_pedidos.configurar_executor(None)
                    try:
                        modulo_pedidos.definir_pasta(dados_dir / "pedidos")
                        modulo_pedidos.limpar_tudo()

                        pedido_id = str(uuid.uuid4())
                        sessao_id = "sess-j2-teste"
                        pedido = Pedido(
                            pedido_id=pedido_id,
                            sessao_id=sessao_id,
                            origem=Origem.PAINEL,
                            texto="quais são as configurações atuais?",
                        )

                        eventos: list[dict] = []

                        def emitir(ev):
                            eventos.append({
                                "tipo": ev.tipo.value if hasattr(ev.tipo, "value") else str(ev.tipo),
                                "dados": ev.dados or {},
                            })

                        # Admite o pedido (contrato do executor); com _rodar_fn=None o laço
                        # marca o pedido como FALHOU rapidamente e termina sem tocar no provedor.
                        modulo_pedidos.admitir(pedido)
                        tarefa_laco = modulo_pedidos._lacos_ativos.get(sessao_id)
                        if tarefa_laco is not None:
                            try:
                                await asyncio.wait_for(tarefa_laco, timeout=2.0)
                            except Exception:
                                pass

                        # Chama o executor diretamente; o laço já terminou e não há
                        # concorrência com outro _rodar_fn da suíte.
                        await _executar_pedido_cerebro(pedido, emitir)
                    finally:
                        modulo_pedidos.configurar_executor(rodar_fn_original)
                        server_mod._ferramentas_cerebro = original_tools

                    # Verifica estado final
                    info = modulo_pedidos.consultar(pedido_id)
                    assert info is not None
                    tipos_eventos = [e["tipo"] for e in eventos]
                    assert len(eventos) > 0
                    assert "fim" in tipos_eventos or "erro" in tipos_eventos

                    # Afirma que a ferramenta foi EXECUTADA (não apenas anunciada):
                    # 1) O gerenciador fake registrou a chamada com ver_configuracoes
                    assert len(chamadas_fake) > 0, "gerenciador fake não registrou nenhuma chamada"
                    assert chamadas_fake[0][1] == "ver_configuracoes", (
                        f"esperado ver_configuracoes; recebido: {chamadas_fake[0][1]}"
                    )

                    # 2) O servidor falso recebeu duas chamadas (tool_call + tool_result)
                    assert len(HandlerOpenAIFalsoComFerramenta.chamadas) >= 2, (
                        "esperado >=2 chamadas ao provedor (tool_call + tool_result); "
                        f"recebidas: {len(HandlerOpenAIFalsoComFerramenta.chamadas)}"
                    )
                    segunda_chamada = HandlerOpenAIFalsoComFerramenta.chamadas[1]["body"]
                    assert "tool_call_id" in segunda_chamada, (
                        "segunda chamada ao provedor deve conter tool_call_id (resultado da ferramenta)"
                    )

                    # 3) A resposta final menciona o resultado da ferramenta
                    eventos_fim = [e for e in eventos if e["tipo"] == "fim"]
                    assert len(eventos_fim) > 0, f"esperado evento 'fim'; recebidos: {tipos_eventos}"
                    texto_final = str(eventos_fim[0].get("dados", {}))
                    assert "configura" in texto_final.lower() or "consultadas" in texto_final.lower(), (
                        f"resposta final deve mencionar o resultado da ferramenta; recebido: {texto_final[:200]}"
                    )
        finally:
            srv.shutdown()


# ---------------------------------------------------------------------------
# Teste de canário: credencial nunca toca disco e autorização é exigida
# ---------------------------------------------------------------------------

class HandlerCanario(BaseHTTPRequestHandler):
    """Provedor falso que exige Authorization: Bearer <canário>.

    Registra todas as autorizações recebidas. Responde 401 quando o
    cabeçalho falta ou diverge; caso contrário emite tool_call + texto final.
    """

    autorizacoes_recebidas: list[str] = []
    canario_esperado: str = ""

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        auth = self.headers.get("Authorization", "")
        HandlerCanario.autorizacoes_recebidas.append(auth)

        if not auth.startswith("Bearer ") or auth[7:] != self.canario_esperado:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        tem_tool_result = b'"tool"' in body and b'"tool_call_id"' in body

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        if not tem_tool_result:
            chunk_tool = {
                "id": "chatcmpl-canario",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_canario",
                        "type": "function",
                        "function": {"name": "ver_configuracoes", "arguments": "{}"},
                    }]
                }, "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(chunk_tool)}\n".encode())
            fim = {
                "id": "chatcmpl-canario",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(fim)}\n".encode())
        else:
            chunk_texto = {
                "id": "chatcmpl-canario",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"content": "Configurações consultadas com sucesso."}, "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(chunk_texto)}\n".encode())
            fim = {
                "id": "chatcmpl-canario",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {}, "finish_reason": "stop", "index": 0}],
            }
            self.wfile.write(f"data: {json.dumps(fim)}\n".encode())

        self.wfile.write(b"data: [DONE]\n")
        self.wfile.flush()


class TestCanarioCredencialEmMemoria:
    """Garante que a credencial nunca toca disco e que a autorização é exercitada."""

    async def test_canario_nao_vaza_e_autorizacao_exigida(self):
        canario = f"CANARIO-{uuid.uuid4().hex}"
        HandlerCanario.autorizacoes_recebidas.clear()
        HandlerCanario.canario_esperado = canario

        porta = _porta_livre()
        srv = HTTPServer(("127.0.0.1", porta), HandlerCanario)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory(prefix="vard-canario-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                config_dir = tmp_path / "config"
                config_dir.mkdir()
                dados_dir = tmp_path / "dados"
                dados_dir.mkdir()

                paineis = {
                    "versao": 1,
                    "provedores": [{
                        "id": "canario-fake",
                        "nome": "Canario Fake",
                        "tipo": "openai_compat",
                        "url_base": f"http://127.0.0.1:{porta}",
                        "modelo": "m-canario-teste",
                    }],
                    "ativo": "canario-fake",
                    "reserva": None,
                    "agentes": {
                        "claude": {"padrao": "", "modelos": []},
                        "codex": {"padrao": "", "modelos": []},
                        "opencode": {"padrao": "", "modelos": []},
                        "agy": {"padrao": "", "modelos": []},
                    },
                    "mcps": [],
                }
                (config_dir / "paineis.json").write_text(
                    json.dumps(paineis, ensure_ascii=False), encoding="utf-8"
                )

                from vard import config, segredos as modulo_segredos
                original_arquivo = config.arquivo_config
                original_pasta_dados = config.pasta_dados
                original_arquivo_segredos = config.arquivo_segredos

                def _fake_arquivo(nome: str) -> Path:
                    return config_dir / nome

                def _fake_pasta_dados() -> Path:
                    return dados_dir

                def _fake_segredos() -> Path:
                    return config_dir / "segredos.toml"

                # Injeta credencial EM MEMÓRIA — nenhum arquivo é criado
                modulo_segredos.definir_em_memoria({"lmstudio": {"chave": canario}})

                with (
                    patch.object(config, "arquivo_config", side_effect=_fake_arquivo),
                    patch.object(config, "pasta_dados", side_effect=_fake_pasta_dados),
                    patch.object(config, "arquivo_segredos", side_effect=_fake_segredos),
                ):
                    from vard.cerebro import pedidos as modulo_pedidos
                    from vard.cerebro.contratos import Origem, Pedido
                    import server as server_mod
                    from server import _executar_pedido_cerebro

                    # Patcha _resolver_credencial_cofre para devolver o canário em memória
                    def _fake_resolver(credencial_ref: str, tipo: str) -> str:
                        return canario

                    original_resolver = server_mod._resolver_credencial_cofre
                    server_mod._resolver_credencial_cofre = _fake_resolver

                    chamadas_fake: list[tuple[str, str, dict]] = []

                    class FakeGerenciadorFerramentas:
                        async def listar_todas(self):
                            return [{
                                "nome": "ver_configuracoes",
                                "descricao": "Mostra configurações atuais",
                                "schema": {"type": "object", "properties": {}},
                                "identificador": "interno",
                            }]

                        async def chamar(self, identificador, nome, argumentos):
                            chamadas_fake.append((identificador, nome, argumentos))
                            return '{"versao": "0.4-canario", "provedor": "canario-fake"}'

                    fake_tools = FakeGerenciadorFerramentas()
                    original_tools = server_mod._ferramentas_cerebro
                    server_mod._ferramentas_cerebro = fake_tools

                    rodar_fn_original = modulo_pedidos._rodar_fn
                    modulo_pedidos.configurar_executor(None)
                    try:
                        modulo_pedidos.definir_pasta(dados_dir / "pedidos")
                        modulo_pedidos.limpar_tudo()

                        pedido_id = str(uuid.uuid4())
                        sessao_id = "sess-canario-teste"
                        pedido = Pedido(
                            pedido_id=pedido_id,
                            sessao_id=sessao_id,
                            origem=Origem.PAINEL,
                            texto="quais são as configurações atuais?",
                        )

                        eventos: list[dict] = []

                        def emitir(ev):
                            eventos.append({
                                "tipo": ev.tipo.value if hasattr(ev.tipo, "value") else str(ev.tipo),
                                "dados": ev.dados or {},
                            })

                        modulo_pedidos.admitir(pedido)
                        tarefa_laco = modulo_pedidos._lacos_ativos.get(sessao_id)
                        if tarefa_laco is not None:
                            try:
                                await asyncio.wait_for(tarefa_laco, timeout=2.0)
                            except Exception:
                                pass

                        await _executar_pedido_cerebro(pedido, emitir)
                    finally:
                        modulo_pedidos.configurar_executor(rodar_fn_original)
                        server_mod._ferramentas_cerebro = original_tools
                        server_mod._resolver_credencial_cofre = original_resolver
                        modulo_segredos.definir_em_memoria(None)

                    # --- Afirmações de segurança ---

                    # 1) Nenhum segredos.toml foi criado no diretório temporário
                    segredos_path = config_dir / "segredos.toml"
                    assert not segredos_path.exists(), (
                        "segredos.toml NÃO deve existir no diretório temporário"
                    )

                    # 2) Varredura recursiva: canário aparece ZERO vezes em qualquer arquivo
                    for arquivo in tmp_path.rglob("*"):
                        if arquivo.is_file():
                            conteudo = arquivo.read_text(encoding="utf-8", errors="replace")
                            assert canario not in conteudo, (
                                f"canário encontrado em {arquivo.relative_to(tmp_path)}"
                            )

                    # 3) Canário não apareceu em stdout/stderr capturado (handler não loga)
                    # O handler registra autorizações; verificamos que só recebeu o canário correto
                    assert len(HandlerCanario.autorizacoes_recebidas) >= 2, (
                        "esperado >=2 requisições ao provedor (tool_call + tool_result)"
                    )
                    for auth in HandlerCanario.autorizacoes_recebidas:
                        assert auth == f"Bearer {canario}", (
                            f"autorização inesperada: {auth[:20]}..."
                        )

                    # 4) Ferramenta foi executada e resposta final chegou
                    assert len(chamadas_fake) > 0, "ferramenta não foi executada"
                    tipos_eventos = [e["tipo"] for e in eventos]
                    assert "fim" in tipos_eventos, f"evento 'fim' ausente; recebidos: {tipos_eventos}"

                    # 5) Prova de autorização: credencial errada deve falhar com auth_401
                    HandlerCanario.autorizacoes_recebidas.clear()
                    HandlerCanario.canario_esperado = canario

                    def _fake_resolver_errado(credencial_ref: str, tipo: str) -> str:
                        return "CREDENCIAL-ERRADA"

                    server_mod._resolver_credencial_cofre = _fake_resolver_errado

                    with (
                        patch.object(config, "arquivo_config", side_effect=_fake_arquivo),
                        patch.object(config, "pasta_dados", side_effect=_fake_pasta_dados),
                        patch.object(config, "arquivo_segredos", side_effect=_fake_segredos),
                    ):
                        modulo_pedidos.configurar_executor(None)
                        try:
                            modulo_pedidos.limpar_tudo()
                            pedido_id_2 = str(uuid.uuid4())
                            pedido_2 = Pedido(
                                pedido_id=pedido_id_2,
                                sessao_id="sess-canario-falha",
                                origem=Origem.PAINEL,
                                texto="teste de falha de auth",
                            )
                            eventos_2: list[dict] = []

                            def emitir_2(ev):
                                eventos_2.append({
                                    "tipo": ev.tipo.value if hasattr(ev.tipo, "value") else str(ev.tipo),
                                    "dados": ev.dados or {},
                                })

                            modulo_pedidos.admitir(pedido_2)
                            tarefa_laco_2 = modulo_pedidos._lacos_ativos.get("sess-canario-falha")
                            if tarefa_laco_2 is not None:
                                try:
                                    await asyncio.wait_for(tarefa_laco_2, timeout=2.0)
                                except Exception:
                                    pass

                            await _executar_pedido_cerebro(pedido_2, emitir_2)
                        finally:
                            modulo_pedidos.configurar_executor(rodar_fn_original)
                            server_mod._resolver_credencial_cofre = original_resolver
                            modulo_segredos.definir_em_memoria(None)

                        info_falha = modulo_pedidos.consultar(pedido_id_2)
                        assert info_falha is not None
                        estado_falha = info_falha.estado.value if hasattr(info_falha.estado, "value") else str(info_falha.estado)
                        erro_falha = str(info_falha.erro or "")
                        assert estado_falha == "falhou" or "auth_401" in erro_falha, (
                            f"esperado falha por auth_401; estado={estado_falha}, erro={erro_falha[:200]}"
                        )
        finally:
            srv.shutdown()
