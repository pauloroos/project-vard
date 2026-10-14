"""Diário de efeitos do cérebro: registra intenção e resultado de ferramentas.

Contrato mínimo (plano T4):
- ``registrar_intencao(pedido_id, chave)`` grava intenção antes do efeito.
- ``registrar_resultado(pedido_id, chave, resultado)`` grava resultado confirmado.
- ``marcar_incerto(pedido_id, chave)`` marca efeito incerto (ocorreu mas resultado não gravado).
- ``obter_resultado(pedido_id, chave)`` devolve resultado confirmado ou None.
- ``tem_incerto(pedido_id, chave)`` verifica se há efeito incerto pendente.
- Repetição no mesmo turno reutiliza resultado confirmado; incerto termina sem repetir.
- Persistência atômica em VARD_DADOS/cerebro/diario/<pedido_id>.jsonl.
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


def _ler_linhas(arq: Path) -> list[dict[str, Any]]:
    try:
        texto = arq.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    linhas: list[dict[str, Any]] = []
    for linha in texto.splitlines():
        try:
            dado = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dado, dict):
            linhas.append(dado)
    return linhas


def _gravar_linha(arq: Path, linha_dict: dict[str, Any]) -> None:
    """Append atômico de uma linha JSON ao arquivo do diário."""
    with _trava:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        linhas_existentes: list[str] = []
        try:
            linhas_existentes = arq.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            pass
        linhas_existentes.append(json.dumps(linha_dict, ensure_ascii=False))
        with tmp.open("w", encoding="utf-8") as f:
            for l in linhas_existentes:
                f.write(l + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, arq)


def _chave_canonica(nome: str, argumentos: dict[str, Any]) -> str:
    """Chave canônica para deduplicação: nome + argumentos ordenados."""
    args_str = json.dumps(argumentos, sort_keys=True, ensure_ascii=False)
    return f"{nome}:{args_str}"


def registrar_intencao(pedido_id: str, nome: str, argumentos: dict[str, Any]) -> str:
    """Grava intenção antes do efeito. Devolve a chave canônica."""
    chave = _chave_canonica(nome, argumentos)
    _gravar_linha(_arquivo_diario(pedido_id), {
        "tipo": "intencao",
        "chave": chave,
        "nome": nome,
    })
    return chave


def registrar_resultado(pedido_id: str, chave: str, resultado: Any) -> None:
    """Grava resultado confirmado após execução bem-sucedida."""
    _gravar_linha(_arquivo_diario(pedido_id), {
        "tipo": "resultado",
        "chave": chave,
        "resultado": resultado,
    })


def marcar_incerto(pedido_id: str, chave: str) -> None:
    """Marca efeito como incerto (ocorreu mas resultado não foi gravado)."""
    _gravar_linha(_arquivo_diario(pedido_id), {
        "tipo": "incerto",
        "chave": chave,
    })


def obter_resultado(pedido_id: str, chave: str) -> Any | None:
    """Devolve resultado confirmado para a chave, ou None se não houver."""
    linhas = _ler_linhas(_arquivo_diario(pedido_id))
    # Busca de trás para frente: último resultado confirmado vence
    for linha in reversed(linhas):
        if linha.get("tipo") == "resultado" and linha.get("chave") == chave:
            return linha.get("resultado")
    return None


def tem_incerto(pedido_id: str, chave: str) -> bool:
    """Verifica se há efeito incerto pendente para a chave."""
    linhas = _ler_linhas(_arquivo_diario(pedido_id))
    for linha in linhas:
        if linha.get("tipo") == "incerto" and linha.get("chave") == chave:
            return True
    return False


def tem_resultado(pedido_id: str, chave: str) -> bool:
    """Verifica se há resultado confirmado para a chave."""
    return obter_resultado(pedido_id, chave) is not None


def listar_efeitos(pedido_id: str) -> list[dict[str, Any]]:
    """Devolve todas as entradas do diário do pedido."""
    return _ler_linhas(_arquivo_diario(pedido_id))


def limpar_diario(pedido_id: str) -> None:
    """Remove o arquivo de diário de um pedido (usado em testes)."""
    arq = _arquivo_diario(pedido_id)
    try:
        arq.unlink()
    except FileNotFoundError:
        pass