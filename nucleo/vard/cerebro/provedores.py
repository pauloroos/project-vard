"""Adaptadores reais de provedores para o Vard 0.8 Parte A.

Contratos:
    AdaptadorProvedor(abc.ABC) -- base abstrata com inferir() assincrono.
    EventoInferencia(tipo, dados) -- evento de streaming.
    ErroProvedor(codigo, recuperavel, detalhe) -- excecao estruturada.

Adaptadores concretos:
    AdaptadorOpenAICompat -- LM Studio, llama-server, qualquer /v1/chat/completions.
    AdaptadorOpenAINativo -- OpenAI oficial com suporte a imagem (vision).
    AdaptadorAnthropic -- Anthropic Messages API nativa.
    AdaptadorGoogle -- Google Gemini generateContent nativo.
"""
from __future__ import annotations

import abc
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Contratos
# ------------------------------------------------------------------------

@dataclass(frozen=True)
class EventoInferencia:
    """Evento emitido pelo stream de inferencia."""
    tipo: str  # 'texto' | 'chamada' | 'fim'
    dados: Dict[str, Any] = field(default_factory=dict)


class ErroProvedor(Exception):
    """Erro estruturado de provedor."""
    def __init__(self, codigo: str, recuperavel: bool, detalhe: str) -> None:
        self.codigo = codigo
        self.recuperavel = recuperavel
        self.detalhe = detalhe
        super().__init__(f"[{codigo}] {detalhe}")


class AdaptadorProvedor(abc.ABC):
    """Base abstrata para adaptadores de provedores."""

    @abc.abstractmethod
    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        """Executa inferencia em streaming."""
        ...
        yield  # pragma: no cover


# -------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------

