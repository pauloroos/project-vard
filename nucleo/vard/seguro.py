"""Contrato das ferramentas MCP do Vard: sempre uma frase em português, nunca exceção."""
from __future__ import annotations

import functools

from vard.mcp_http import ErroMCP


class Frase(Exception):
    """Falha que já é a frase para o usuário (sem prefixo técnico)."""


def seguro(acao: str):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Frase as exc:
                return str(exc)
            except ErroMCP as exc:
                return f"Não consegui {acao}: o serviço de memória respondeu com erro ({str(exc)[:80]})."
            except Exception as exc:  # noqa: BLE001 — contrato: a ferramenta nunca levanta
                return f"Não consegui {acao}: {type(exc).__name__}: {exc}"[:400]
        return wrapper
    return deco
