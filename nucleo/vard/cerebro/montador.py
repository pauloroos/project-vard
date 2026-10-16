"""Montador único de adaptadores de provedor (T16d).

Usado por server.py (executor do cérebro próprio) e primeiro_uso/cerebro.py
(teste de conectividade). Mapeia tipo → adaptador concreto; credenciais são
resolvidas externamente (cofre ou segredos.toml) e passadas como parâmetro.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provedores import AdaptadorProvedor


def montar_adaptador(
    tipo: str,
    base_url: str,
    modelo: str,
    chave: str = "",
    timeout: float = 90.0,
) -> "AdaptadorProvedor":
    """Instancia o adaptador concreto para o tipo de provedor informado.

    Tipos suportados:
      - openai_compat, lmstudio, local → AdaptadorOpenAICompat
      - anthropic → AdaptadorAnthropic
      - google → AdaptadorGoogle
      - openai_nativo → AdaptadorOpenAINativo

    Levanta ValueError para tipos desconhecidos.
    """
    from .provedores import (
        AdaptadorAnthropic,
        AdaptadorGoogle,
        AdaptadorOpenAICompat,
        AdaptadorOpenAINativo,
    )

    if tipo in ("openai_compat", "lmstudio", "local"):
        return AdaptadorOpenAICompat(
            base_url=base_url, modelo=modelo, chave=chave, timeout=timeout
        )
    if tipo == "anthropic":
        return AdaptadorAnthropic(
            chave=chave, modelo=modelo, base_url=base_url, timeout=timeout
        )
    if tipo == "google":
        return AdaptadorGoogle(
            chave=chave, modelo=modelo, base_url=base_url, timeout=timeout
        )
    if tipo == "openai_nativo":
        return AdaptadorOpenAINativo(
            chave=chave, modelo=modelo, base_url=base_url, timeout=timeout
        )
    raise ValueError(f"tipo_de_provedor_desconhecido: {tipo}")