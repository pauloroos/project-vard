"""Central de avisos da ponte: os últimos 100 avisos em %LOCALAPPDATA%/rdl-vard/avisos.jsonl.

O evento chega por POST /events/publicar (só a ponte escreve), o widget lê GET /avisos e marca
como lidos. Cada linha é um aviso em JSON; a leitura ignora linha corrompida e a gravação é atômica
(temporário + os.replace). Os testes trocam ARQUIVO ou passam `arq`.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from vard import config, tarefas

ARQUIVO: Path | None = None
LIMITE = 100
_trava = threading.Lock()      # registrar e marcar_lidos são lê-grava; a ponte atende em várias threads


def _arq(arq: Path | None) -> Path:
    return Path(arq) if arq else ARQUIVO or config.pasta_dados() / "avisos.jsonl"


def _ler(arq: Path) -> list[dict]:
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    avisos = []
    for linha in linhas:
        try:
            d = json.loads(linha)
        except ValueError:
            continue                          # linha corrompida: ignora
        if isinstance(d, dict) and isinstance(d.get("id"), int) and not isinstance(d.get("id"), bool):
            avisos.append(d)
    return avisos[-LIMITE:]


def _gravar(arq: Path, avisos: list[dict]) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for a in avisos:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, arq)


def listar(arq: Path | None = None) -> list[dict]:
    return _ler(_arq(arq))


def registrar(ev: dict, arq: Path | None = None) -> dict | None:
    """Guarda o evento validado como aviso novo e devolve o aviso (com id e hora). Preflight não é guardado."""
    if ev.get("tipo") == "preflight":
        return None
    alvo = _arq(arq)
    with _trava:
        avisos = _ler(alvo)
        aviso = {"id": max((a["id"] for a in avisos), default=0) + 1, "hora": tarefas.agora(),
                 "tipo": ev.get("tipo"), "resumo": str(ev.get("resumo", ""))}
        if "n" in ev:
            aviso["n"] = ev["n"]
        aviso["estado"] = ev.get("estado")
        aviso["lido"] = False
        avisos.append(aviso)
        _gravar(alvo, avisos[-LIMITE:])
    return aviso


def marcar_lidos(ids: list[int] | None = None, arq: Path | None = None) -> int:
    """Marca como lidos os avisos escolhidos (ids=None = todos) e devolve quantos continuam não lidos."""
    alvo = _arq(arq)
    with _trava:
        avisos = _ler(alvo)
        quer = None if ids is None else {i for i in ids if isinstance(i, int)}
        mudou = False
        for a in avisos:
            if (quer is None or a["id"] in quer) and not a.get("lido"):
                a["lido"] = True
                mudou = True
        if mudou:
            _gravar(alvo, avisos)
        return sum(1 for a in avisos if not a.get("lido"))
