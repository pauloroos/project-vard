import json
import sys

import pytest


def test_sessao_claude_recebe_mcps(tmp_path):
    from vard.cerebro.cli_processos import ProvedorCli, _preparar_pasta_sessao
    from vard.segredos import SERVIDORES_LOCAIS
    pasta = _preparar_pasta_sessao(ProvedorCli("cli", "cli-claude"), "sessao", base_dados=tmp_path)
    servidores = json.loads((pasta / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servidores) == set(SERVIDORES_LOCAIS)
    assert "configuracoes" in servidores
    assert servidores["configuracoes"]["command"] == sys.executable
    assert servidores["configuracoes"]["args"][0].endswith("configuracoes_mcp.py")


def test_mcp_aberto_pelo_openjarvis_limpa_seu_proprio_ambiente(monkeypatch):
    import os
    from vard.instalaveis import limpar_ambiente_mcp
    monkeypatch.setenv("CLAUDECODE", "contexto-ficticio")
    monkeypatch.setenv("ANTHROPIC_FICTICIO", "credencial-ficticia")
    monkeypatch.setenv("ORCA_AGENT_FICTICIO", "contexto-ficticio")
    limpar_ambiente_mcp()
    assert not any(k.upper().startswith(("CLAUDE", "ANTHROPIC", "ORCA_AGENT")) for k in os.environ)
    assert os.environ["VARD_CONFIG"]


@pytest.mark.asyncio
async def test_lifespan_reutiliza_ferramentas_e_fecha(monkeypatch):
    import server
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    from vard.cerebro import laco, montador
    from vard.segredos import SERVIDORES_LOCAIS
    conectados = []
    fechados = []
    recebidos = []
    async def adicionar(self, ident, comando, args):
        conectados.append(ident)
        self.registrar_interna("falsa_" + ident, lambda: "ok")
    async def fechar(self):
        fechados.append(self)
    async def executar(*args, **kwargs):
        recebidos.append(kwargs["gerenciador_ferramentas"])
    monkeypatch.setattr(GerenciadorFerramentas, "adicionar_stdio", adicionar)
    monkeypatch.setattr(GerenciadorFerramentas, "fechar_tudo", fechar)
    monkeypatch.setattr(server.telegram_mod, "deve_iniciar_poller", lambda: False)
    monkeypatch.setattr(server, "_ler_provedor_ativo", lambda: {"tipo": "lmstudio", "url_base": "http://127.0.0.1:1", "modelo": "falso"})
    monkeypatch.setattr(montador, "montar_adaptador", lambda *a: object())
    monkeypatch.setattr(laco, "executar_pedido", executar)
    async with server.lifespan(server.app):
        await server._executar_pedido_cerebro(None, lambda e: None)
        await server._executar_pedido_cerebro(None, lambda e: None)
        assert conectados == list(SERVIDORES_LOCAIS)
        assert recebidos[0] is recebidos[1]
        assert len(await recebidos[0].listar_todas()) == len(SERVIDORES_LOCAIS)
    assert fechados == [recebidos[0]]


@pytest.mark.asyncio
async def test_saida_com_erro_fecha_instalacao_e_cli(monkeypatch):
    import server
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    monkeypatch.setattr(GerenciadorFerramentas, "adicionar_stdio", AsyncMock())
    monkeypatch.setattr(server.telegram_mod, "deve_iniciar_poller", lambda: False)
    instalacao = Mock()
    cli = AsyncMock()
    monkeypatch.setattr(server, "_instalaveis", SimpleNamespace(encerrar=instalacao))
    monkeypatch.setattr(server, "_supervisor_cli", SimpleNamespace(encerrar_tudo=cli))
    with pytest.raises(RuntimeError, match="fictício"):
        async with server.lifespan(server.app):
            raise RuntimeError("fictício")
    instalacao.assert_called_once()
    cli.assert_awaited_once()


@pytest.mark.asyncio
async def test_stdio_limpa_ambiente_e_serializa_chamadas(monkeypatch):
    import asyncio
    from vard.cerebro.ferramentas import _ClienteStdio
    chamadas = []
    entrada = asyncio.StreamReader()
    class Saida:
        def write(self, dados):
            chamadas.append(json.loads(dados))
        async def drain(self):
            await asyncio.sleep(0)
    from types import SimpleNamespace
    async def criar(*args, **kwargs):
        return SimpleNamespace(stdin=Saida(), stdout=entrada)
    monkeypatch.setenv("CLAUDECODE", "contexto-ficticio")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", criar)
    cliente = _ClienteStdio("falso", sys.executable, [])
    cliente._process = await criar()
    async def responder():
        await asyncio.sleep(0.02)
        entrada.feed_data(b'{"id":1,"result":{"ok":true}}\n')
        await asyncio.sleep(0.02)
        entrada.feed_data(b'{"id":2,"result":{"ok":true}}\n')
    tarefa = asyncio.create_task(responder())
    try:
        resultados = await asyncio.gather(cliente._rpc("primeira"), cliente._rpc("segunda"))
    finally:
        await tarefa
    assert resultados == [{"ok": True}, {"ok": True}]
    assert [c["method"] for c in chamadas] == ["primeira", "segunda"]


@pytest.mark.asyncio
async def test_iniciar_stdio_nao_herda_contexto_do_agente(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from vard.cerebro.ferramentas import _ClienteStdio
    opcoes = []
    async def criar(*args, **kwargs):
        opcoes.append(kwargs)
        return SimpleNamespace()
    monkeypatch.setenv("CLAUDECODE", "contexto-ficticio")
    monkeypatch.setenv("ANTHROPIC_FICTICIO", "contexto-ficticio")
    monkeypatch.setenv("ORCA_AGENT_FICTICIO", "contexto-ficticio")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", criar)
    cliente = _ClienteStdio("falso", sys.executable, [])
    monkeypatch.setattr(cliente, "_rpc", AsyncMock(return_value={"tools": []}))
    monkeypatch.setattr(cliente, "_notify", AsyncMock())
    await cliente.iniciar()
    assert not any(k.upper().startswith(("CLAUDE", "ANTHROPIC", "ORCA_AGENT")) for k in opcoes[0]["env"])


@pytest.mark.asyncio
async def test_laco_chama_mcp_pelo_nome_exposto_a_api(tmp_path):
    from pathlib import Path
    from vard.cerebro import laco, pedidos
    from vard.cerebro.contratos import Pedido, Origem
    from vard.cerebro.provedores import ResultadoInferencia
    from vard.cerebro.ferramentas import GerenciadorFerramentas
    gerente = GerenciadorFerramentas()
    pedido = Pedido(pedido_id="pedido-mcp", sessao_id="sessao-mcp", origem=Origem.PAINEL, texto="eco")
    pedidos.definir_pasta(tmp_path / "pedidos")
    pedidos.admitir(pedido)
    class Modelo:
        turno = 0
        async def inferir(self, mensagens, ferramentas=None):
            self.turno += 1
            if self.turno == 1:
                assert any(f["name"] == "eco" for f in ferramentas)
                return ResultadoInferencia(chamadas_ferramenta=[{"id": "c1", "nome": "eco", "argumentos": {"texto": "mensagem fictícia"}}])
            resultados = [json.loads(m["content"]) for m in mensagens if m["role"] == "tool"]
            assert resultados == [{"resultado": "mensagem fictícia"}]
            chamadas = [m for m in mensagens if m["role"] == "assistant" and m.get("tool_calls")]
            assert chamadas[0]["tool_calls"][0]["function"]["name"] == "eco"
            return ResultadoInferencia(texto="feito")
    try:
        await gerente.adicionar_stdio("externo-falso", sys.executable, [str(Path(__file__).parent / "fixtures/cerebro/mcp_falso.py")])
        await laco.executar_pedido(pedido, Modelo(), lambda e: None, gerente)
        assert pedidos.consultar(pedido.pedido_id).resposta == "feito"
    finally:
        await gerente.fechar_tudo()
        pedidos.limpar_tudo()
        pedidos.definir_pasta(None)
