"""Sanitização de textos para provas e logs: remove segredos e dados pessoais.

Usado por scripts/provas/prova-real-ferramentas.py e pelos testes automatizados.
Nunca imprime valores; só substitui por marcadores genéricos.
"""
from __future__ import annotations

import os
import re


def sanitizar(texto: str) -> str:
    """Remove segredos, endpoints, modelos e caminhos pessoais do texto."""
    if not isinstance(texto, str):
        texto = str(texto)

    # Remove valores de variáveis de ambiente sensíveis
    for var in ("OMNI_API_KEY", "OMNI_BASE_URL", "OMNI_MODELO"):
        valor = os.environ.get(var, "")
        if valor and len(valor) > 3:
            texto = texto.replace(valor, "***")

    # Padrões genéricos de tokens/chaves
    texto = re.sub(r"(Bearer\s+)\S+", r"\1***", texto, flags=re.IGNORECASE)
    texto = re.sub(r'\bsk-[A-Za-z0-9_-]{10,}\b', 'sk-***', texto)
    texto = re.sub(r'(api[_-]?key["\s:=]+)\S+', r'\1***', texto, flags=re.IGNORECASE)
    texto = re.sub(r'(token[=:]\s*)\S+', r'\1***', texto, flags=re.IGNORECASE)
    texto = re.sub(r'(chave[=:]\s*)\S+', r'\1***', texto, flags=re.IGNORECASE)

    # Caminhos absolutos pessoais (/home/user, /Users/user, C:\Users\)
    texto = re.sub(r'/home/[A-Za-z0-9_.-]+', '/home/***', texto)
    texto = re.sub(r'/Users/[A-Za-z0-9_.-]+', '/Users/***', texto)
    texto = re.sub(r'[A-Z]:\\Users\\[A-Za-z0-9_. -]+', r'C:\\Users\\***', texto)

    return texto


def verificar_ambiente() -> list[str]:
    """Retorna lista de variáveis obrigatórias ausentes para prova real."""
    obrigatorias = ["OMNI_BASE_URL", "OMNI_API_KEY", "OMNI_MODELO"]
    return [v for v in obrigatorias if not os.environ.get(v, "").strip()]