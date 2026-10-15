"""Preferência de dispositivos de áudio para a reunião.

Contrato da T9 (0.7):
- A preferência é salva atomicamente e lida pela ponte via GET /reuniao/dispositivos.
- Campos: microfone_id, microfone_rotulo, saida_id, saida_rotulo (string vazia = padrão).
- A reunião usa a preferência quando disponível; se o dispositivo sumir, volta ao padrão
  com marcador na transcrição (já existente em sessao.verificar_dispositivos).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger("vard_reuniao.preferencia")


@dataclass
class PreferenciaDispositivos:
    microfone_id: str = ""
    microfone_rotulo: str = ""
    saida_id: str = ""
    saida_rotulo: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


def _caminho_preferencia() -> Path:
    """Caminho do arquivo de preferência: VARD_DADOS/reuniao/preferencia.json."""
    base = os.environ.get("VARD_DADOS", "").strip()
    if not base:
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "rdl-vard")
    return Path(base) / "reuniao" / "preferencia.json"


def ler_preferencia() -> PreferenciaDispositivos:
    """Lê a preferência salva; retorna padrão se não existir ou estiver corrompido."""
    caminho = _caminho_preferencia()
    if not caminho.is_file():
        return PreferenciaDispositivos()
    try:
        with caminho.open("r", encoding="utf-8") as f:
            d = json.load(f)
        return PreferenciaDispositivos(
            microfone_id=str(d.get("microfone_id", "")),
            microfone_rotulo=str(d.get("microfone_rotulo", "")),
            saida_id=str(d.get("saida_id", "")),
            saida_rotulo=str(d.get("saida_rotulo", "")),
        )
    except (OSError, ValueError, TypeError):
        log.exception("falha ao ler preferencia de dispositivos")
        return PreferenciaDispositivos()


def gravar_preferencia(pref: PreferenciaDispositivos) -> None:
    """Grava a preferência atomicamente (write + rename)."""
    caminho = _caminho_preferencia()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(pref.como_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(caminho)
    except OSError:
        log.exception("falha ao gravar preferencia de dispositivos")
        raise