"""Servidor HTTP do núcleo: /saude própria e /status compatível com o MVP."""
from __future__ import annotations

import errno
import logging
import os
import socket
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import __version__

log = logging.getLogger("vard")

SAIDA_PORTA_OCUPADA = 3
SAIDA_SEM_TOKEN = 2


def _verificar_porta(host: str, porta: int) -> None:
    """Tenta abrir o socket antes do uvicorn para gerar erro identificável."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, porta))
    except OSError as exc:
        raise exc
    finally:
        s.close()


def criar_app() -> FastAPI:
    """Cria a aplicação FastAPI do núcleo com /saude e preserva rotas da ponte.

    Idempotente: chamar múltiplas vezes não duplica a rota /saude.
    """
    # Importa a app da ponte (server.py) e adiciona /saude sem quebrar contratos existentes.
    # O import é tardio para que --versao não carregue dependências pesadas.
    from server import app as ponte_app  # type: ignore[import-untyped]

    # Evita duplicar /saude se criar_app() for chamada mais de uma vez.
    if not any(getattr(r, "path", None) == "/saude" for r in ponte_app.routes):
        @ponte_app.get("/saude")
        def saude():
            return {"ok": True, "versao": __version__, "pid": os.getpid()}

    return ponte_app


def servir(porta: int = 4700, host: str = "127.0.0.1") -> int:
    """Sobe o núcleo em loopback. Retorna código de saída específico para porta ocupada."""
    try:
        _verificar_porta(host, porta)
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, errno.WSAEADDRINUSE):  # type: ignore[attr-defined]
            print(f"porta {porta} ocupada", file=sys.stderr)
            return SAIDA_PORTA_OCUPADA
        print(f"não consegui abrir a porta {porta}: {exc}", file=sys.stderr)
        return 1

    app = criar_app()
    log.info("núcleo %s subindo em %s:%d (pid %d)", __version__, host, porta, os.getpid())
    uvicorn.run(app, host=host, port=porta, log_level="info", access_log=False)
    return 0