"""Trazer o Telegram do OpenJarvis para o Vard, sem tocar na origem.

Onde o OpenJarvis guarda o Telegram (só leitura aqui):
- `%OPENJARVIS_HOME%\\config.toml` (OPENJARVIS_HOME do ambiente; na falta, `openjarvis_home` do
  instalacao.json; por último a casa padrão `~/.openjarvis`): `[channel] enabled` e
  `[channel.telegram] bot_token`, `allowed_chat_ids` (texto separado por vírgula) e `parse_mode`.
- Na instalação do Vard com OpenJarvis, esse bloco é gerado por `aplicar-config.ps1` a partir de
  `segredos.toml` `[telegram] token`/`chat_id`, que serve de segunda fonte.

Destino: token direto no cofre do Windows (`vard:canal:telegram`, o mesmo da tela) e chats
permitidos/ligado em `telegram.toml`. Idempotente; um Telegram já configurado no Vard só é
substituído com `substituir=True`. O token nunca sai deste processo: respostas, logs e erros
mostram só presença e contagens.
"""
from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vard import config, credenciais, instalacao
from vard import telegram as tg

log = logging.getLogger("vard.telegram")

_TOKEN = re.compile(r"\d{3,}:[A-Za-z0-9_-]{10,}")


@dataclass(frozen=True)
class OrigemTelegram:
    fonte: str                      # "openjarvis" (config.toml vivo) ou "segredos" (segredos.toml)
    chats: tuple[str, ...]
    habilitado: bool
    token: str = field(repr=False)  # nunca em repr, log ou resposta


def _ler_toml(arq: Path) -> dict:
    try:
        with arq.open("rb") as f:
            dados = tomllib.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _token_valido(valor: Any) -> str:
    """Token no formato da Bot API; marcadores (__TELEGRAM_TOKEN__) e lixo viram vazio."""
    texto = str(valor or "").strip()
    return texto if _TOKEN.fullmatch(texto) else ""


def _chats(valor: Any) -> tuple[str, ...]:
    """allowed_chat_ids aceita "1,2", "1; 2", lista ou número; só ids numéricos, sem repetição."""
    return tg.separar_chats(valor)


def casas_openjarvis() -> list[Path]:
    """Casas possíveis do OpenJarvis, na ordem: ambiente, instalacao.json, padrão do upstream."""
    casas: list[Path] = []
    amb = os.environ.get("OPENJARVIS_HOME", "").strip()
    if amb:
        casas.append(Path(amb))
    casa = str(instalacao.ler().get("openjarvis_home", "")).strip()
    if casa:
        casas.append(Path(casa))
    casas.append(Path.home() / ".openjarvis")
    unicas: list[Path] = []
    for c in casas:
        if c not in unicas:
            unicas.append(c)
    return unicas


def _do_openjarvis() -> OrigemTelegram | None:
    for casa in casas_openjarvis():
        canal = _ler_toml(casa / "config.toml").get("channel")
        if not isinstance(canal, dict):
            continue
        bloco = canal.get("telegram") if isinstance(canal.get("telegram"), dict) else {}
        token = _token_valido(bloco.get("bot_token"))
        if token:
            return OrigemTelegram("openjarvis", _chats(bloco.get("allowed_chat_ids")),
                                  bool(canal.get("enabled")), token)
    return None


def _dos_segredos() -> OrigemTelegram | None:
    bloco = _ler_toml(config.arquivo_segredos()).get("telegram")
    if not isinstance(bloco, dict):
        return None
    token = _token_valido(bloco.get("token"))
    if not token:
        return None
    chats = _chats(bloco.get("chat_id"))
    return OrigemTelegram("segredos", chats, bool(chats), token)


def ler_origem() -> OrigemTelegram | None:
    """Telegram do OpenJarvis: o config.toml vivo primeiro; depois o segredos.toml que o alimenta."""
    return _do_openjarvis() or _dos_segredos()


def openjarvis_sobe() -> bool:
    """Mesma regra do app: o OpenJarvis sobe se for quem responde ou se 'manter ligado' estiver marcado."""
    try:
        from vard import ajustes
        hud = ajustes.ler_documento("hud")
    except Exception:  # noqa: BLE001
        return False
    return hud.get("cerebro") == "openjarvis" or hud.get("usar_openjarvis") is True


AVISO_CONFLITO = ("O OpenJarvis está marcado para subir (quem responde ou 'Manter o OpenJarvis ligado'): "
                  "dois programas no mesmo bot brigam pelas mensagens. Desligue o OpenJarvis para o Telegram do Vard funcionar.")


def _igual(origem: OrigemTelegram) -> bool:
    cfg = tg._ler_config_telegram()
    return (tg.token_do_cofre() == origem.token and not str(cfg.get("token", "")).strip()
            and sorted(tg._chats_permitidos(cfg)) == sorted(origem.chats)
            and bool(cfg.get("habilitado")) == origem.habilitado)


def previa() -> dict[str, Any]:
    """O que há para trazer, sem o token: a tela mostra o botão quando `pode_trazer`."""
    origem = ler_origem()
    vard_configurado = tg.configurado()
    resposta: dict[str, Any] = {
        "disponivel": origem is not None,
        "vard_configurado": vard_configurado,
        "ja_migrado": bool(origem and _igual(origem)),
        "pode_trazer": origem is not None and not vard_configurado,
    }
    if origem:
        resposta.update(fonte=origem.fonte, chats=len(origem.chats), ligado=origem.habilitado)
    return resposta


def trazer(substituir: bool = False) -> dict[str, Any]:
    """Copia token (cofre) e chats/ligado (telegram.toml). A origem só é lida."""
    origem = ler_origem()
    if origem is None:
        return {"ok": False, "motivo": "sem_origem",
                "detalhe": "Não achei o Telegram do OpenJarvis (config.toml ou segredos.toml)."}
    aviso = {"aviso": AVISO_CONFLITO} if origem.habilitado and openjarvis_sobe() else {}
    if _igual(origem):
        return {"ok": True, "mudou": False, "fonte": origem.fonte, "chats": len(origem.chats),
                "ligado": origem.habilitado, "detalhe": "O Telegram do OpenJarvis já está no Vard.", **aviso}
    if tg.configurado() and not substituir:
        return {"ok": False, "motivo": "ja_configurado",
                "detalhe": "O Vard já tem um Telegram configurado; confirme para substituir pelo do OpenJarvis."}
    try:
        credenciais.gravar(tg.COFRE_TIPO, tg.COFRE_ID, origem.token)
        if tg.token_do_cofre() != origem.token:
            raise RuntimeError("cofre não confirmou")
    except Exception:  # noqa: BLE001
        log.warning("migração do Telegram: cofre indisponível; nada foi gravado")
        return {"ok": False, "motivo": "cofre", "detalhe": "Não consegui guardar o token no cofre do Windows."}
    dados = tg._ler_config_telegram()
    dados.pop("token", None)   # o formato antigo em texto sai: o cofre passa a valer
    dados["habilitado"] = origem.habilitado
    dados["chats_permitidos"] = list(origem.chats)
    tg.gravar_config_telegram(dados)
    log.info("telegram trazido do OpenJarvis (fonte=%s, chats=%d)", origem.fonte, len(origem.chats))
    return {"ok": True, "mudou": True, "fonte": origem.fonte, "chats": len(origem.chats),
            "ligado": origem.habilitado, "detalhe": "Telegram trazido do OpenJarvis.", **aviso}
