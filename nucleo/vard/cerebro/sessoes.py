"""Sessões do cérebro: histórico isolado por sessão e limite de trocas completas.

Cada sessão mantém sua própria lista de mensagens confirmadas (usuário/assistente)
e um contador de trocas completas. O limite padrão é 10 trocas; ao exceder, as
mais antigas são descartadas inteiras. Persistência em arquivos atômicos dentro
de VARD_DADOS/cerebro/sessoes/.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from vard import config

LIMITE_TROCAS = 10
_trava = threading.Lock()


def _pasta_sessoes() -> Path:
    return config.pasta_dados() / "cerebro" / "sessoes"


def _arquivo_sessao(sessao_id: str) -> Path:
    if not sessao_id or "/" in sessao_id or "\\" in sessao_id:
        raise ValueError(f"sessao_id inválido: {sessao_id!r}")
    return _pasta_sessoes() / f"{sessao_id}.json"


def _ler(sessao_id: str) -> dict[str, Any]:
    arq = _arquivo_sessao(sessao_id)
    try:
        texto = arq.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"mensagens": [], "trocass": 0}
    try:
        dados = json.loads(texto)
    except ValueError:
        return {"mensagens": [], "trocass": 0}
    if not isinstance(dados, dict):
        return {"mensagens": [], "trocass": 0}
    msgs = dados.get("mensagens", [])
    if not isinstance(msgs, list):
        msgs = []
    trocas = dados.get("trocass", 0)
    if not isinstance(trocas, int):
        trocas = 0
    return {"mensagens": msgs, "trocass": trocas}


def _gravar(sessao_id: str, dados: dict[str, Any]) -> None:
    arq = _arquivo_sessao(sessao_id)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, arq)


def obter_historico(sessao_id: str) -> list[dict[str, Any]]:
    """Devolve a lista de mensagens confirmadas da sessão."""
    with _trava:
        return list(_ler(sessao_id)["mensagens"])


def adicionar_mensagem(sessao_id: str, mensagem: dict[str, Any]) -> None:
    """Acrescenta uma mensagem confirmada e aplica o limite de trocas."""
    with _trava:
        dados = _ler(sessao_id)
        msgs = dados["mensagens"]
        msgs.append(mensagem)
        # Conta troca completa quando há par usuário+assistente desde a última contagem
        # Simplificação: incrementa quando assistente responde após usuário
        role = mensagem.get("role")
        if role == "assistant":
            dados["trocass"] = dados.get("trocass", 0) + 1
        while dados["trocass"] > LIMITE_TROCAS and len(msgs) >= 2:
            # Remove a troca mais antiga (par usuário+assistente)
            msgs.pop(0)
            msgs.pop(0)
            dados["trocass"] = max(dados["trocass"] - 1, 0)
        _gravar(sessao_id, dados)


def limpar(sessao_id: str) -> None:
    """Remove o arquivo de sessão (usado em testes)."""
    arq = _arquivo_sessao(sessao_id)
    try:
        arq.unlink()
    except FileNotFoundError:
        pass