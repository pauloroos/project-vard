"""Estado do ciclo de vida (estado.json) e disparo do ciclo nativo ou vard-modo.ps1.

Quando o app novo (Tauri) está vivo com supervisor ativo, os pedidos são publicados
na caixa IPC (VARD_DADOS/ciclo/pedidos/) para a fila serial do Rust consumir.
Sem app vivo, mantém o comportamento legado (PowerShell via vard-modo.ps1).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import uuid
from pathlib import Path

from vard.segredos import PASTA

ARQUIVO_ESTADO = PASTA / "estado.json"
SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "windows" / "vard-modo.ps1"
# sonda: só confirma pedido→Rust→registro.
# aba: confirma pedido→Rust→registro (UI fica no frontend).
# iniciar/parar/recarregar/sair/tentar/jogo/voltar: verbos da fila serial.
VERBOS = ("iniciar", "jogo", "voltar", "parar", "recarregar", "sonda", "aba", "tentar", "sair")
DESCONHECIDO = {"modo": "desconhecido", "desde": "", "detalhe": "estado.json ausente ou ilegível"}
ARQUIVO_SONDA = PASTA / "sonda.txt"

# Caixa IPC: pasta onde o Rust consome pedidos atômicos.
PASTA_PEDIDOS = PASTA / "ciclo" / "pedidos"
ARQUIVO_APP = PASTA / "ciclo" / "app.json"

# Sem janela, mas com console: o powershell.exe 5.1 lançado com DETACHED_PROCESS devolve 0 e
# não roda nada (provado na revisão final do plano 2). Por isso CREATE_NO_WINDOW.
FLAGS_DISPARO = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def ler_estado() -> dict:
    try:
        dados = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DESCONHECIDO)
    if not isinstance(dados, dict) or "modo" not in dados:
        return dict(DESCONHECIDO)
    return {"modo": str(dados.get("modo")), "desde": str(dados.get("desde", "")), "detalhe": str(dados.get("detalhe", ""))}


def _ps_literal(texto: str) -> str:
    """String literal do PowerShell (aspas simples; apóstrofo dobrado)."""
    return "'" + texto.replace("'", "''") + "'"


def comando_intermediario(alvo: Path, verbo: str) -> str:
    """Texto PowerShell que o intermediário roda: só um Start-Process do script e sai.

    O -File vai entre aspas duplas porque o Start-Process do PowerShell 5.1 junta o
    -ArgumentList com espaços sem pôr aspas (caminho com espaço quebraria).
    """
    argumentos = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", f'"{alvo}"', verbo]
    lista = ",".join(_ps_literal(a) for a in argumentos)
    return f"Start-Process -FilePath powershell -ArgumentList @({lista}) -WindowStyle Hidden"


def _app_vivo() -> dict | None:
    """Lê app.json e devolve o conteúdo se o app novo estiver vivo com supervisor ativo."""
    try:
        dados = json.loads(ARQUIVO_APP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or "sessao_id" not in dados:
        return None
    # Verifica supervisor no instalacao.json
    from vard.segredos import PASTA as _P
    inst = _P / "instalacao.json"
    try:
        cfg = json.loads(inst.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not cfg.get("supervisor", False):
        return None
    return dados


def publicar_pedido(verbo: str) -> dict:
    """Publica pedido atômico na caixa IPC para a fila serial do Rust consumir.

    Retorna {"ok": True, "id": "<uuid>"} em caso de sucesso.
    Levanta ValueError para verbo desconhecido ou OSError para falha de escrita.
    """
    if verbo not in VERBOS:
        raise ValueError(f"verbo desconhecido: {verbo}")
    app = _app_vivo()
    if app is None:
        raise RuntimeError("app novo indisponivel ou supervisor desabilitado")
    pedido_id = str(uuid.uuid4())
    PASTA_PEDIDOS.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps({"id": pedido_id, "verbo": verbo, "sessao": app["sessao_id"]})
    tmp = PASTA_PEDIDOS / f"{pedido_id}.tmp"
    alvo = PASTA_PEDIDOS / f"{pedido_id}.json"
    tmp.write_text(conteudo, encoding="utf-8")
    tmp.rename(alvo)
    return {"ok": True, "id": pedido_id}


def disparar(verbo: str, script: Path | None = None) -> int | dict:
    """Publica pedido na caixa IPC (app novo) ou roda vard-modo.ps1 (legado).

    Com app novo vivo e supervisor ativo: publica na caixa e devolve {"ok": True, "id": uuid}.
    Sem app novo: mantém comportamento legado (PowerShell) e devolve PID do intermediário.
    """
    if verbo not in VERBOS:
        raise ValueError(f"verbo desconhecido: {verbo}")
    # Tenta publicar na caixa IPC primeiro
    try:
        return publicar_pedido(verbo)
    except (RuntimeError, OSError):
        pass
    # Fallback legado: PowerShell via vard-modo.ps1
    alvo = Path(script or SCRIPT)
    if not alvo.exists():
        raise FileNotFoundError(f"vard-modo.ps1 não encontrado em {alvo}")
    codificado = base64.b64encode(comando_intermediario(alvo, verbo).encode("utf-16-le")).decode("ascii")
    p = subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", codificado],
        creationflags=FLAGS_DISPARO, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return p.pid