def _sem_segredo(texto: str) -> str:
    """Sanitiza tokens/keys de logs."""
    texto = re.sub(r"(Bearer\s+)\S+", r"\1***", texto, flags=re.IGNORECASE)
    texto = re.sub(r'(api[_-]?key["\s:=]+)\S+', r"\1***", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(key=)[^&\s]+", r"\1***", texto, flags=re.IGNORECASE)
    return texto


def _verificar_cancelamento(cancelamento: Optional[asyncio.Event]) -> None:
    if cancelamento and cancelamento.is_set():
        raise asyncio.CancelledError()


async def _stream_http(
    metodo: str,
    url: str,
    *,
    headers: Dict[str, str],
    json_body: Dict[str, Any],
    timeout: float,
    cancelamento: Optional[asyncio.Event],
    trust_env: bool = True,
) -> AsyncIterator[str]:
    """Stream SSE/NDJSON; levanta ErroProvedor em falhas HTTP."""
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=trust_env) as cliente:
            async with cliente.stream(metodo, url, json=json_body, headers=headers) as resp:
                if resp.status_code == 401:
                    raise ErroProvedor("auth_401", False, "credencial recusada")
                if resp.status_code == 429:
                    raise ErroProvedor("rate_429", True, "limite de taxa")
                if resp.status_code >= 500:
                    raise ErroProvedor("servidor_5xx", True, f"HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    raise ErroProvedor("http_erro", False, f"HTTP {resp.status_code}")
                async for linha in resp.aiter_lines():
                    _verificar_cancelamento(cancelamento)
                    yield linha
    except asyncio.CancelledError:
        raise
    except httpx.TimeoutException as exc:
        raise ErroProvedor("timeout", True, str(exc)) from exc
    except httpx.ConnectError as exc:
        raise ErroProvedor("conexao", True, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ErroProvedor("rede", True, type(exc).__name__) from exc


# -------------------------------------------------------------------------
# AdaptadorOpenAICompat -- LM Studio, llama-server, OpenAI-compativel
# -------------------------------------------------------------------------

class AdaptadorOpenAICompat(AdaptadorProvedor):
    """LM Studio, llama-server e qualquer endpoint OpenAI-compativel.
    Usa /v1/chat/completions com stream=True; suporta tool calls fragmentadas.
    URL com prefixo respeitada. Credencial via Bearer token.
    Imagem levanta ErroProvedor('imagem_nao_suportada').
    """

    def __init__(
        self,
        base_url: str,
        modelo: str,
        chave: str = "",
        timeout: float = 90.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._modelo = modelo
        self._chave = chave
        self._timeout = timeout

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        if imagem is not None:
            raise ErroProvedor(
                "imagem_nao_suportada", False,
                "openai_compat nao aceita imagem nesta versao",
            )

        url = f"{self._base}/v1/chat/completions"
        corpo: Dict[str, Any] = {"model": self._modelo, "messages": mensagens, "stream": True}
        if ferramentas:
            corpo["tools"] = ferramentas

        cabecalhos: Dict[str, str] = {"Content-Type": "application/json"}
        if self._chave:
            cabecalhos["Authorization"] = f"Bearer {self._chave}"

        log.debug("OpenAICompat POST %s model=%s", _sem_segredo(url), self._modelo)

        chamadas_parciais: Dict[int, Dict[str, Any]] = {}
        chamadas_emitidas: set[int] = set()
        concluido = False

        async for linha in _stream_http(
            "POST", url,
            headers=cabecalhos, json_body=corpo,
            timeout=self._timeout, cancelamento=cancelamento,
        ):
            if not linha.startswith("data:"):
                continue
            payload = linha[5:].strip()
            if payload == "[DONE]":
                concluido = True
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                log.warning("JSON invalido ignorado no stream OpenAI: %s", _sem_segredo(payload[:200]))
                continue

            escolhas = chunk.get("choices") or []
            if not escolhas:
                continue
            delta = escolhas[0].get("delta") or {}

            conteudo = delta.get("content")
            if conteudo:
                yield EventoInferencia("texto", {"conteudo": conteudo})

            tc_list = delta.get("tool_calls")
            if tc_list:
                for tc in tc_list:
                    idx = tc.get("index", 0)
                    if idx not in chamadas_parciais:
                        chamadas_parciais[idx] = {
                            "id": tc.get("id", ""),
                            "nome": (tc.get("function") or {}).get("name", ""),
                            "argumentos": "",
                        }
                    parcial = chamadas_parciais[idx]
                    if tc.get("id"):
                        parcial["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        parcial["nome"] = fn["name"]
                    if fn.get("arguments"):
                        parcial["argumentos"] += fn["arguments"]

            # Emite chamadas completas somente se argumentos forem JSON valido
            # e ainda nao foram emitidas (evita duplicacao a cada chunk)
            for idx in sorted(chamadas_parciais.keys()):
                if idx in chamadas_emitidas:
                    continue
                parcial = chamadas_parciais[idx]
                args_str = parcial["argumentos"]
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    continue
                chamadas_emitidas.add(idx)
                yield EventoInferencia("chamada", {
                    "id": parcial["id"],
                    "nome": parcial["nome"],
                    "argumentos": args,
                })

        if not concluido:
            raise ErroProvedor("sse_interrompido", True, "fluxo sem marcador final")

        # Emite chamadas pendentes que so fecharam apos o fim do stream
        for idx in sorted(chamadas_parciais.keys()):
            if idx in chamadas_emitidas:
                continue
            parcial = chamadas_parciais[idx]
            args_str = parcial["argumentos"]
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                log.warning(
                    "Tool call com argumentos invalidos ignorada: %s",
                    _sem_segredo(args_str[:200]),
                )
                continue
            yield EventoInferencia("chamada", {
                "id": parcial["id"],
                "nome": parcial["nome"],
                "argumentos": args,
            })

        yield EventoInferencia("fim", {})


# -------------------------------------------------------------------------
# AdaptadorOpenAINativo -- api.openai.com com visao
# -------------------------------------------------------------------------

class AdaptadorOpenAINativo(AdaptadorProvedor):
    """OpenAI API nativa. Mesma rota compativel mas com suporte a imagem."""

    def __init__(
        self,
        chave: str,
        modelo: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com",
        timeout: float = 90.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._modelo = modelo
        self._chave = chave
        self._timeout = timeout

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        msgs = list(mensagens)
        if imagem is not None:
            msgs.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagem}"}},
                ],
            })

        compat = AdaptadorOpenAICompat(self._base, self._modelo, self._chave, self._timeout)
        async for ev in compat.inferir(msgs, ferramentas, None, cancelamento):
            yield ev


# -------------------------------------------------------------------------
# AdaptadorAnthropic -- Messages API nativa
# -------------------------------------------------------------------------

class AdaptadorAnthropic(AdaptadorProvedor):
    """Anthropic Messages API nativa. POST /v1/messages com x-api-key."""

    def __init__(
        self,
        chave: str,
        modelo: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._modelo = modelo
        self._chave = chave
        self._timeout = timeout

    @staticmethod
    def _converter_mensagens(
        mensagens: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        system_text = ""
        msgs_ant: List[Dict[str, Any]] = []
        for m in mensagens:
            role = m.get("role", "")
            if role == "system":
                system_text += (m.get("content") or "") + "\n"
            elif role == "user":
                msgs_ant.append({"role": "user", "content": m.get("content", "")})
            elif role == "assistant":
                content_parts: List[Dict[str, Any]] = []
                if m.get("content"):
                    content_parts.append({"type": "text", "text": m["content"]})
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        content_parts.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "input": args,
                        })
                msgs_ant.append({
                    "role": "assistant",
                    "content": content_parts or [{"type": "text", "text": ""}],
                })
            elif role == "tool":
                msgs_ant.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }],
                })
        return system_text.strip(), msgs_ant

    @staticmethod
    def _converter_ferramentas(
        ferramentas: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        tools_ant: List[Dict[str, Any]] = []
        for t in ferramentas:
            fn = t.get("function", {})
            tools_ant.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return tools_ant

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        if imagem is not None:
            raise ErroProvedor(
                "imagem_nao_suportada", False,
                "anthropic: imagem requer formatacao especifica nao implementada",
            )

        system_text, msgs_ant = self._converter_mensagens(mensagens)
        corpo: Dict[str, Any] = {
            "model": self._modelo,
            "max_tokens": 4096,
            "messages": msgs_ant,
            "stream": True,
        }
        if system_text:
            corpo["system"] = system_text
        if ferramentas:
            corpo["tools"] = self._converter_ferramentas(ferramentas)

        cabecalhos = {
            "Content-Type": "application/json",
            "x-api-key": self._chave,
            "anthropic-version": "2023-06-01",
        }
        url = f"{self._base}/v1/messages"
        log.debug("Anthropic POST %s model=%s", _sem_segredo(url), self._modelo)

        tc_atual: Optional[Dict[str, Any]] = None

        async for linha in _stream_http(
            "POST", url,
            headers=cabecalhos, json_body=corpo,
            timeout=self._timeout, cancelamento=cancelamento,
        ):
            if not linha.startswith("data:"):
                continue
            payload = linha[5:].strip()
            if not payload:
                continue
            try:
                evento = json.loads(payload)
            except json.JSONDecodeError:
                log.warning("Chunk Anthropic JSON invalido: %s", _sem_segredo(payload[:200]))
                continue

            tipo_evento = evento.get("type", "")

            if tipo_evento == "content_block_start":
                cb = evento.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tc_atual = {
                        "id": cb.get("id", ""),
                        "nome": cb.get("name", ""),
                        "_args_raw": "",
                    }

            elif tipo_evento == "content_block_delta":
                delta = evento.get("delta", {})
                delta_type = delta.get("type", "")
                if delta_type == "text_delta":
                    txt = delta.get("text", "")
                    if txt:
                        yield EventoInferencia("texto", {"conteudo": txt})
                elif delta_type == "input_json_delta":
                    if tc_atual is not None:
                        tc_atual["_args_raw"] += delta.get("partial_json", "")

            elif tipo_evento == "content_block_stop":
                if tc_atual is not None:
                    args_raw = tc_atual.get("_args_raw", "")
                    try:
                        argumentos = json.loads(args_raw) if args_raw else {}
                    except json.JSONDecodeError:
                        log.warning(
                            "Tool call Anthropic com args invalidos ignorada: %s",
                            _sem_segredo(args_raw[:200]),
                        )
                        tc_atual = None
                        continue
                    yield EventoInferencia("chamada", {
                        "id": tc_atual["id"],
                        "nome": tc_atual["nome"],
                        "argumentos": argumentos,
                    })
                    tc_atual = None

            elif tipo_evento == "message_stop":
                break

        yield EventoInferencia("fim", {})


# -------------------------------------------------------------------------
# AdaptadorGoogle -- Gemini API nativa
# -------------------------------------------------------------------------

class AdaptadorGoogle(AdaptadorProvedor):
    """Google Gemini API nativa.
    POST /v1beta/models/{model}:streamGenerateContent?key={chave}.
    """

    def __init__(
        self,
        chave: str,
        modelo: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._modelo = modelo
        self._chave = chave
        self._timeout = timeout

    @staticmethod
    def _converter_mensagens(
        mensagens: List[Dict[str, Any]],
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        system_instruction: Optional[str] = None
        contents: List[Dict[str, Any]] = []
        for msg in mensagens:
            role = msg.get("role", "")
            conteudo = msg.get("content", "")
            if role == "system":
                texto = conteudo if isinstance(conteudo, str) else str(conteudo)
                system_instruction = (
                    texto if system_instruction is None
                    else f"{system_instruction}\n{texto}"
                )
                continue
            if role == "user":
                if isinstance(conteudo, str):
                    parts = [{"text": conteudo}]
                elif isinstance(conteudo, list):
                    parts = []
                    for bloco in conteudo:
                        if isinstance(bloco, dict):
                            if bloco.get("type") == "text":
                                parts.append({"text": bloco.get("text", "")})
                            elif bloco.get("type") == "image_url":
                                url_img = bloco.get("image_url", {}).get("url", "")
                                if url_img.startswith("data:"):
                                    partes_uri = url_img.split(",", 1)
                                    if len(partes_uri) == 2:
                                        header = partes_uri[0]
                                        mime = "image/png"
                                        if "image/jpeg" in header:
                                            mime = "image/jpeg"
                                        elif "image/webp" in header:
                                            mime = "image/webp"
                                        parts.append({
                                            "inline_data": {
                                                "mime_type": mime,
                                                "data": partes_uri[1],
                                            }
                                        })
                                else:
                                    parts.append({"text": f"[imagem: {url_img}]"})
                        else:
                            parts.append({"text": str(bloco)})
                else:
                    parts = [{"text": str(conteudo)}]
                contents.append({"role": "user", "parts": parts})
                continue
            if role == "assistant":
                parts_a: List[Dict[str, Any]] = []
                if isinstance(conteudo, str) and conteudo:
                    parts_a.append({"text": conteudo})
                elif isinstance(conteudo, list):
                    for bloco in conteudo:
                        if isinstance(bloco, dict) and bloco.get("type") == "text":
                            parts_a.append({"text": bloco.get("text", "")})
                tcs = msg.get("tool_calls")
                if tcs:
                    for tc in tcs:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        parts_a.append({
                            "functionCall": {"name": fn.get("name", ""), "args": args}
                        })
                contents.append({"role": "model", "parts": parts_a or [{"text": ""}]})
                continue
            if role == "tool":
                nome = msg.get("name", "unknown")
                resp_conteudo = conteudo if isinstance(conteudo, str) else str(conteudo)
                try:
                    resp_obj = json.loads(resp_conteudo)
                except (json.JSONDecodeError, TypeError):
                    resp_obj = {"result": resp_conteudo}
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": nome,
                            "response": resp_obj,
                        }
                    }],
                })
                continue
        return system_instruction, contents

    @staticmethod
    def _converter_ferramentas(
        ferramentas: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        decls: List[Dict[str, Any]] = []
        for f in ferramentas:
            fn = f.get("function", f)
            decls.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return [{"functionDeclarations": decls}]

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        if imagem is not None:
            raise ErroProvedor(
                "imagem_nao_suportada", False,
                "google: imagem inline nao implementada nesta versao",
            )

        system_instruction, contents = self._converter_mensagens(mensagens)
        corpo: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            corpo["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if ferramentas:
            corpo["tools"] = self._converter_ferramentas(ferramentas)

        url = f"{self._base}/v1beta/models/{self._modelo}:streamGenerateContent?key={self._chave}"
        cabecalhos = {"Content-Type": "application/json"}
        log.debug("Google POST %s model=%s", _sem_segredo(url), self._modelo)

        async for linha in _stream_http(
            "POST", url,
            headers=cabecalhos, json_body=corpo,
            timeout=self._timeout, cancelamento=cancelamento,
        ):
            linha = linha.strip()
            if not linha:
                continue
            payload = linha
            if linha.startswith("data:"):
                payload = linha[len("data:"):].strip()
            if not payload:
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                log.warning("Gemini chunk JSON invalido: %s", _sem_segredo(payload[:200]))
                continue

            candidates = chunk.get("candidates")
            if not candidates:
                continue
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part and part["text"]:
                    yield EventoInferencia("texto", {"conteudo": part["text"]})
                if "functionCall" in part:
                    fc = part["functionCall"]
                    yield EventoInferencia("chamada", {
                        "id": f"gemini_{fc.get('name', 'call')}",
                        "nome": fc.get("name", ""),
                        "argumentos": fc.get("args", {}),
                    })

        yield EventoInferencia("fim", {})


# -------------------------------------------------------------------------
# Compatibilidade com T1/T3/T5 (laco.py, reserva.py)
# ------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoInferencia:
    """Compat: resultado sincrono usado por laco.py e reserva.py."""
    texto: Optional[str] = None
    chamadas_ferramenta: List[Dict[str, Any]] = field(default_factory=list)
    provedor: str = ""
    erro: Optional[str] = None
    ttft_ms: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.erro is None


class AdaptadorFalso(AdaptadorProvedor):
    """Compat: adaptador de teste usado por laco.py e reserva.py."""

    nome = "falso"

    def __init__(self, resposta: str = "ok", falhar: bool = False) -> None:
        self._resposta = resposta
        self._falhar = falhar

    async def inferir(
        self,
        mensagens: List[Dict[str, Any]],
        ferramentas: Optional[List[Dict[str, Any]]] = None,
        imagem: Optional[str] = None,
        cancelamento: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[EventoInferencia]:
        if self._falhar:
            raise ErroProvedor("conexao", True, "erro de teste simulado")
        yield EventoInferencia("texto", {"conteudo": self._resposta})
        yield EventoInferencia("fim", {})

class ClienteLMStudio:
    """Ger?ncia expl?cita da API v1; nenhuma carga por descoberta ou infer?ncia.

    GET /api/v1/models inclui modelos baixados e inst?ncias com contexto.
    N?o devolve corpo de erro, cabe?alhos, URL ou segredo ao chamador.
    """

    def __init__(self, base_url: str, chave: str = ""):
        self.base = base_url.rstrip("/")
        self.chave = chave

    async def requisitar(self, metodo: str, caminho: str, corpo=None):
        headers = {"Authorization": f"Bearer {self.chave}"} if self.chave else {}
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as cliente:
                resposta = await cliente.request(metodo, f"{self.base}/api/v1/models{caminho}",
                                                json=corpo, headers=headers)
                if resposta.is_error:
                    raise ErroProvedor("http_erro", False, f"HTTP {resposta.status_code}")
                return resposta.json()
        except httpx.TimeoutException:
            raise ErroProvedor("timeout", True, "prazo esgotado") from None
        except httpx.HTTPError:
            raise ErroProvedor("conexao", True, "provedor indispon?vel") from None

    async def listar(self) -> list[dict[str, Any]]:
        dados = await self.requisitar("GET", "")
        if not isinstance(dados, dict) or not isinstance(dados.get("models"), list):
            raise ErroProvedor("listagem_invalida", False, "n?o foi poss?vel confirmar inst?ncias")
        modelos = []
        for m in dados["models"]:
            if not isinstance(m, dict) or m.get("type") != "llm":
                continue
            if not isinstance(m.get("key"), str) or not isinstance(m.get("loaded_instances"), list):
                raise ErroProvedor("listagem_invalida", False, "inst?ncias n?o confirmadas")
            instancias = []
            for i in m["loaded_instances"]:
                if not isinstance(i, dict) or not isinstance(i.get("id"), str) or not i["id"]:
                    raise ErroProvedor("listagem_invalida", False, "inst?ncia inv?lida")
                cfg = i.get("config") or {}
                instancias.append({"id": i["id"], "contexto": cfg.get("context_length")})
            modelos.append({"id": m["key"], "instancias": instancias})
        return modelos

    async def trocar(self, modelo: str) -> str:
        modelos = await self.listar()
        if not any(m["id"] == modelo for m in modelos):
            raise ErroProvedor("modelo_inexistente", False, "modelo n?o baixado")
        instancias = [i for m in modelos for i in m["instancias"]]
        alvo = next(m for m in modelos if m["id"] == modelo)
        if len(instancias) == 1 and alvo["instancias"]:
            return alvo["instancias"][0]["id"]
        for instancia in instancias:
            await self.requisitar("POST", "/unload", {"instance_id": instancia["id"]})
        # N?o basta HTTP 200 na descarga. Qualquer inst?ncia restante impede carga.
        if any(m["instancias"] for m in await self.listar()):
            raise ErroProvedor("descarga_nao_confirmada", False, "carga interrompida")
        await self.requisitar("POST", "/load", {"model": modelo})
        modelos = await self.listar()
        alvo = next((m for m in modelos if m["id"] == modelo), None)
        if not alvo or len(alvo["instancias"]) != 1 or sum(len(m["instancias"]) for m in modelos) != 1:
            raise ErroProvedor("carga_nao_confirmada", False, "prontid?o n?o confirmada")
        return alvo["instancias"][0]["id"]
