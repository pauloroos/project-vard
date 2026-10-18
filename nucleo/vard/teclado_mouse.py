"""Clique, digitação, teclas e rolagem pelo SendInput do Windows (ctypes puro).

A montagem dos eventos é pura (testável); só `_enviar` e `_posicionar_cursor` tocam o Windows,
e os testes trocam as duas. Coordenadas em pixels físicos da área de trabalho virtual.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

LIMITE_TEXTO = 4000
LIMITE_REPETICOES = 50
LIMITE_ROLAGEM = 50
DELTA_RODA = 120

# Eventos abstratos: ("tecla", vk, solta, estendida) | ("unicode", unidade_utf16, solta)
#                    ("mouse", flag) | ("roda", delta)

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN = 0x10, 0x11, 0x12, 0x5B
VK_RETURN, VK_TAB = 0x0D, 0x09

MODIFICADORES = {
    "ctrl": VK_CONTROL, "control": VK_CONTROL, "controle": VK_CONTROL,
    "shift": VK_SHIFT, "maiusculas": VK_SHIFT,
    "alt": VK_MENU,
    "win": VK_LWIN, "windows": VK_LWIN, "super": VK_LWIN, "meta": VK_LWIN,
}

TECLAS = {
    "enter": VK_RETURN, "return": VK_RETURN, "entrar": VK_RETURN,
    "esc": 0x1B, "escape": 0x1B, "tab": VK_TAB,
    "espaco": 0x20, "space": 0x20, "barra de espaco": 0x20,
    "backspace": 0x08, "apagar": 0x08, "voltar": 0x08,
    "delete": 0x2E, "del": 0x2E, "excluir": 0x2E,
    "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "inicio": 0x24, "end": 0x23, "fim": 0x23,
    "pageup": 0x21, "page up": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "page down": 0x22, "pgdn": 0x22,
    "up": 0x26, "cima": 0x26, "seta cima": 0x26, "seta para cima": 0x26,
    "down": 0x28, "baixo": 0x28, "seta baixo": 0x28, "seta para baixo": 0x28,
    "left": 0x25, "esquerda": 0x25, "seta esquerda": 0x25, "seta para esquerda": 0x25,
    "right": 0x27, "direita": 0x27, "seta direita": 0x27, "seta para direita": 0x27,
    "menu": 0x5D, "contexto": 0x5D,
    "printscreen": 0x2C, "print screen": 0x2C,
    "mais": 0xBB, "menos": 0xBD,
    "volume mudo": 0xAD, "volume menos": 0xAE, "volume mais": 0xAF,
    "play": 0xB3, "pausar midia": 0xB3, "proxima faixa": 0xB0, "faixa anterior": 0xB1,
}
TECLAS.update({f"f{n}": 0x6F + n for n in range(1, 25)})

# Teclas que precisam da marca "estendida" (senão viram teclado numérico com NumLock).
ESTENDIDAS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5D, 0x2C}

BOTOES = {
    "esquerdo": (0x0002, 0x0004), "left": (0x0002, 0x0004),
    "direito": (0x0008, 0x0010), "right": (0x0008, 0x0010),
    "meio": (0x0020, 0x0040), "middle": (0x0020, 0x0040),
}
MOUSEEVENTF_WHEEL = 0x0800


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().lower()


@dataclass(frozen=True)
class Combinacao:
    modificadores: tuple[int, ...]
    vk: int
    shift_da_tecla: bool = False   # caractere que no layout atual exige Shift (ex.: '?' no ABNT2)


def _vk_do_caractere(ch: str) -> tuple[int, bool] | None:
    """VK e se precisa de Shift para o caractere no layout de teclado atual (VkKeyScanW)."""
    import ctypes

    r = ctypes.windll.user32.VkKeyScanW(ord(ch))
    if r == -1 or r & 0xFF == 0xFF:
        return None
    return r & 0xFF, bool(r & 0x100)


def interpretar(combinacao: str) -> Combinacao:
    """'ctrl+l', 'ctrl + shift + t', 'enter', 'alt+f4', 'seta para baixo' -> Combinacao.

    Levanta ValueError com frase pronta quando não entende.
    """
    bruto = (combinacao or "").strip()
    if not bruto:
        raise ValueError("Diga qual tecla apertar (ex.: enter, ctrl+l).")
    if bruto.endswith("++"):
        partes = [p for p in bruto[:-2].split("+")] + ["+"]
    else:
        partes = bruto.split("+")
    partes = [p.strip() for p in partes if p.strip()]
    if not partes:
        raise ValueError(f"Não entendi a combinação '{combinacao}'.")
    *mods_txt, tecla_txt = partes
    mods: list[int] = []
    for m in mods_txt:
        vk = MODIFICADORES.get(_simples(m))
        if vk is None:
            raise ValueError(f"'{m}' não é ctrl, shift, alt ou win.")
        if vk not in mods:
            mods.append(vk)
    chave = _simples(tecla_txt)
    if chave in MODIFICADORES and not mods_txt:
        return Combinacao((), MODIFICADORES[chave])
    if {VK_CONTROL, VK_MENU} <= set(mods) and chave in ("delete", "del", "excluir"):
        raise ValueError("O Windows não deixa programas enviarem Ctrl+Alt+Del.")
    if chave in TECLAS:
        return Combinacao(tuple(mods), TECLAS[chave])
    if len(tecla_txt) == 1:
        ch = tecla_txt
        if ch.isascii() and ch.isalpha():
            return Combinacao(tuple(mods), ord(ch.upper()))
        if ch.isdigit():
            return Combinacao(tuple(mods), ord(ch))
        achado = _vk_do_caractere(ch)
        if achado:
            vk, shift = achado
            return Combinacao(tuple(mods), vk, shift)
    raise ValueError(f"Não conheço a tecla '{tecla_txt}'. Exemplos: enter, tab, esc, f5, ctrl+l, alt+tab.")


def eventos_combinacao(c: Combinacao) -> list[tuple]:
    mods = list(c.modificadores)
    if c.shift_da_tecla and VK_SHIFT not in mods:
        mods.append(VK_SHIFT)
    ev: list[tuple] = [("tecla", m, False, m in ESTENDIDAS) for m in mods]
    ev.append(("tecla", c.vk, False, c.vk in ESTENDIDAS))
    ev.append(("tecla", c.vk, True, c.vk in ESTENDIDAS))
    ev.extend(("tecla", m, True, m in ESTENDIDAS) for m in reversed(mods))
    return ev


def eventos_texto(texto: str) -> list[tuple]:
    """Cada caractere vira Unicode (independe do layout ABNT2); quebra de linha vira Enter."""
    ev: list[tuple] = []
    for ch in texto.replace("\r\n", "\n"):
        if ch == "\n":
            ev += [("tecla", VK_RETURN, False, False), ("tecla", VK_RETURN, True, False)]
            continue
        if ch == "\t":
            ev += [("tecla", VK_TAB, False, False), ("tecla", VK_TAB, True, False)]
            continue
        dados = ch.encode("utf-16-le")
        unidades = [int.from_bytes(dados[i:i + 2], "little") for i in range(0, len(dados), 2)]
        for u in unidades:
            ev.append(("unicode", u, False))
        for u in unidades:
            ev.append(("unicode", u, True))
    return ev


def eventos_clique(botao: str = "esquerdo", duplo: bool = False) -> list[tuple]:
    par = BOTOES.get(_simples(botao or "esquerdo"))
    if par is None:
        raise ValueError(f"Botão '{botao}' não existe; use esquerdo, direito ou meio.")
    desce, sobe = par
    uma = [("mouse", desce), ("mouse", sobe)]
    return uma * (2 if duplo else 1)


def eventos_rolagem(quantidade: int) -> list[tuple]:
    """Positivo desce a página, negativo sobe (em 'cliques' da roda)."""
    if not quantidade:
        raise ValueError("Diga quanto rolar (positivo desce, negativo sobe).")
    if abs(quantidade) > LIMITE_ROLAGEM:
        raise ValueError(f"Role no máximo {LIMITE_ROLAGEM} de cada vez.")
    passo = -DELTA_RODA if quantidade > 0 else DELTA_RODA
    return [("roda", passo)] * abs(quantidade)


# --- Windows ---------------------------------------------------------------------------------

def _enviar(eventos: list[tuple]) -> int:
    """Converte para INPUT[] e chama SendInput. Devolve quantos eventos o Windows aceitou."""
    import ctypes
    from ctypes import wintypes

    ulong_ptr = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    KEYUP, UNICODE, EXTENDED = 0x0002, 0x0004, 0x0001
    lista = (INPUT * len(eventos))()
    for i, ev in enumerate(eventos):
        tipo = ev[0]
        if tipo == "tecla":
            _, vk, solta, estendida = ev
            flags = (KEYUP if solta else 0) | (EXTENDED if estendida else 0)
            lista[i].type = 1
            lista[i].u.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
        elif tipo == "unicode":
            _, unidade, solta = ev
            lista[i].type = 1
            lista[i].u.ki = KEYBDINPUT(0, unidade, UNICODE | (KEYUP if solta else 0), 0, 0)
        elif tipo == "mouse":
            lista[i].type = 0
            lista[i].u.mi = MOUSEINPUT(0, 0, 0, ev[1], 0, 0)
        elif tipo == "roda":
            lista[i].type = 0
            lista[i].u.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(ev[1]).value, MOUSEEVENTF_WHEEL, 0, 0)
    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
    return int(user32.SendInput(len(eventos), ctypes.byref(lista), ctypes.sizeof(INPUT)))


def _posicionar_cursor(x: int, y: int) -> bool:
    import ctypes

    from vard import monitores

    monitores.ativar_dpi()
    return bool(ctypes.windll.user32.SetCursorPos(int(x), int(y)))


def _conferir(eventos: list[tuple]) -> None:
    aceitos = _enviar(eventos)
    if aceitos != len(eventos):
        raise RuntimeError("o Windows bloqueou a entrada (janela de administrador ou tela bloqueada?)")


def clicar(x: int, y: int, botao: str = "esquerdo", duplo: bool = False) -> None:
    eventos = eventos_clique(botao, duplo)
    if not _posicionar_cursor(x, y):
        raise RuntimeError("o Windows não deixou mover o cursor")
    _conferir(eventos)


def digitar(texto: str) -> int:
    if len(texto) > LIMITE_TEXTO:
        raise ValueError(f"Texto longo demais: digito até {LIMITE_TEXTO} caracteres por vez.")
    eventos = eventos_texto(texto)
    if eventos:
        _conferir(eventos)
    return len(texto)


def teclar(combinacao: str, vezes: int = 1) -> Combinacao:
    if not 1 <= vezes <= LIMITE_REPETICOES:
        raise ValueError(f"Repita de 1 a {LIMITE_REPETICOES} vezes.")
    c = interpretar(combinacao)
    _conferir(eventos_combinacao(c) * vezes)
    return c


def rolar(quantidade: int, x: int | None = None, y: int | None = None) -> None:
    eventos = eventos_rolagem(quantidade)
    if x is not None and y is not None and not _posicionar_cursor(x, y):
        raise RuntimeError("o Windows não deixou mover o cursor")
    _conferir(eventos)
