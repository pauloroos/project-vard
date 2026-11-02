"""Gerenciador de ferramentas do cérebro: registra funções internas e conecta MCPs externos.
Contrato mínimo (plano T3):
- ``adicionar_stdio(identificador, comando, args)`` lança subprocesso MCP via stdio.
- ``adicionar_http(identificador, url, token)`` conecta MCP via Streamable HTTP.
- ``listar_todas()`` devolve lista de ferramentas habilitadas com identificador estável.
- ``chamar(identificador, nome, argumentos)`` executa ferramenta e devolve texto.
- ``desabilitar(identificador, nome)`` remove ferramenta da lista sem desconectar servidor.
- ``fechar_tudo()`` encerra todos os subprocessos e conexões; usado em finally.
Credenciais só em memória; log sanitizado. Servidor quebrado não derruba outros.
Ferramenta bloqueante não trava outra sessão (cada chamada é independente).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Exceções
# ------------------------------------------------------------------------
class ServidorIndisponivelError(Exception):
    """Servidor MCP não pôde ser iniciado ou conectado."""


class FerramentaBloqueanteError(Exception):
    """Ferramenta bloqueou além do timeout permitido."""


# -------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------
def _sem_segredo(texto: str) -> str:
    """Sanitiza tokens/keys de logs."""
    texto = re.sub(r"(Bearer\s+)\S+", r"\1***", texto, flags=re.IGNORECASE)
    texto = re.sub(r'(api[_-]?key["\s:=]+)\S+', r"\1***", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(token[=:]\s*)\S+", r"\1***", texto, flags=re.IGNORECASE)
    return texto


# -------------------------------------------------------------------------
# Cliente MCP stdio (subprocesso JSON-RPC sobre stdin/stdout)
# ------------------------------------------------------------------------
class _ClienteStdio:
    """Cliente MCP via stdio: lança subprocesso e comunica por JSON-RPC newline-delimited."""

    def __init__(self, identificador: str, comando: str, args: List[str]) -> None:
        self.identificador = identificador
        self._comando = comando
        self._args = args
        self._process: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._ferramentas: List[Dict[str, Any]] = []
        self._desabilitados: set[str] = set()
        self._trava_rpc = asyncio.Lock()
        self._dreno_stderr: asyncio.Task | None = None

    async def iniciar(self) -> None:
        """Lança subprocesso e faz handshake MCP."""
        from vard.instalaveis import ambiente_limpo
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._comando, *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=ambiente_limpo(),
                limit=16 * 1024 * 1024,  # tools/list de um MCP grande passa fácil de 64 KB (padrão do asyncio)
            )
        except (OSError, FileNotFoundError) as exc:
            raise ServidorIndisponivelError(
                f"não foi possível iniciar {self._comando}: {exc}"
            ) from exc

        if getattr(self._process, "stderr", None) is not None:
            self._dreno_stderr = asyncio.create_task(self._drenar_stderr())
        # initialize
        init_result = await self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "vard-cerebro", "version": "1"},
        })
        log.debug("MCP stdio [%s] initialize ok: %s", self.identificador, _sem_segredo(str(init_result)[:200]))

        # notifications/initialized (sem resposta esperada)
        await self._notify("notifications/initialized")
        log.debug("MCP stdio [%s] notifications/initialized enviado", self.identificador)

        # tools/list
        result = await self._rpc("tools/list")
        self._ferramentas = result.get("tools", [])
        log.debug("MCP stdio [%s] tools/list: %d ferramentas", self.identificador, len(self._ferramentas))

    async def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Sessões diferentes compartilham o servidor, mas nunca o leitor do stdio.
        async with self._trava_rpc:
            return await asyncio.wait_for(self._rpc_serial(method, params), timeout=60)

    async def _drenar_stderr(self) -> None:
        """Descarta diagnóstico do subprocesso: evita bloqueio e não registra dados locais."""
        while self._process is not None and await self._process.stderr.read(4096):
            pass

    async def _rpc_serial(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Envia request JSON-RPC e aguarda response com mesmo id."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise ServidorIndisponivelError(f"processo {self.identificador} não está ativo")
        self._id += 1
        msg_id = self._id
        request = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        linha = json.dumps(request, ensure_ascii=False) + "\n"
        log.debug("MCP stdio [%s] → %s", self.identificador, _sem_segredo(linha.strip()[:300]))
        self._process.stdin.write(linha.encode("utf-8"))
        await self._process.stdin.drain()

        # Lê respostas até encontrar a com nosso id
        while True:
            raw = await self._process.stdout.readline()
            if not raw:
                raise ServidorIndisponivelError(f"processo {self.identificador} fechou stdout")
            texto = raw.decode("utf-8").strip()
            if not texto:
                continue
            log.debug("MCP stdio [%s] ← %s", self.identificador, _sem_segredo(texto[:300]))
            try:
                resp = json.loads(texto)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise ServidorIndisponivelError(
                        f"MCP {self.identificador}: {resp['error']}"
                    )
                return resp.get("result", {})

    async def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Envia notification JSON-RPC (sem id, sem resposta)."""
        if self._process is None or self._process.stdin is None:
            raise ServidorIndisponivelError(f"processo {self.identificador} não está ativo")
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        linha = json.dumps(msg, ensure_ascii=False) + "\n"
        log.debug("MCP stdio [%s] → notify %s", self.identificador, method)
        self._process.stdin.write(linha.encode("utf-8"))
        await self._process.stdin.drain()

    async def chamar(self, nome: str, argumentos: Dict[str, Any]) -> str:
        """Chama tools/call e devolve texto do resultado."""
        result = await self._rpc("tools/call", {"name": nome, "arguments": argumentos})
        if result.get("isError"):
            conteudo = result.get("content", [])
            texto_erro = "".join(c.get("text", "") for c in conteudo if isinstance(c, dict))
            raise RuntimeError(texto_erro or "erro na ferramenta")
        conteudo = result.get("content", [])
        return "".join(c.get("text", "") for c in conteudo if isinstance(c, dict))

    def listar_ferramentas(self) -> List[Dict[str, Any]]:
        """Devolve ferramentas habilitadas (exclui desabilitados)."""
        return [
            f for f in self._ferramentas
            if f.get("name") not in self._desabilitados
        ]

    def desabilitar(self, nome: str) -> None:
        self._desabilitados.add(nome)

    async def fechar(self) -> None:
        """Encerra subprocesso."""
        if self._process is not None:
            try:
                if self._process.stdin is not None:
                    self._process.stdin.close()
                    try:
                        await self._process.stdin.wait_closed()
                    except (OSError, BrokenPipeError, ConnectionResetError):
                        pass
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()
            except ProcessLookupError:
                pass
            self._process = None
            if self._dreno_stderr is not None:
                self._dreno_stderr.cancel()
                await asyncio.gather(self._dreno_stderr, return_exceptions=True)
                self._dreno_stderr = None
            log.debug("MCP stdio [%s] processo encerrado", self.identificador)


