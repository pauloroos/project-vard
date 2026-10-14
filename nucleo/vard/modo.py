"""Estado do ciclo de vida (estado.json) e disparo do vard-modo.ps1.

O script PowerShell é a fonte de verdade; aqui só se lê o estado que ele grava e se
dispara um verbo em processo separado, para a ponte (ou a bandeja) poder responder antes de cair.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from vard.segredos import PASTA

ARQUIVO_ESTADO = PASTA / "estado.json"
SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "windows" / "vard-modo.ps1"
# sonda: só grava sonda.txt (preflight prova que o disparo roda de verdade).
# aba: só abre a janela do Vard no Chrome se ela não existir (bandeja).
VERBOS = ("jogo", "voltar", "parar", "recarregar", "sonda", "aba")
DESCONHECIDO = {"modo": "desconhecido", "desde": "", "detalhe": "estado.json ausente ou ilegível"}
ARQUIVO_SONDA = PASTA / "sonda.txt"

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


def disparar(verbo: str, script: Path | None = None) -> int:
    """Roda `vard-modo.ps1 <verbo>` fora da árvore de processos de quem chamou.

    Lança um powershell INTERMEDIÁRIO que só faz Start-Process do script e sai na hora: o
    script fica órfão e o `taskkill /T` que ele mesmo dá na ponte ou na bandeja não o alcança.
    O comando vai em -EncodedCommand para o caminho passar intacto pelas duas camadas de
    aspas (Python -> powershell -> Start-Process). Devolve o PID do intermediário (já morto
    pouco depois); não é o PID do script.
    """
    if verbo not in VERBOS:
        raise ValueError(f"verbo desconhecido: {verbo}")
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
