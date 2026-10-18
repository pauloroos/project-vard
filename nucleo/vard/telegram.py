"""Telegram próprio do cérebro: long polling com Bot API direta, desligado por padrão.

O poller só sobe quando telegram.toml tem habilitado=true, há token e chat permitido.
O token fica no cofre do Windows (alvo vard:canal:telegram); `token` no telegram.toml é
só o formato antigo, lido quando o cofre está vazio. Dois consumidores no mesmo bot
brigam pelo getUpdates (409): com o Telegram no Vard, o OpenJarvis fica desligado.
Cada chat autorizado gera uma sessão isolada no cérebro; áudio recebido marca origem
TELEGRAM para transcrição posterior pelo STT próprio. Token e URL completa da Bot API
NUNCA aparecem em log, erro ou exceção.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from vard import config, credenciais, modo
from vard.cerebro import pedidos
from vard.cerebro.contratos import Origem, Pedido

log = logging.getLogger("vard.telegram")

# Desativa logs de httpx/httpcore que registram URL com token
for _nome in ("httpx", "httpcore"):
    logging.getLogger(_nome).setLevel(logging.WARNING)

LIMITE_MENSAGEM = 4096
POLL_TIMEOUT_PADRAO = 30
POLL_INTERVAL_PADRAO = 1.0
ESPERA_CONFLITO_S = 30.0     # 409: outro consumidor (OpenJarvis?) no mesmo bot; não insistir a cada segundo
#: Alvo do token no cofre do Windows (o app grava o mesmo pela tela).
COFRE_TIPO, COFRE_ID = "canal", "telegram"
ESTADO_ARQUIVO_PADRAO = None  # resolvido em tempo de execução via config.pasta_dados()


def _arquivo_estado() -> Path:
    return config.pasta_dados() / "telegram_estado.json"


def _ler_config_telegram() -> dict[str, Any]:
    """Lê telegram.toml da pasta de config; ausente ou ilegível = vazio."""
    try:
        arq = config.arquivo_config("telegram.toml")
        if not arq.exists():
            return {}
        import tomllib
        with arq.open("rb") as f:
            dados = tomllib.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def deve_iniciar_poller() -> bool:
    """Retorna True apenas se telegram.toml existe e tem habilitado=true."""
    cfg = _ler_config_telegram()
    return bool(cfg.get("habilitado"))


def _chats_permitidos(cfg: dict[str, Any]) -> set[str]:
    lista = cfg.get("chats_permitidos", [])
    if isinstance(lista, list):
        return {str(c) for c in lista if str(c).strip()}
    return set()


def token_do_cofre() -> str:
    """Token do bot no cofre do Windows; vazio se ausente ou cofre indisponível. Nunca logado."""
    try:
        return (credenciais.ler_para_uso_interno(COFRE_TIPO, COFRE_ID) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _token_seguro(cfg: dict[str, Any]) -> str:
    """Token do cofre; sem ele, o `token` antigo do telegram.toml. Vazio se não configurado. Nunca logado."""
    return token_do_cofre() or str(cfg.get("token", "")).strip()


def gravar_config_telegram(dados: dict[str, Any]) -> None:
    """Grava telegram.toml de forma atômica (tmp + replace)."""
    import tomli_w
    alvo = config.arquivo_config("telegram.toml")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(tomli_w.dumps(dados), encoding="utf-8")
    os.replace(tmp, alvo)


def separar_chats(valor: Any) -> tuple[str, ...]:
    """Chats como a tela e o OpenJarvis escrevem: "1, 2", "1;2", lista ou número; só ids numéricos, sem repetição."""
    if isinstance(valor, (list, tuple)):
        partes = [str(v) for v in valor]
    elif isinstance(valor, (int, str)) and not isinstance(valor, bool):
        partes = re.split(r"[,;\s]+", str(valor))
    else:
        partes = []
    vistos: list[str] = []
    for p in (x.strip() for x in partes):
        if re.fullmatch(r"-?\d{1,20}", p) and p not in vistos:
            vistos.append(p)
    return tuple(vistos)


def configurar(ligado: bool, chat: str = "") -> None:
    """Liga/desliga e define os chats permitidos (o campo da tela, "1, 2"); chat vazio mantém os atuais.

    Preserva o resto do telegram.toml; o token não passa por aqui.
    """
    dados = _ler_config_telegram()
    dados["habilitado"] = bool(ligado)
    chats = separar_chats(chat)
    if chats:
        dados["chats_permitidos"] = list(chats)
    elif not isinstance(dados.get("chats_permitidos"), list):
        dados["chats_permitidos"] = []
    gravar_config_telegram(dados)


def estado() -> dict[str, Any]:
    """Resumo para a tela e o assistente: nunca o token, só se ele existe."""
    cfg = _ler_config_telegram()
    chats = sorted(_chats_permitidos(cfg))
    return {"ligado": bool(cfg.get("habilitado")), "chat_permitido": ", ".join(chats),
            "token_configurado": bool(_token_seguro(cfg))}


def configurado() -> bool:
    """O Vard já tem Telegram (token ou chat permitido): migrar por cima exige confirmação."""
    cfg = _ler_config_telegram()
    return bool(_token_seguro(cfg)) or bool(_chats_permitidos(cfg))


class TelegramPoller:
    """Long polling contra a Bot API do Telegram com offset persistente."""

    def __init__(
        self,
        *,
        token: str,
        chats_permitidos: set[str],
        base_url: str = "https://api.telegram.org",
        timeout_s: int = POLL_TIMEOUT_PADRAO,
        poll_interval_s: float = POLL_INTERVAL_PADRAO,
        estado_arquivo: Path | None = None,
    ) -> None:
        self._token = token
        self._chats = chats_permitidos
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._interval = poll_interval_s
        self._estado_arq = estado_arquivo or _arquivo_estado()
        self._offset: int | None = None
        self.conflito = False   # último getUpdates deu 409 (outro consumidor no mesmo bot)
        self._carregar_offset()

    def _carregar_offset(self) -> None:
        try:
            if self._estado_arq.exists():
                dados = json.loads(self._estado_arq.read_text(encoding="utf-8"))
                off = dados.get("offset")
                if isinstance(off, int):
                    self._offset = off
        except (OSError, ValueError):
            pass

    def _salvar_offset(self) -> None:
        if self._offset is None:
            return
        try:
            self._estado_arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._estado_arq.with_suffix(".tmp")
            tmp.write_text(json.dumps({"offset": self._offset}), encoding="utf-8")
            os.replace(tmp, self._estado_arq)
        except OSError:
            pass

    async def processar_updates(self) -> int:
        """Busca e processa updates pendentes. Retorna quantos foram admitidos."""
        params: dict[str, Any] = {"timeout": self._timeout}
        if self._offset is not None:
            params["offset"] = self._offset

        admitidos = 0
        try:
            async with httpx.AsyncClient(timeout=self._timeout + 5, trust_env=False) as client:
                url = f"{self._base}/bot{self._token}/getUpdates"
                r = await client.get(url, params=params)

                self.conflito = r.status_code == 409
                if r.status_code == 409:
                    log.warning("conflito 409 no getUpdates: outro consumidor no mesmo bot (OpenJarvis ligado?)")
                    return 0
                if r.status_code == 429:
                    retry = r.json().get("parameters", {}).get("retry_after", 30)
                    log.warning("rate limit 429; aguardando %s s", retry)
                    await asyncio.sleep(min(retry, 60))
                    return 0
                if r.status_code != 200:
                    log.warning("getUpdates falhou: HTTP %s", r.status_code)
                    return 0

                dados = r.json()
                if not dados.get("ok"):
                    log.warning("getUpdates ok=false")
                    return 0

                results = dados.get("result", [])
                for update in results:
                    update_id = update.get("update_id")
                    if update_id is None:
                        continue
                    if self._processar_update(update):
                        admitidos += 1
                    # Avança offset independentemente de admissão (chat não autorizado, etc.)
                    self._offset = update_id + 1
                    self._salvar_offset()

        except httpx.HTTPError as exc:
            log.warning("erro de rede no getUpdates: %s", type(exc).__name__)
        except Exception:  # noqa: BLE001
            log.warning("erro inesperado no polling")

        return admitidos

    def _processar_update(self, update: dict) -> bool:
        """Processa um update individual. Retorna True se admitiu pedido."""
        message = update.get("message")
        if not isinstance(message, dict):
            return False

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return False

        chat_id = str(chat.get("id", ""))
        if chat_id not in self._chats:
            return False

        update_id = update.get("update_id")
        if update_id is None:
            return False

        # Modo jogo: recebe mas não admite para inferência
        try:
            estado_modo = modo.ler_estado()
            if estado_modo.get("modo") == "jogo":
                return False
        except Exception:  # noqa: BLE001
            pass

        sessao_id = f"tg-chat-{chat_id}"
        pedido_id = f"tg-{chat_id}-{update_id}"

        texto = ""
        if "text" in message and isinstance(message["text"], str):
            texto = message["text"].strip()
        elif "voice" in message and isinstance(message["voice"], dict):
            # Áudio recebido: placeholder para transcrição posterior pelo STT próprio
            texto = "[áudio recebido]"

        if not texto:
            return False

        pedido = Pedido(
            pedido_id=pedido_id,
            sessao_id=sessao_id,
            origem=Origem.TELEGRAM,
            texto=texto,
        )

        try:
            pedidos.admitir(pedido)
            return True
        except ValueError:
            # Conflito de pedido_id com corpo diferente: já processado
            return False
        except Exception:  # noqa: BLE001
            log.warning("falha ao admitir pedido tg")
            return False


async def enviar_texto_dividido(
    *,
    chat_id: str,
    texto: str,
    token: str,
    base_url: str = "https://api.telegram.org",
) -> int:
    """Envia texto longo dividido em blocos <= LIMITE_MENSAGEM. Retorna quantos blocos foram enviados."""
    if not texto:
        return 0

    blocos = []
    while texto:
        bloco = texto[:LIMITE_MENSAGEM]
        blocos.append(bloco)
        texto = texto[LIMITE_MENSAGEM:]

    enviados = 0
    url = f"{base_url.rstrip('/')}/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            for bloco in blocos:
                r = await client.post(url, json={"chat_id": chat_id, "text": bloco})
                if r.status_code == 200 and r.json().get("ok"):
                    enviados += 1
                else:
                    log.warning("sendMessage falhou: HTTP %s", r.status_code)
    except httpx.HTTPError as exc:
        log.warning("erro de rede no sendMessage: %s", type(exc).__name__)

    return enviados