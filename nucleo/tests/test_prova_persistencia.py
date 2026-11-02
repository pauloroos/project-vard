"""Prova offline: respostas, erros e argumentos não devem atingir arquivos."""
import asyncio
import importlib.util
import io
import json
import threading
import sys
import uuid
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


async def test_comando_publico_falha_fechado_sem_criar_arquivos(monkeypatch, tmp_path):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_bloqueada", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    monkeypatch.setenv("OMNI_API_KEY", uuid.uuid4().hex)
    monkeypatch.setenv("OMNI_BASE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("OMNI_MODELO", "modelo-ficticio")
    def nao_criar(*args, **kwargs):
        pytest.fail("comando iniciou antes de recusar")
    monkeypatch.setattr(prova.tempfile, "TemporaryDirectory", nao_criar)
    with pytest.raises(SystemExit):
        await prova.main(tmp_path / "resultado.json")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("etapa", ["preparo", "apos_injecao"])
async def test_falha_na_preparacao_limpa_credencial(monkeypatch, tmp_path, etapa):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_falha_preparo", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    from vard import segredos

    monkeypatch.setenv("OMNI_API_KEY", uuid.uuid4().hex)
    monkeypatch.setenv("OMNI_BASE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("OMNI_MODELO", "modelo-ficticio")
    monkeypatch.setattr(segredos, "_EM_MEMORIA", None)

    def falhar():
        raise RuntimeError("falha fictícia na preparação")

    if etapa == "preparo":
        monkeypatch.setattr(prova, "_estado_em_memoria", falhar)
    else:
        async def sem_mcps(*args):
            assert segredos._EM_MEMORIA is not None
            return []
        monkeypatch.setattr(prova, "provar_mcps_diretos", sem_mcps)
        monkeypatch.setattr(prova, "_porta_livre", falhar)
    with pytest.raises(RuntimeError, match="falha fictícia"):
        await prova._executar_prova(tmp_path / "resultado.json")
    assert segredos._EM_MEMORIA is None


def test_falha_parcial_na_preparacao_restaura_patches(monkeypatch):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_falha_parcial", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    from vard import instalaveis
    from vard.cerebro import pedidos

    ambiente_original = instalaveis.ambiente_limpo
    ler_original = pedidos._ler_info
    patch_original = prova.patch.object
    chamadas = 0

    def falhar_no_terceiro(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 3:
            raise RuntimeError("falha fictícia")
        return patch_original(*args, **kwargs)

    monkeypatch.setattr(prova.patch, "object", falhar_no_terceiro)
    with pytest.raises(RuntimeError, match="falha fictícia"):
        prova._estado_em_memoria()
    assert instalaveis.ambiente_limpo is ambiente_original
    assert pedidos._ler_info is ler_original


async def test_handshake_cancelado_encerra_subprocesso(monkeypatch):
    from vard.cerebro.ferramentas import GerenciadorFerramentas

    gm = GerenciadorFerramentas()
    inicio = asyncio.Event()
    processo = []
    original = asyncio.create_subprocess_exec

    async def criar(*args, **kwargs):
        proc = await original(*args, **kwargs)
        processo.append(proc)
        inicio.set()
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", criar)
    tarefa = asyncio.create_task(gm.adicionar_stdio("teste", sys.executable, ["-c", "import time; time.sleep(30)"]))
    try:
        await asyncio.wait_for(inicio.wait(), 5)
        assert gm.pids_mcp() == {}
    finally:
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)
        await gm.fechar_tudo()
    assert processo[0].returncode is not None


@pytest.mark.parametrize("base", ["http://exemplo.invalid/v1", "http://127.0.0.1.exemplo.invalid", "http://localhost:9999"])
async def test_http_fora_de_loopback_ip_recusado(monkeypatch, tmp_path, base):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_http", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    monkeypatch.setenv("OMNI_API_KEY", uuid.uuid4().hex)
    monkeypatch.setenv("OMNI_BASE_URL", base)
    monkeypatch.setenv("OMNI_MODELO", "modelo-ficticio")
    def nao_criar(*args, **kwargs):
        pytest.fail("não recusou antes de criar arquivos")
    monkeypatch.setattr(prova.tempfile, "TemporaryDirectory", nao_criar)
    with pytest.raises(SystemExit):
        await prova._executar_prova(tmp_path / "resultado.json")
    assert not list(tmp_path.iterdir())


def test_credencial_nao_e_herdada_pelos_mcps(monkeypatch):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_ambiente", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    from vard import instalaveis

    monkeypatch.setenv("OMNI_API_KEY", uuid.uuid4().hex)
    with prova._estado_em_memoria():
        assert "OMNI_API_KEY" not in instalaveis.ambiente_limpo()
    assert "OMNI_API_KEY" in instalaveis.ambiente_limpo()


@pytest.mark.parametrize("modo", ["resposta", "erro", "erro_executor", "argumentos", "ferramenta", "nome", "url_codificada", "modelo_codificado", "fragmentos", "acesso_local", "mcp_lento"])
async def test_prova_completa_nao_grava_credencial(monkeypatch, tmp_path, capsys, caplog, modo):
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("prova_persistencia", raiz / "scripts/provas/prova-real-ferramentas.py")
    prova = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prova)
    canario = uuid.uuid4().hex
    codificado = "".join(f"%{ord(c):02X}" for c in canario)
    recebidos = []
    acesso_local = []
    filhos = []

    class Provedor(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            recebidos.append(self.headers.get("Authorization"))
            tamanho = int(self.headers.get("Content-Length", "0"))
            corpo = self.rfile.read(tamanho)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if modo in ("argumentos", "ferramenta", "nome") and b'"tool_call_id"' not in corpo:
                args = {"reason": canario} if modo == "argumentos" else {}
                nome = canario if modo == "nome" else "ver_configuracoes"
                delta = {"tool_calls": [{"index": 0, "id": "chamada", "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}]}
            else:
                delta = {"content": canario}
            mensagem = {"choices": [{"delta": delta, "index": 0}]}
            self.wfile.write(f"data: {json.dumps(mensagem)}\n".encode())
            self.wfile.write(b"data: [DONE]\n")

    servidor = HTTPServer(("127.0.0.1", 0), Provedor)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OMNI_API_KEY", canario)
    monkeypatch.setenv("OMNI_BASE_URL", f"http://127.0.0.1:{servidor.server_port}" + ("/" + codificado if modo == "url_codificada" else ""))
    monkeypatch.setenv("OMNI_MODELO", codificado if modo == "modelo_codificado" else "modelo-ficticio")

    import server
    from vard.cerebro import pedidos
    from vard.cerebro import provedores
    monkeypatch.setattr(pedidos, "_pasta_pedidos", None)
    chamadas = []

    class Ferramentas:
        async def listar_todas(self):
            return [{"nome": "ver_configuracoes", "identificador": "configuracoes", "schema": {"type": "object", "properties": {}}}]

        async def chamar(self, identificador, nome, argumentos):
            chamadas.append((identificador, nome, argumentos))
            return "configuração fictícia"

        async def fechar_tudo(self):
            pass

    @asynccontextmanager
    async def lifespan(app):
        monkeypatch.setattr(server, "_ferramentas_cerebro", Ferramentas())
        if modo == "erro_executor":
            async def executor(pedido, emitir):
                raise RuntimeError(canario)
        else:
            executor = server._executar_pedido_cerebro
        pedidos.configurar_executor(executor)
        def emitir(ev):
            if modo == "fragmentos" and ev.tipo.value == "fim":
                for parte in (canario[:16], canario[16:]):
                    server.publicar_evento_pedido(pedido_id=ev.pedido_id, sessao_id=ev.sessao_id,
                                                  seq=ev.seq, tipo="texto", dados={"texto": parte})
            server.publicar_evento_pedido(pedido_id=ev.pedido_id, sessao_id=ev.sessao_id,
                                          seq=ev.seq, tipo=ev.tipo.value, dados=ev.dados or {})
        pedidos.configurar_emissor(emitir)
        yield

    monkeypatch.setattr(server.app.router, "lifespan_context", lifespan)
    if modo == "erro":
        original_stream = provedores._stream_http

        async def stream_com_erro(*args, **kwargs):
            async for linha in original_stream(*args, **kwargs):
                raise RuntimeError(canario)
                yield linha

        monkeypatch.setattr(provedores, "_stream_http", stream_com_erro)
    async def sem_mcps(*args):
        if modo == "mcp_lento":
            filhos.append(await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(30)"))
        return []
    monkeypatch.setattr(prova, "provar_mcps_diretos", sem_mcps)
    if modo == "acesso_local":
        import httpx
        original_provar = prova.provar_cerebro_http

        async def provar_com_tentativa(config, dados, porta, token):
            async with httpx.AsyncClient() as cliente:
                resposta = await cliente.get(f"http://127.0.0.1:{porta}/saude")
                acesso_local.append(resposta.status_code)
                resposta = await cliente.post(f"http://127.0.0.1:{porta}/pedidos", json={})
                acesso_local.append(resposta.status_code)
                resposta = await cliente.get(f"http://127.0.0.1:{porta}/saude", headers={"X-Vard-Prova": "incorreto"})
                acesso_local.append(resposta.status_code)
            return await original_provar(config, dados, porta, token)

        monkeypatch.setattr(prova, "provar_cerebro_http", provar_com_tentativa)

    original_open = io.open
    escritas = []
    vazamentos = []

    class Monitor:
        def __init__(self, arquivo):
            self.arquivo = arquivo
            self.acumulado = ""

        def write(self, dados):
            texto = dados.decode("utf-8", errors="replace") if isinstance(dados, bytes) else dados
            self.acumulado += texto
            escritas.append(texto)
            if canario in self.acumulado or codificado in self.acumulado:
                vazamentos.append(True)
                raise AssertionError("credencial enviada para escrita em disco")
            return self.arquivo.write(dados)

        def __enter__(self):
            self.arquivo.__enter__()
            return self

        def __exit__(self, *args):
            return self.arquivo.__exit__(*args)

        def __getattr__(self, nome):
            return getattr(self.arquivo, nome)

    def abrir(arquivo, modo="r", *args, **kwargs):
        f = original_open(arquivo, modo, *args, **kwargs)
        return Monitor(f) if any(c in modo for c in "wax+") else f

    monkeypatch.setattr(io, "open", abrir)
    try:
        resultado = await prova._executar_prova(tmp_path / "resultado.json")
        assert escritas
        assert not vazamentos, "tentativa de gravar credencial"
        assert canario not in json.dumps(resultado, ensure_ascii=False)
        if modo == "fragmentos":
            conteudo = json.dumps(resultado, ensure_ascii=False)
            assert canario[:16] not in conteudo and canario[16:] not in conteudo
        if modo == "acesso_local":
            assert acesso_local == [403, 403, 403]
        if modo == "mcp_lento":
            assert filhos[0].returncode is not None
            assert any(p.get("pid") == filhos[0].pid for p in resultado["processos"])
        saida = capsys.readouterr()
        assert canario not in saida.out + saida.err + caplog.text
        if modo != "erro_executor":
            assert recebidos and all(a == f"Bearer {canario}" for a in recebidos)
        if modo == "ferramenta":
            assert chamadas == [("configuracoes", "ver_configuracoes", {})]
        if modo == "argumentos":
            assert not chamadas
    finally:
        for filho in filhos:
            if filho.returncode is None:
                filho.terminate()
                await filho.wait()
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)
