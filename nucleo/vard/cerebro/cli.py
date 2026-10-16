"""Adaptador de CLI como cérebro (T15 da 0.8): dialetos stream-json → eventos do cérebro.

Contratos (plano 0.8 T15 / spec C13-C14 / docs/cli.md da T13):
- Dialeto: linha_usuario/interpretar/ferramentas_iniciais; DIALETOS = claude e agy.
- AdaptadorCli(AdaptadorProvedor) recebe um canal injetável (enviar/linhas/interromper);
  o processo real vem da T16 (SupervisorCli).
- Ferramentas rodam dentro da CLI: cada uso vira evento informativo 'ferramenta',
  nunca 'chamada' executada pelo núcleo (C14).
- Cancelamento chama canal.interromper() e encerra o turno (C13).
- Prazos injetáveis: sem evento útil em prazo_evento (15 s) ou turno acima de
  prazo_turno (180 s) viram ErroProvedor('cli_tempo'); stream sem resultado vira
  'cli_caiu'; erro de login vira 'cli_sem_login'.
- Erros têm mensagem curta fixa, sem segredo nem caminho (ver
  test_erro_sem_segredo_nem_caminho).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from typing import Any, AsyncIterator, List, Optional, Protocol, runtime_checkable

from .provedores import AdaptadorProvedor, ErroProvedor, EventoInferencia

log = logging.getLogger(__name__)

PRAZO_EVENTO_CLI = 15.0
PRAZO_TURNO_CLI = 180.0

_EPSILON = 1e-6


@runtime_checkable
class Dialeto(Protocol):
    """Envelope de uma CLI em stream-json (entrada e saída)."""

    def linha_usuario(self, texto: str) -> str:
        ...

    def interpretar(self, linha: str) -> List[EventoInferencia]:
        ...

    def ferramentas_iniciais(self, linha: str) -> Optional[List[str]]:
        ...


@runtime_checkable
class CanalCli(Protocol):
    """Canal de uma CLI viva: escrever turno, ler linhas, interromper (T16 fornece o real).

    linhas() devolve um iterador estável: cada chamada de __anext__ lê a sequência
    do stream sem perder linhas, mesmo sendo chamadas uma a uma em tarefas soltas.
    """

    async def enviar(self, linha: str) -> None:
        ...

    def linhas(self) -> AsyncIterator[str]:
        ...

    async def interromper(self) -> None:
        ...


def _parsear(linha: str) -> Optional[dict]:
    """Linha NDJSON → dict; vazio/banner/não-JSON viram None e são ignorados."""
    texto = linha.strip()
    if not texto:
        return None
    try:
        obj = json.loads(texto)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _eh_erro_de_login(texto: str) -> bool:
    baixo = texto.lower()
    return "auth" in baixo or "login" in baixo or "401" in baixo


def _erro_resultado_cli(status: Optional[int], texto: Optional[str]) -> tuple[str, bool, str]:
    """Erro de resultado da CLI → (codigo, recuperavel, detalhe curto sem ecoar a saída)."""
    bruto = texto or ""
    if status == 401 or _eh_erro_de_login(bruto):
        return "cli_sem_login", True, "CLI sem login"
    return "cli_erro", True, "CLI devolveu erro no turno"


class DialetoClaude:
    """Claude Code em stream-json: envelope 'type' (docs/cli.md da T13)."""

    def linha_usuario(self, texto: str) -> str:
        return json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": texto}]},
        }, ensure_ascii=False)

    def interpretar(self, linha: str) -> List[EventoInferencia]:
        obj = _parsear(linha)
        if obj is None:
            return []
        tipo = obj.get("type")
        if tipo == "assistant":
            return self._interpretar_assistant(obj.get("message") or {})
        if tipo == "result":
            return self._interpretar_result(obj)
        # init/hook_started/informational ficam fora do laço do cérebro
        return []

    @staticmethod
    def _interpretar_assistant(mensagem: dict) -> List[EventoInferencia]:
        eventos: List[EventoInferencia] = []
        for bloco in mensagem.get("content") or []:
            if not isinstance(bloco, dict):
                continue
            if bloco.get("type") == "text":
                conteudo = bloco.get("text", "")
                if conteudo:
                    eventos.append(EventoInferencia("texto", {"conteudo": conteudo}))
            elif bloco.get("type") == "server_tool_use":
                eventos.append(EventoInferencia("ferramenta", {
                    "id": bloco.get("id", ""),
                    "nome": bloco.get("name", ""),
                    "argumentos": bloco.get("input", {}),
                }))
        return eventos

    @staticmethod
    def _interpretar_result(obj: dict) -> List[EventoInferencia]:
        if obj.get("is_error"):
            raise ErroProvedor(*_erro_resultado_cli(obj.get("api_error_status"), obj.get("result")))
        return [EventoInferencia("fim", {"num_turns": obj.get("num_turns")})]

    def ferramentas_iniciais(self, linha: str) -> Optional[List[str]]:
        obj = _parsear(linha)
        if obj is None or obj.get("type") != "system" or obj.get("subtype") != "init":
            return None
        ferramentas = obj.get("tools")
        if isinstance(ferramentas, list):
            return [str(f) for f in ferramentas]
        return None


class DialetoAgy:
    """Antigravity (agy) em stream-json: envelope 'event' (docs/cli.md da T13)."""

    def linha_usuario(self, texto: str) -> str:
        return json.dumps({
            "event": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": texto}]},
        }, ensure_ascii=False)

    def interpretar(self, linha: str) -> List[EventoInferencia]:
        obj = _parsear(linha)
        if obj is None:
            return []
        evento = obj.get("event")
        if evento == "step_update":
            passo = obj.get("step_update") or {}
            if passo.get("state") == "ACTIVE" and passo.get("step_type") == "agent_response":
                delta = passo.get("text_delta", "")
                return [EventoInferencia("texto", {"conteudo": delta})] if delta else []
            return []
        if evento == "assistant":
            return self._interpretar_assistant(obj.get("message") or {})
        if evento == "result":
            return self._interpretar_result(obj.get("result") or {})
        # init e demais eventos ficam fora do laço do cérebro
        return []

    @staticmethod
    def _interpretar_assistant(mensagem: dict) -> List[EventoInferencia]:
        eventos: List[EventoInferencia] = []
        for bloco in mensagem.get("content") or []:
            if not isinstance(bloco, dict):
                continue
            if bloco.get("type") == "tool_use":
                eventos.append(EventoInferencia("ferramenta", {
                    "id": bloco.get("id", ""),
                    "nome": bloco.get("name", ""),
                    "argumentos": bloco.get("input", {}),
                }))
            elif bloco.get("type") == "text":
                conteudo = bloco.get("text", "")
                if conteudo:
                    eventos.append(EventoInferencia("texto", {"conteudo": conteudo}))
        return eventos

    @staticmethod
    def _interpretar_result(resultado: dict) -> List[EventoInferencia]:
        if str(resultado.get("status", "")).upper() == "ERROR":
            raise ErroProvedor(*_erro_resultado_cli(None, resultado.get("error")))
        return [EventoInferencia("fim", {"num_turns": resultado.get("num_turns")})]

    def ferramentas_iniciais(self, linha: str) -> Optional[List[str]]:
        obj = _parsear(linha)
        if obj is None or obj.get("event") != "init":
            return None
        ferramentas = (obj.get("init") or {}).get("tools")
        if isinstance(ferramentas, list):
            return [str(f) for f in ferramentas]
        return None


DIALETOS = {"claude": DialetoClaude(), "agy": DialetoAgy()}


def _ultimo_texto_usuario(mensagens: Optional[List[dict]]) -> str:
    """Só a última mensagem do usuário: o contexto da conversa é da CLI, não do núcleo."""
    for msg in reversed(mensagens or []):
        if msg.get("role") != "user":
            continue
        conteudo = msg.get("content")
        if isinstance(conteudo, str):
            return conteudo
        if isinstance(conteudo, list):
            partes = [
                bloco.get("text", "")
                for bloco in conteudo
                if isinstance(bloco, dict) and bloco.get("type") == "text"
            ]
            return "".join(partes)
    return ""


class AdaptadorCli(AdaptadorProvedor):
    """Converte o stream NDJSON de uma CLI em eventos do cérebro.

    O canal é injetável (enviar/linhas/interromper); a T16 fornece o canal real
    de um processo vivo. Só a última mensagem do usuário vai para a CLI.
    """

    nome = "cli"

    def __init__(
        self,
        canal: Any,
        dialeto: str | Dialeto,
        *,
        prazo_evento: float = PRAZO_EVENTO_CLI,
        prazo_turno: float = PRAZO_TURNO_CLI,
    ) -> None:
        if isinstance(dialeto, str):
            if dialeto not in DIALETOS:
                raise ValueError(f"dialeto desconhecido: {dialeto!r}")
            dialeto = DIALETOS[dialeto]
        self._canal = canal
        self._dialeto = dialeto
        self._prazo_evento = float(prazo_evento)
        self._prazo_turno = float(prazo_turno)

    async def inferir(
        self,
        mensagens: List[dict],
        ferramentas: Optional[List[dict]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        if imagem is not None:
            raise ErroProvedor("imagem_nao_suportada", False, "CLI nao aceita imagem nesta versao")
        await self._interromper_se_cancelado(cancelamento)
        texto = _ultimo_texto_usuario(mensagens)
        await self._canal.enviar(self._dialeto.linha_usuario(texto))

        aiter_linhas = await self._abrir_linhas()
        inicio = time.monotonic()
        ultimo_util = inicio
        while True:
            agora = time.monotonic()
            idade_turno = agora - inicio
            if idade_turno >= self._prazo_turno - _EPSILON:
                raise ErroProvedor("cli_tempo", True, "turno da CLI acima do prazo")
            idade_util = agora - ultimo_util
            if idade_util >= self._prazo_evento - _EPSILON:
                raise ErroProvedor("cli_tempo", True, "sem evento util da CLI no prazo")
            espera = min(self._prazo_turno - idade_turno, self._prazo_evento - idade_util)
            try:
                linha = await self._esperar_linha(aiter_linhas, cancelamento, espera)
            except asyncio.TimeoutError:
                continue  # o topo do laço decide qual prazo venceu
            if linha is None:
                raise ErroProvedor("cli_caiu", True, "CLI fechou o stream antes do fim do turno")
            eventos = self._dialeto.interpretar(linha)
            if eventos or self._dialeto.ferramentas_iniciais(linha) is not None:
                ultimo_util = time.monotonic()
            for evento in eventos:
                yield evento
                if evento.tipo == "fim":
                    return

    async def _abrir_linhas(self) -> AsyncIterator[str]:
        res = self._canal.linhas()
        if inspect.isawaitable(res):
            res = await res
        return res.__aiter__()

    async def _esperar_linha(
        self,
        aiter_linhas: AsyncIterator[str],
        cancelamento: Optional[asyncio.Event],
        espera: float,
    ) -> Optional[str]:
        """Próxima linha, ou None se o stream fechou. TimeoutError se o prazo venceu."""
        tarefa_linha = asyncio.ensure_future(aiter_linhas.__anext__())
        tarefas: set[asyncio.Task] = {tarefa_linha}
        tarefa_cancel: Optional[asyncio.Task] = None
        if cancelamento is not None:
            tarefa_cancel = asyncio.ensure_future(cancelamento.wait())
            tarefas.add(tarefa_cancel)
        try:
            prontas, _ = await asyncio.wait(tarefas, timeout=espera, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            for tarefa in tarefas:
                tarefa.cancel()
            raise
        if tarefa_cancel is not None and tarefa_cancel in prontas and tarefa_cancel.result():
            tarefa_linha.cancel()
            await self._canal.interromper()
            raise asyncio.CancelledError()
        if tarefa_linha in prontas:
            try:
                return tarefa_linha.result()
            except StopAsyncIteration:
                return None
        for tarefa in tarefas:
            tarefa.cancel()
        raise asyncio.TimeoutError()

    async def _interromper_se_cancelado(self, cancelamento: Optional[asyncio.Event]) -> None:
        if cancelamento is not None and cancelamento.is_set():
            await self._canal.interromper()
            raise asyncio.CancelledError()
