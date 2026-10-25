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
        return {"mensagens": [], "trocas": 0, "trocass": 0}
    try:
        dados = json.loads(texto)
    except ValueError:
        return {"mensagens": [], "trocas": 0, "trocass": 0}
    if not isinstance(dados, dict):
        return {"mensagens": [], "trocas": 0, "trocass": 0}
    msgs = dados.get("mensagens", [])
    if not isinstance(msgs, list):
        msgs = []
    trocas = dados.get("trocas", dados.get("trocass", 0))
    if not isinstance(trocas, int):
        trocas = 0
    return {"mensagens": msgs, "trocas": trocas, "trocass": trocas}


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


def contar_trocas(sessao_id: str) -> int:
    """Devolve a quantidade de trocas completas gravadas na sessão."""
    with _trava:
        return _ler(sessao_id).get("trocas", 0)


def adicionar_troca(sessao_id: str, pergunta: str | dict[str, Any], resposta: str | dict[str, Any]) -> None:
    """Acrescenta o par pergunta/resposta confirmado e aplica o limite de trocas."""
    msg_user = pergunta if isinstance(pergunta, dict) else {"role": "user", "content": pergunta}
    msg_assist = resposta if isinstance(resposta, dict) else {"role": "assistant", "content": resposta}
    with _trava:
        dados = _ler(sessao_id)
        msgs = dados["mensagens"]
        msgs.append(msg_user)
        msgs.append(msg_assist)
        dados["trocas"] = dados.get("trocas", dados.get("trocass", 0)) + 1
        dados["trocass"] = dados["trocas"]
        while dados["trocas"] > LIMITE_TROCAS and len(msgs) >= 2:
            # Remove a troca mais antiga (par usuário+assistente)
            msgs.pop(0)
            msgs.pop(0)
            dados["trocas"] = max(dados["trocas"] - 1, 0)
            dados["trocass"] = dados["trocas"]
        _gravar(sessao_id, dados)


def gravar_troca(sessao_id: str, pergunta: str | dict[str, Any], resposta: str | dict[str, Any]) -> None:
    """Sinônimo de adicionar_troca."""
    adicionar_troca(sessao_id, pergunta, resposta)


def adicionar_mensagem(sessao_id: str, mensagem: dict[str, Any]) -> None:
    """Acrescenta uma mensagem confirmada e aplica o limite de trocas."""
    with _trava:
        dados = _ler(sessao_id)
        msgs = dados["mensagens"]
        msgs.append(mensagem)
        role = mensagem.get("role")
        trocas = dados.get("trocas", dados.get("trocass", 0))
        if role == "assistant":
            trocas += 1
        dados["trocas"] = trocas
        dados["trocass"] = trocas
        while dados["trocas"] > LIMITE_TROCAS and len(msgs) >= 2:
            # Remove a troca mais antiga (par usuário+assistente)
            msgs.pop(0)
            msgs.pop(0)
            dados["trocas"] = max(dados["trocas"] - 1, 0)
            dados["trocass"] = dados["trocas"]
        _gravar(sessao_id, dados)


def limpar(sessao_id: str) -> None:
    """Remove o arquivo de sessão (usado em testes)."""
    arq = _arquivo_sessao(sessao_id)
    try:
        arq.unlink()
    except FileNotFoundError:
        pass