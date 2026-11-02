"""Pastas do usuário: configuração e dados ficam fora do repositório.

Precedência: variável de ambiente (VARD_CONFIG, VARD_DADOS) e, na falta dela, a pasta padrão do usuário.
Nunca se procura configuração dentro do checkout.
"""
from __future__ import annotations

import os
from pathlib import Path


def _base_usuario() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "rdl-vard"


def pasta_config() -> Path:
    """Pasta das configurações (*.toml, persona*.md). VARD_CONFIG sobrescreve."""
    valor = os.environ.get("VARD_CONFIG", "").strip()
    return Path(valor) if valor else _base_usuario() / "config"


def pasta_dados() -> Path:
    """Pasta de estado, logs, tarefas e reuniões. VARD_DADOS sobrescreve."""
    valor = os.environ.get("VARD_DADOS", "").strip()
    return Path(valor) if valor else _base_usuario()


def arquivo_config(nome: str) -> Path:
    """Caminho de um arquivo de configuração do usuário; só o nome, sem subir de pasta."""
    if not nome or Path(nome).name != nome or nome in {".", ".."}:
        raise ValueError(f"nome de configuração inválido: {nome!r}")
    return pasta_config() / nome


def arquivo_segredos() -> Path:
    """segredos.toml fica ao lado da pasta de configuração (VARD_CONFIG/../segredos.toml) ou na pasta do usuário."""
    valor = os.environ.get("VARD_CONFIG", "").strip()
    return (Path(valor).parent if valor else _base_usuario()) / "segredos.toml"
