"""Capacidade do enxuto: a CLI enxuta só roda se cobre as ferramentas do cérebro local.

Contrato (plano 0.8 T17 / spec C5):
- ``verificar_enxuto(ferramentas_cli, ferramentas_local) -> (ok, faltando)``;
- o supervisor confere a lista que a CLI informa no evento de início da sessão e,
  se faltar ferramenta, reabre a sessão sem enxuto e registra o aviso aqui;
- ``GET /status`` expõe os avisos em ``cli_enxuto.avisos``.

Os avisos trazem só nomes de ferramenta e o id do provedor: sem segredo, sem
caminho e sem dado do usuário, com teto para não crescer sem fim.
"""
from __future__ import annotations

from typing import List, Tuple

LIMITE_AVISOS = 20

_avisos: List[str] = []


def verificar_enxuto(ferramentas_cli: List[str], ferramentas_local: List[str]) -> Tuple[bool, List[str]]:
    """Regra C5: ok=True só quando a CLI contém todas as ferramentas do cérebro local.

    ``faltando`` preserva a ordem do cérebro local e não repete nome, para o
    aviso dizer exatamente o que falta.
    """
    da_cli = {str(nome) for nome in ferramentas_cli or []}
    faltando: List[str] = []
    vistos: set[str] = set()
    for nome in ferramentas_local or []:
        chave = str(nome)
        if chave in da_cli or chave in vistos:
            continue
        vistos.add(chave)
        faltando.append(chave)
    return (not faltando, faltando)


def registrar_aviso(mensagem: str) -> None:
    """Guarda o aviso do enxuto para o /status, sem duplicar e com teto."""
    texto = str(mensagem).strip()
    if not texto:
        return
    if texto in _avisos:
        _avisos.remove(texto)
    _avisos.append(texto)
    del _avisos[:-LIMITE_AVISOS]


def avisos() -> List[str]:
    """Avisos do enxuto registrados, na ordem em que entraram."""
    return list(_avisos)


def limpar_avisos() -> None:
    """Esvazia os avisos (testes e troca de configuração)."""
    _avisos.clear()
