"""Regras de texto puras: encerramento por voz (D9), eco entre trilhas (D1), tempo legível."""
from __future__ import annotations

import difflib
import re
import unicodedata

from .armazenamento import Fala, mmss  # noqa: F401 (reexporta mmss)

# O nome aceita as grafias que o whisper dá (as mesmas de viewer/rotas.js VARIANTES) e pontuação depois dele.
# vard/reuniao.py guarda uma cópia idêntica deste padrão (o projeto da raiz não importa vard_reuniao): há teste que compara.
ENCERRAMENTO = re.compile(
    r"\b(?:aurora|vard|varde|vardi|ward|bard)[\s,.!?:]+"
    r"(?:encerra|encerre|encerrar|para|pare|parar|termina|termine|terminar|terminou|acabou|acaba)\s+"
    r"(?:(?:a|essa|esta|aqui a)\s+)?reuni[aã]o\b", re.I)


def simples(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def e_encerramento(texto: str) -> bool:
    return bool(ENCERRAMENTO.search(unicodedata.normalize("NFKC", str(texto))))


def similaridade(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, simples(a), simples(b)).ratio()


def eco(fala_eu: Fala, outros: list[Fala], limiar: float = 0.8, folga_s: float = 1.0) -> bool:
    for o in outros:
        sobrepoe = o.t0 - folga_s <= fala_eu.t1 and o.t1 + folga_s >= fala_eu.t0
        if sobrepoe and similaridade(fala_eu.texto, o.texto) >= limiar:
            return True
    return False
