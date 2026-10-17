"""Detecção das CLIs instaladas e validação do cadastro cli-* do painel (T17a da 0.8).

A detecção só consulta o PATH e roda `--version` (e `agy models` para a lista do
agy): nunca prompt, e nenhum caminho absoluto sai na resposta (C11).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# Tipos de provedor que são uma CLI de agente (0.8).
# TIPOS_CLI é usado para validação de cadastro (cérebro ativo); só claude/agy são aceitos.
TIPOS_CLI = ("cli-claude", "cli-agy")

# Tipos detectáveis pelo modal (inclui Codex/OpenCode, que só servem para tarefas delegadas).
TIPOS_DETECTAVEIS = ("cli-claude", "cli-agy", "cli-codex", "cli-opencode")

# Sugestões do Claude (C11); o agy lista os modelos com `agy models`.
MODELOS_SUGERIDOS: Dict[str, List[str]] = {
    "cli-claude": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    "cli-agy": [],
    "cli-codex": [],
    "cli-opencode": [],
}

_COMANDOS = {
    "cli-claude": "claude",
    "cli-agy": "agy",
    "cli-codex": "codex",
    "cli-opencode": "opencode",
}
TEMPO_LIMITE = 10.0
_TAMANHO_MAX = 100
_MODELOS_MAX = 50


def _rodar(comando: List[str]) -> str:
    """Roda um comando de leitura (--version/models) e devolve a saída; qualquer falha vira vazio."""
    try:
        r = subprocess.run(
            comando, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TEMPO_LIMITE,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("cli: %s não rodou (%s)", comando[0], type(exc).__name__)
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout or ""


def _primeira_linha(saida: str) -> str:
    for linha in saida.splitlines():
        limpa = linha.strip()
        if limpa:
            return limpa[:_TAMANHO_MAX]
    return ""


def _modelos_agy(exe: str) -> List[str]:
    # `agy models` imprime um cabeçalho e linhas `id<TAB>Nome de exibição`; o --model aceita só o id.
    saida = _rodar([exe, "models"])
    modelos: List[str] = []
    for linha in saida.splitlines():
        nome = linha.split("\t", 1)[0].strip()[:_TAMANHO_MAX]
        if nome and not any(c.isspace() for c in nome) and nome not in modelos:
            modelos.append(nome)
    return modelos[:_MODELOS_MAX]


def detectar() -> List[Dict[str, Any]]:
    """Sonda o PATH pelas CLIs conhecidas (C11); resposta sem caminho algum."""
    itens: List[Dict[str, Any]] = []
    for tipo in TIPOS_DETECTAVEIS:
        exe = shutil.which(_COMANDOS[tipo])
        item: Dict[str, Any] = {"tipo": tipo, "instalada": exe is not None, "versao": "", "modelos": []}
        if exe:
            item["versao"] = _primeira_linha(_rodar([exe, "--version"]))
            if tipo == "cli-agy":
                item["modelos"] = _modelos_agy(exe)
            else:
                item["modelos"] = list(MODELOS_SUGERIDOS.get(tipo, []))
        itens.append(item)
    return itens


def validar_provedor_cli(entrada: Any) -> Dict[str, Any]:
    """Valida e normaliza um cadastro cli-* do painel (C11).

    Sem url_base nem credencial; yolo liga por padrão, enxuto desliga, esforco é opcional.
    """
    if not isinstance(entrada, dict):
        raise ValueError("provedor cli precisa ser um objeto")
    ident = str(entrada.get("id") or "")
    tipo = entrada.get("tipo")
    if tipo not in TIPOS_CLI:
        raise ValueError(f"tipo de provedor não é CLI: {tipo!r}")
    if not ident:
        raise ValueError("provedor cli sem id")
    if not isinstance(entrada.get("nome"), str):
        raise ValueError(f"provedor cli {ident} sem nome")
    if entrada.get("url_base"):
        raise ValueError(f"provedor cli {ident} não aceita url_base")
    if entrada.get("credencial_ref"):
        raise ValueError(f"provedor cli {ident} não aceita credencial")
    modelo = str(entrada.get("modelo") or "").strip()
    if not modelo:
        raise ValueError(f"provedor cli {ident} sem modelo")
    yolo = entrada.get("yolo", True)
    enxuto = entrada.get("enxuto", False)
    esforco = entrada.get("esforco", None)
    if not isinstance(yolo, bool):
        raise ValueError(f"provedor cli {ident} com yolo que não é booleano")
    if not isinstance(enxuto, bool):
        raise ValueError(f"provedor cli {ident} com enxuto que não é booleano")
    if esforco is not None and not isinstance(esforco, str):
        raise ValueError(f"provedor cli {ident} com esforco que não é texto")
    return {
        "id": ident,
        "nome": entrada.get("nome"),
        "tipo": tipo,
        "modelo": modelo,
        "yolo": yolo,
        "enxuto": enxuto,
        "esforco": esforco,
    }
