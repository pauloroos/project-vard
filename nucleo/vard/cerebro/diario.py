"""Diário de efeitos do cérebro: registra resultados de ferramentas antes de devolver ao modelo.
Persistência atômica em VARD_DADOS/cerebro/diario/<pedido_id>.jsonl. Cada linha é um efeito
confirmado; leitura ignora linhas corrompidas. Usado para evitar repetição de ações com resultado
desconhecido em caso de falha/reserva.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from vard import config

_trava = threading.Lock()


def _pasta_diario() -> Path:
    return config.pasta_dados() / "cerebro" / "diario"


def _arquivo_diario(pedido_id: str) -> Path:
    if not pedido_id or "/" in pedido_id or "\\" in pedido_id:
        raise ValueError(f"pedido_id inválido: {pedido_id!r}")
    return _pasta_diario() / f"{pedido_id}.jsonl"


def registrar_efeito(pedido_id: str, efeito: dict[str, Any]) -> None:
    """Grava um efeito confirmado no diário do pedido (append atômico)."""
    if not isinstance(efeito, dict):
        raise TypeError("efeito deve ser dict")
    arq = _arquivo_diario(pedido_id)
    with _trava:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        # Lê conteúdo existente e acrescenta nova linha
        linhas: list[str] = []
        try:
            linhas = arq.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            pass
        linhas.append(json.dumps(efeito, ensure_ascii=False))
        with tmp.open("w", encoding="utf-8") as f:
            for linha in linhas:
                f.write(linha + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, arq)


def listar_efeitos(pedido_id: str) -> list[dict[str, Any]]:
    """Devolve os efeitos confirmados do pedido; ignora linhas corrompidas."""
    arq = _arquivo_diario(pedido_id)
    try:
        texto = arq.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    efeitos: list[dict[str, Any]] = []
    for linha in texto.splitlines():
        try:
            dado = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dado, dict):
            efeitos.append(dado)
    return efeitos


def limpar_diario(pedido_id: str) -> None:
    """Remove o arquivo de diário de um pedido (usado em testes)."""
    arq = _arquivo_diario(pedido_id)
    try:
        arq.unlink()
    except FileNotFoundError:
        pass