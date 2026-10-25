"""instalacao.json: onde o Vard e o OpenJarvis estão instalados nesta máquina.

Fora do repositório, junto dos dados do usuário. VARD_INSTALACAO sobrescreve o caminho.
Ausente ou inválido: defaults neutros, nunca exceção (a instalação pode ainda não existir).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from vard import config as _config

TEXTOS = ("raiz_codigo", "openjarvis_src", "openjarvis_home", "modelo")


def _padrao() -> dict:
    return {"raiz_codigo": "", "openjarvis_src": "", "openjarvis_home": "", "modelo": "",
            "contexto": 0, "servicos": {}}


def arquivo() -> Path:
    """instalacao.json da máquina; VARD_INSTALACAO sobrescreve."""
    valor = os.environ.get("VARD_INSTALACAO", "").strip()
    return Path(valor) if valor else _config.pasta_dados() / "instalacao.json"


def supervisor_ativo(caminho: Path | None = None) -> bool:
    """supervisor:true no instalacao.json (app único: o vard.exe cuida dos serviços e da bandeja)."""
    arq = Path(caminho) if caminho is not None else arquivo()
    try:
        dados = json.loads(arq.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(dados, dict) and dados.get("supervisor") is True


def ler(caminho: Path | None = None) -> dict:
    """Lê o instalacao.json; arquivo ausente ou JSON inválido devolve defaults neutros."""
    arq = Path(caminho) if caminho is not None else arquivo()
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _padrao()
    if not isinstance(dados, dict):
        return _padrao()
    saida = _padrao()
    for campo in TEXTOS:
        if campo in dados and dados[campo] is not None:
            saida[campo] = str(dados[campo])
    try:
        saida["contexto"] = int(dados.get("contexto") or 0)
    except (TypeError, ValueError):
        saida["contexto"] = 0
    if isinstance(dados.get("servicos"), dict):
        saida["servicos"] = dict(dados["servicos"])
    return saida