# -------------------------------------------------------------------------
# Cliente MCP HTTP (Streamable HTTP via mcp_http.ClienteMCP)
# ------------------------------------------------------------------------
class _ClienteHTTP:
    """Wrapper assíncrono sobre mcp_http.ClienteMCP para uso no GerenciadorFerramentas."""

    def __init__(self, identificador: str, url: str, token: str) -> None:
        self.identificador = identificador
        self._url = url
        self._token = token
        self._cliente: Any = None
        self._ferramentas: List[Dict[str, Any]] = []
        self._desabilitados: set[str] = set()

    async def iniciar(self) -> None:
        """Conecta e faz handshake via HTTP."""
        from vard.mcp_http import ClienteMCP, ErroMCP

        self._cliente = ClienteMCP(self._url, self._token)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._cliente.iniciar)
            log.debug("MCP HTTP [%s] initialize ok", self.identificador)
            ferramentas_raw = await loop.run_in_executor(None, self._cliente.listar_ferramentas)
            self._ferramentas = ferramentas_raw
            log.debug("MCP HTTP [%s] tools/list: %d ferramentas", self.identificador, len(self._ferramentas))
        except ErroMCP as exc:
            raise ServidorIndisponivelError(
                f"MCP HTTP {self.identificador}: {exc}"
            ) from exc

    async def chamar(self, nome: str, argumentos: Dict[str, Any]) -> str:
        from vard.mcp_http import ErroMCP

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._cliente.chamar, nome, argumentos)
        except ErroMCP as exc:
            raise RuntimeError(str(exc)) from exc

    def listar_ferramentas(self) -> List[Dict[str, Any]]:
        return [
            f for f in self._ferramentas
            if f.get("name") not in self._desabilitados
        ]

    def desabilitar(self, nome: str) -> None:
        self._desabilitados.add(nome)

    async def fechar(self) -> None:
        # ClienteMCP HTTP não mantém conexão persistente; nada a fechar
        self._cliente = None
        log.debug("MCP HTTP [%s] desconectado", self.identificador)


