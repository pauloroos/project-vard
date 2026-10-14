"""Normaliza o texto antes da síntese (XTTS v2 verbaliza ponto final e erra números/horas)."""
from __future__ import annotations

import re

from num2words import num2words

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

ORD_M = {1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto", 6: "sexto",
         7: "sétimo", 8: "oitavo", 9: "nono", 10: "décimo"}
ORD_F = {k: v[:-1] + "a" for k, v in ORD_M.items()}


def _card(n: int) -> str:
    return num2words(n, lang="pt_BR")


def _fem(n: int) -> str:
    return {1: "uma", 2: "duas"}.get(n) or _card(n)


def _int_pt(s: str) -> int:
    return int(s.replace(".", ""))


def _decimal_pt(s: str) -> str:
    """'3,5' / '1.200,50' (sem sinal) -> palavras."""
    inteiro, _, dec = s.partition(",")
    txt = _card(_int_pt(inteiro))
    if dec:
        zeros = len(dec) - len(dec.lstrip("0"))
        resto = dec.lstrip("0")
        partes = ["zero"] * zeros
        if resto:
            partes.append(_card(int(resto)))
        txt += " vírgula " + " ".join(partes)
    return txt


# ---------- Markdown ----------
def _markdown(t: str) -> str:
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\*\s+", "", t, flags=re.M)
    t = t.replace("`", "").replace("*", "").replace("_", " ")
    linhas = [ln.strip() for ln in t.splitlines() if ln.strip()]
    saida = []
    for i, ln in enumerate(linhas):
        if i < len(linhas) - 1 and not re.search(r"[.!?…,;:]$", ln):
            ln += ","
        saida.append(ln)
    return " ".join(saida)


# ---------- URLs e e-mails ----------
TLD = r"(?:com\.br|com|org|net|dev|io|app|gov\.br|gov|edu|br|ai|me|tv)"


def _dominio(m: re.Match) -> str:
    return m.group(0).replace(".", " ponto ")


def _urls(t: str) -> str:
    t = re.sub(r"\b(?:https?://|www\.)", "", t, flags=re.I)
    t = re.sub(r"\b([\w.+-]+)@([\w-]+(?:\.[\w-]+)*\.[a-z]{2,})\b",
               lambda m: f"{m.group(1).replace('.', ' ponto ')} arroba {m.group(2).replace('.', ' ponto ')}", t, flags=re.I)
    t = re.sub(rf"\b[\w-]+(?:\.[\w-]+)*\.{TLD}\b(?:/[\w./%-]*)?",
               lambda m: _dominio(m).replace("/", " barra "), t, flags=re.I)
    return t


# ---------- datas ----------
def _data(m: re.Match) -> str:
    d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= d <= 31 and 1 <= mes <= 12):
        return m.group(0)
    dia = "primeiro" if d == 1 else _card(d)
    return f"{dia} de {MESES[mes - 1]} de {_card(a)}"


# ---------- horas ----------
def _hora(h: int, mi: int | None, s: int | None = None) -> str | None:
    if h > 23 or (mi is not None and mi > 59) or (s is not None and s > 59):
        return None
    if mi is None or mi == 0:
        base = f"{_fem(h)} hora" + ("" if h == 1 else "s") if h != 0 else "zero hora"
    else:
        base = f"{_fem(h)} e {_card(mi)}"
    if s:
        base += f" e {_card(s)} segundo" + ("" if s == 1 else "s")
    return base


def _hora_h(m: re.Match) -> str:
    r = _hora(int(m.group(1)), int(m.group(2)) if m.group(2) else None)
    return r or m.group(0)


def _hora_dp(m: re.Match) -> str:
    r = _hora(int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    return r or m.group(0)


# ---------- valores ----------
NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def _dinheiro(m: re.Match) -> str:
    inteiro, cent = m.group(1), m.group(2)
    reais = _int_pt(inteiro)
    c = int(cent.ljust(2, "0")) if cent else 0
    partes = []
    if reais or not c:
        partes.append(f"{_card(reais)} " + ("real" if reais == 1 else "reais"))
    if c:
        partes.append(f"{_card(c)} " + ("centavo" if c == 1 else "centavos"))
    return " e ".join(partes)


UNIDADES = [  # (regex após o número, singular, plural)
    (r"km/h", "quilômetro por hora", "quilômetros por hora"),
    (r"km", "quilômetro", "quilômetros"),
    (r"kg", "quilo", "quilos"),
    (r"°\s?C", "grau", "graus"),
    (r"°", "grau", "graus"),
    (r"%", "por cento", "por cento"),
]


def _com_unidade(m: re.Match, sing: str, plur: str) -> str:
    bruto = m.group(1)
    um = bruto == "1"
    return f"{_decimal_pt(bruto)} {sing if um else plur}"


def _ordinal(m: re.Match) -> str:
    n, suf = int(m.group(1)), m.group(2)
    tab = ORD_F if suf == "ª" else ORD_M
    return tab.get(n, f"{_card(n)}{'a' if suf == 'ª' else ''}")


def _numeros(t: str) -> str:
    return re.sub(rf"(?<![\w,.])({NUM})(?![\d])", lambda m: _decimal_pt(m.group(1)), t)


# ---------- abreviações ----------
ABREV = [
    (r"\bDra\.", "doutora"), (r"\bDr\.", "doutor"), (r"\bSra\.", "senhora"),
    (r"\bSrta\.", "senhorita"), (r"\bSr\.", "senhor"), (r"\bProfa\.", "professora"),
    (r"\bProf\.", "professor"), (r"\betc\.", "etcétera"), (r"\bp\.\s?ex\.", "por exemplo"),
    (r"\bkm/h\b", "quilômetros por hora"),
]


def normalizar(texto: str) -> str:
    original = texto.strip()
    t = _markdown(original)
    for pad, rep in ABREV:
        t = re.sub(pad, rep, t, flags=re.I)
    t = _urls(t)
    t = re.sub(r"(^|[\s(])-(?=\d)", r"\1menos ", t)
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", _data, t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", _hora_dp, t)
    t = re.sub(r"\b(\d{1,2})h(\d{2})?\b", _hora_h, t)
    t = re.sub(rf"R\$\s*(\d{{1,3}}(?:\.\d{{3}})+|\d+)(?:,(\d{{1,2}}))?", _dinheiro, t)
    for pad, sing, plur in UNIDADES:
        t = re.sub(rf"({NUM})\s?{pad}(?!\w)", lambda m, s=sing, p=plur: _com_unidade(m, s, p), t)
    t = re.sub(r"\b(\d+)\s?([ºª])", _ordinal, t)
    t = _numeros(t)
    # pontuação
    t = re.sub(r"\s*(?:…|\.{3,})\s*", ", ", t)
    t = re.sub(r"\s+([,;:.!?])", r"\1", t)
    # "?" final fica (só muda a entonação, o XTTS não o verbaliza); ponto, "!" e fechamentos saem.
    t = re.sub(r"[\s.!…,;:\"'”’)\]»]+$", "", t)
    t = re.sub(r"[?!.\s\"'”’)\]»]*\?[?!.\s\"'”’)\]»]*$", "?", t)
    t = re.sub(r"^[\s,;:.!?…\"'“‘(\[«]+", "", t)
    t = re.sub(r",\s*,+", ",", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or original
