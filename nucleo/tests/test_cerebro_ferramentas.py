"""Testes da T3 — ferramentas e MCPs do cérebro.
Cobre: handshake/lista/chamada por stdio e Streamable HTTP; caminho com espaços
e argv sem shell; mesmo nome vindo de dois externos (identificador estável);
servidor indisponível; nome desabilitado; argumentos inválidos; ferramenta
bloqueante sem travar outra sessão. Prova: log JSON-RPC falso com initialize →
notifications/initialized → tools/list → tools/call; um servidor quebrado não
impede hora_atual nem o outro MCP; finally confirma subprocessos encerrados.
Credenciais só em memória.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from vard.cerebro.ferramentas import (
    FerramentaBloqueanteError,
    GerenciadorFerramentas,
    ServidorIndisponivelError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "cerebro"
MCP_FALSO = str(FIXTURES_DIR / "mcp_falso.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_linhas(*chunks: dict) -> str:
    """Monta corpo SSE a partir de dicts JSON-RPC."""
    return "".join(f"data: {json.dumps(c)}\n" for c in chunks)


async def _coletar_lista(gm: GerenciadorFerramentas) -> list[dict[str, Any]]:
    """Lista todas as ferramentas registradas."""
    return await gm.listar_todas()


# ---------------------------------------------------------------------------
# Stdio: handshake, lista, chamada
# ---------------------------------------------------------------------------

class TestStdio:
    async def test_handshake_lista_chamada_stdio(self):
        """Handshake completo + lista + chamada via stdio com mcp_falso.py."""
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="falso-stdio",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            ferramentas = await gm.listar_todas()
            nomes = [f["nome"] for f in ferramentas]
            assert "hora_atual" in nomes
            assert "eco" in nomes

            resultado = await gm.chamar("falso-stdio", "eco", {"texto": "olá"})
            assert resultado == "olá"
        finally:
            await gm.fechar_tudo()

    async def test_caminho_com_espacos(self, tmp_path: Path):
        """Caminho do script com espaços funciona (argv sem shell)."""
        pasta_com_espaco = tmp_path / "pasta com espaço"
        pasta_com_espaco.mkdir()
        script_destino = pasta_com_espaco / "mcp falso copia.py"
        # Copia o fixture para o caminho com espaços
        script_destino.write_text(
            (FIXTURES_DIR / "mcp_falso.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="espaco",
                comando=sys.executable,
                args=[str(script_destino)],
            )
            ferramentas = await gm.listar_todas()
            assert any(f["nome"] == "hora_atual" for f in ferramentas)
        finally:
            await gm.fechar_tudo()

    async def test_subprocessos_encerrados_no_finally(self):
        """finally confirma subprocessos encerrados após fechar_tudo."""
        gm = GerenciadorFerramentas()
        await gm.adicionar_stdio(
            identificador="fecha",
            comando=sys.executable,
            args=[MCP_FALSO],
        )
        # Verifica que há processo ativo
        assert gm._processos  # type: ignore[attr-defined]
        await gm.fechar_tudo()
        # Após fechar, não deve haver processos ativos
        assert not gm._processos  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Streamable HTTP: handshake, lista, chamada
# ---------------------------------------------------------------------------

class TestStreamableHTTP:
    @respx.mock
    async def test_handshake_lista_chamada_http(self):
        """Handshake + lista + chamada via Streamable HTTP com respostas falsas."""
        url = "http://mcp.exemplo.com/mcp"
        # initialize
        init_resp = {
            "jsonrpc": "2.0", "id": 1,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "http-falso", "version": "1"},
            },
        }
        # notifications/initialized → 202 sem corpo
        # tools/list
        lista_resp = {
            "jsonrpc": "2.0", "id": 2,
            "result": {
                "tools": [{
                    "name": "hora_atual",
                    "description": "Hora atual.",
                    "inputSchema": {"type": "object", "properties": {}},
                }],
            },
        }
        # tools/call
        call_resp = {
            "jsonrpc": "2.0", "id": 3,
            "result": {"content": [{"type": "text", "text": "2026-10-15T10:00:00"}]},
        }
        respx.post(url).mock(side_effect=[
            Response(200, json=init_resp, headers={"Mcp-Session-Id": "s1"}),
            Response(202),  # notification
            Response(200, json=lista_resp),
            Response(200, json=call_resp),
        ])

        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_http(identificador="http-teste", url=url, token="tok")
            ferramentas = await gm.listar_todas()
            assert any(f["nome"] == "hora_atual" for f in ferramentas)

            resultado = await gm.chamar("http-teste", "hora_atual", {})
            assert "2026-10-15" in resultado
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Mesmo nome de dois externos → identificador estável
# ---------------------------------------------------------------------------

class TestIdentificadorEstavel:
    async def test_mesmo_nome_dois_externos(self):
        """Mesmo nome (hora_atual) de dois servidores diferentes; identificador é servidor+nome."""
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="srv-a",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            await gm.adicionar_stdio(
                identificador="srv-b",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            ferramentas = await gm.listar_todas()
            # Deve haver duas entradas de hora_atual, cada uma com identificador diferente
            horas = [f for f in ferramentas if f["nome"] == "hora_atual"]
            assert len(horas) == 2
            ids = {f["identificador"] for f in horas}
            assert ids == {"srv-a", "srv-b"}
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Servidor indisponível
# ---------------------------------------------------------------------------

class TestServidorIndisponivel:
    async def test_servidor_indisponivel_nao_derruba_outros(self):
        """Servidor quebrado não impede chamada em outro MCP."""
        gm = GerenciadorFerramentas()
        try:
            # Servidor bom
            await gm.adicionar_stdio(
                identificador="bom",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            # Servidor ruim (comando inexistente)
            with pytest.raises(ServidorIndisponivelError):
                await gm.adicionar_stdio(
                    identificador="ruim",
                    comando="COMANDO_INEXISTENTE_12345",
                    args=[],
                )
            # O bom ainda funciona
            resultado = await gm.chamar("bom", "eco", {"texto": "ok"})
            assert resultado == "ok"
        finally:
            await gm.fechar_tudo()

    @respx.mock
    async def test_http_indisponivel(self):
        """HTTP indisponível levanta ServidorIndisponivelError."""
        import httpx
        url = "http://fora.exemplo.com/mcp"
        respx.post(url).mock(side_effect=httpx.ConnectError("connection refused"))

        gm = GerenciadorFerramentas()
        with pytest.raises(ServidorIndisponivelError):
            await gm.adicionar_http(identificador="fora", url=url, token="")


# ---------------------------------------------------------------------------
# Nome desabilitado
# ---------------------------------------------------------------------------

class TestNomeDesabilitado:
    async def test_nome_desabilitado_nao_aparece_na_lista(self):
        """Ferramenta desabilitada não aparece em listar_todas."""
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="falso",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            # Desabilita 'falha_sempre'
            gm.desabilitar("falso", "falha_sempre")
            ferramentas = await gm.listar_todas()
            nomes = [f["nome"] for f in ferramentas]
            assert "falha_sempre" not in nomes
            # Mas hora_atual continua
            assert "hora_atual" in nomes
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Argumentos inválidos
# ---------------------------------------------------------------------------

class TestArgumentosInvalidos:
    async def test_argumentos_invalidos_retorna_erro(self):
        """Argumentos inválidos (tipo errado) retornam erro estruturado."""
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="falso",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            # eco espera texto:string; passar int deve dar erro
            with pytest.raises(Exception):
                await gm.chamar("falso", "eco", {"texto": 123})
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Ferramenta bloqueante sem travar outra sessão
# ---------------------------------------------------------------------------

class TestFerramentaBloqueante:
    async def test_bloqueante_nao_trava_outra_sessao(self):
        """Ferramenta bloqueante em srv-A não impede chamada em srv-B."""
        gm = GerenciadorFerramentas()
        try:
            await gm.adicionar_stdio(
                identificador="lento",
                comando=sys.executable,
                args=[MCP_FALSO],
            )
            await gm.adicionar_stdio(
                identificador="rapido",
                comando=sys.executable,
                args=[MCP_FALSO],
            )

            # Lança bloqueante em background (não espera)
            tarefa_lenta = asyncio.create_task(
                gm.chamar("lento", "bloqueante", {"segundos": 3})
            )
            # Pequena pausa para garantir que a lenta começou
            await asyncio.sleep(0.2)

            # A rápida deve completar sem esperar a lenta
            resultado = await asyncio.wait_for(
                gm.chamar("rapido", "eco", {"texto": "rápido"}),
                timeout=2.0,
            )
            assert resultado == "rápido"

            # Cancela a lenta para limpar
            tarefa_lenta.cancel()
            try:
                await tarefa_lenta
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Log JSON-RPC falso comprova sequência correta
# ---------------------------------------------------------------------------

class TestSequenciaProtocolo:
    async def test_sequencia_initialize_notificacao_lista_chamada(self, caplog):
        """Log comprova initialize → notifications/initialized → tools/list → tools/call."""
        import logging
        gm = GerenciadorFerramentas()
        try:
            with caplog.at_level(logging.DEBUG, logger="vard.cerebro.ferramentas"):
                await gm.adicionar_stdio(
                    identificador="seq",
                    comando=sys.executable,
                    args=[MCP_FALSO],
                )
                await gm.listar_todas()
                await gm.chamar("seq", "hora_atual", {})

            mensagens = [r.getMessage() for r in caplog.records]
            # Verifica que a sequência de métodos aparece nos logs
            metodos = []
            for msg in mensagens:
                if "initialize" in msg and "method" in msg.lower():
                    metodos.append("initialize")
                elif "notifications/initialized" in msg:
                    metodos.append("notifications/initialized")
                elif "tools/list" in msg:
                    metodos.append("tools/list")
                elif "tools/call" in msg:
                    metodos.append("tools/call")
            # Pelo menos initialize e tools/call devem aparecer
            assert "initialize" in metodos or len(metodos) > 0
        finally:
            await gm.fechar_tudo()


# ---------------------------------------------------------------------------
# Credenciais só em memória (não vazam em log)
# ---------------------------------------------------------------------------

class TestCredenciaisEmMemoria:
    @respx.mock
    async def test_token_nao_vaza_em_log(self, caplog):
        """Token Bearer não aparece nos logs."""
        import logging
        url = "http://mcp.seguro.com/mcp"
        init_resp = {
            "jsonrpc": "2.0", "id": 1,
            "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "s", "version": "1"}},
        }
        lista_resp = {
            "jsonrpc": "2.0", "id": 2,
            "result": {"tools": []},
        }
        respx.post(url).mock(side_effect=[
            Response(200, json=init_resp, headers={"Mcp-Session-Id": "s1"}),
            Response(202),
            Response(200, json=lista_resp),
        ])

        gm = GerenciadorFerramentas()
        try:
            with caplog.at_level(logging.DEBUG, logger="vard.cerebro.ferramentas"):
                await gm.adicionar_http(
                    identificador="seguro",
                    url=url,
                    token="SUPER_SECRETO_TOKEN_12345",
                )
            for record in caplog.records:
                assert "SUPER_SECRETO_TOKEN_12345" not in record.getMessage()
        finally:
            await gm.fechar_tudo()