# -------------------------------------------------------------------------
# GerenciadorFerramentas
# ------------------------------------------------------------------------
class GerenciadorFerramentas:
    """Registra e gerencia ferramentas internas e MCPs externos."""

    def __init__(self) -> None:
        self._clientes: Dict[str, _ClienteStdio | _ClienteHTTP] = {}
        self._processos: Dict[str, asyncio.subprocess.Process] = {}
        self._internas: Dict[str, Dict[str, Any]] = {}

    def registrar_interna(
        self,
        nome: str,
        fn: Callable[..., Any],
        descricao: str = "",
        schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra função interna como ferramenta do cérebro."""
        self._internas[nome] = {
            "nome": nome,
            "fn": fn,
            "descricao": descricao,
            "schema": schema or {"type": "object", "properties": {}},
            "identificador": "interno",
        }

    async def chamar_interna(self, nome: str, argumentos: Dict[str, Any]) -> str:
        """Chama ferramenta interna registrada."""
        entrada = self._internas.get(nome)
        if entrada is None:
            raise ValueError(f"ferramenta interna desconhecida: {nome}")
        fn = entrada["fn"]
        loop = asyncio.get_running_loop()
        try:
            resultado = await loop.run_in_executor(None, lambda: fn(**argumentos))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)[:200]) from exc
        return str(resultado) if resultado is not None else ""

    async def adicionar_stdio(
        self,
        identificador: str,
        comando: str,
        args: List[str],
    ) -> None:
        """Adiciona servidor MCP via stdio."""
        cliente = _ClienteStdio(identificador, comando, args)
        try:
            await asyncio.wait_for(cliente.iniciar(), timeout=15)
        except BaseException:
            await cliente.fechar()
            raise
        self._clientes[identificador] = cliente
        if cliente._process is not None:
            self._processos[identificador] = cliente._process

    async def adicionar_http(
        self,
        identificador: str,
        url: str,
        token: str = "",
    ) -> None:
        """Adiciona servidor MCP via Streamable HTTP."""
        cliente = _ClienteHTTP(identificador, url, token)
        await cliente.iniciar()
        self._clientes[identificador] = cliente

    async def listar_todas(self) -> List[Dict[str, Any]]:
        """Lista todas as ferramentas habilitadas (internas + MCPs externos)."""
        resultado: List[Dict[str, Any]] = []
        # Ferramentas internas primeiro
        for entrada in self._internas.values():
            resultado.append(dict(entrada))
        # Depois MCPs externos
        for identificador, cliente in self._clientes.items():
            for f in cliente.listar_ferramentas():
                entrada = dict(f)
                # Normaliza chave "name" do protocolo MCP para "nome"
                if "name" in entrada and "nome" not in entrada:
                    entrada["nome"] = entrada.pop("name")
                entrada["identificador"] = identificador
                resultado.append(entrada)
        return resultado

    async def chamar(
        self,
        identificador: str,
        nome: str,
        argumentos: Dict[str, Any],
    ) -> str:
        """Chama ferramenta pelo identificador do servidor + nome."""
        if identificador == "interno":
            return await self.chamar_interna(nome, argumentos)
        cliente = self._clientes.get(identificador)
        if cliente is None:
            raise ValueError(f"servidor desconhecido: {identificador}")
        log.debug("tools/call [%s] %s args=%s", identificador, nome, _sem_segredo(str(argumentos)[:200]))
        return await cliente.chamar(nome, argumentos)

    def desabilitar(self, identificador: str, nome: str) -> None:
        """Desabilita ferramenta específica de um servidor."""
        cliente = self._clientes.get(identificador)
        if cliente is not None:
            cliente.desabilitar(nome)

    async def fechar_tudo(self) -> None:
        """Encerra todos os subprocessos e conexões."""
        for identificador, cliente in list(self._clientes.items()):
            try:
                await cliente.fechar()
            except Exception:  # noqa: BLE001
                log.warning("erro ao fechar MCP [%s]", identificador, exc_info=True)
        self._clientes.clear()
        self._processos.clear()
