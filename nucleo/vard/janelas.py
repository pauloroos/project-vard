"""Janelas do Windows: listar, escolher por trecho do título, focar, fechar, posicionar."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from vard import monitores
from vard.monitores import Monitor, Retangulo


@dataclass(frozen=True)
class Janela:
    hwnd: int
    titulo: str
    processo: str


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def escolher(lista: list[Janela], trecho: str) -> Janela | None:
    alvo = _simples(trecho).strip()
    if not alvo:
        return None
    candidatas = [j for j in lista if alvo in _simples(j.titulo)]
    if not candidatas:
        return None
    return min(candidatas, key=lambda j: len(j.titulo))


def listar() -> list[Janela]:
    import win32gui
    import win32process
    import psutil  # adicionado ao pyproject

    achadas: list[Janela] = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            titulo = win32gui.GetWindowText(hwnd)
            if not titulo:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                nome = psutil.Process(pid).name()
            except Exception:
                nome = "?"
            achadas.append(Janela(hwnd, titulo, nome))
        except Exception:
            # Uma janela ruim não pode abortar a enumeração inteira.
            return

    win32gui.EnumWindows(_cb, None)
    return achadas


def focar(j: Janela) -> bool:
    """Traz a janela para a frente. Devolve False se o Windows recusar (processo em segundo plano)."""
    import pywintypes
    import win32api
    import win32con
    import win32gui

    try:
        if win32gui.IsIconic(j.hwnd):
            win32gui.ShowWindow(j.hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(j.hwnd)
        except pywintypes.error:
            # O Windows só deixa trazer janela pra frente quem tem entrada recente:
            # um toque de Alt libera a permissão por um instante.
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(j.hwnd)
        return True
    except pywintypes.error:
        return False


def fechar(j: Janela) -> bool:
    """Pede para a janela fechar (WM_CLOSE). Devolve False se o hwnd já não existe."""
    import pywintypes
    import win32con
    import win32gui

    try:
        if not win32gui.IsWindow(j.hwnd):
            return False
        win32gui.PostMessage(j.hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except pywintypes.error:
        return False


def ativa() -> Janela | None:
    """A janela em primeiro plano (a que a pessoa está vendo)."""
    import win32gui
    import win32process
    import psutil

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    titulo = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        nome = psutil.Process(pid).name()
    except Exception:  # noqa: BLE001 — o nome do processo é só informativo
        nome = "?"
    return Janela(hwnd, titulo or "(sem título)", nome)


# --- Posição e tamanho -------------------------------------------------------------------------

POSICOES = {
    "maximizar": ("maximizar", "maximiza", "maximizada", "maximo", "maximize"),
    "minimizar": ("minimizar", "minimiza", "minimizada", "minimize"),
    "restaurar": ("restaurar", "restaura", "normal", "restore"),
    "esquerda": ("esquerda", "metade esquerda", "lado esquerdo", "left"),
    "direita": ("direita", "metade direita", "lado direito", "right"),
    "cima": ("cima", "em cima", "topo", "metade de cima", "superior", "top"),
    "baixo": ("baixo", "embaixo", "em baixo", "metade de baixo", "inferior", "bottom"),
    "centro": ("centro", "centralizar", "centraliza", "meio", "center"),
    "tela cheia": ("tela cheia", "tela inteira", "cheia", "fullscreen"),
}


def normalizar_posicao(texto: str) -> str:
    """Posição falada -> nome canônico; vazio fica vazio. ValueError com frase se não reconhecer."""
    t = _simples(texto or "").strip()
    if not t:
        return ""
    for canonica, sinonimos in POSICOES.items():
        if t in sinonimos or t == canonica:
            return canonica
    raise ValueError(f"Não conheço a posição '{texto}'. Use: {', '.join(POSICOES)}.")


@dataclass(frozen=True)
class Plano:
    """O que fazer com a janela: estado final e, se houver, o retângulo visível de destino."""
    estado: str                    # "normal", "maximizar", "minimizar" ou "restaurar"
    ret: Retangulo | None = None


def _caber(ret: Retangulo, area: Retangulo) -> Retangulo:
    """Limita o tamanho à área e empurra a janela para dentro dela."""
    largura = max(1, min(ret.largura, area.largura))
    altura = max(1, min(ret.altura, area.altura))
    x = min(max(ret.x, area.x), area.direita - largura)
    y = min(max(ret.y, area.y), area.baixo - altura)
    return Retangulo(x, y, largura, altura)


def proporcional(ret: Retangulo, origem: Retangulo, destino: Retangulo) -> Retangulo:
    """Leva a janela de uma área útil para outra mantendo posição e tamanho relativos."""
    fx = destino.largura / origem.largura if origem.largura else 1
    fy = destino.altura / origem.altura if origem.altura else 1
    novo = Retangulo(round(destino.x + (ret.x - origem.x) * fx), round(destino.y + (ret.y - origem.y) * fy),
                     round(ret.largura * fx), round(ret.altura * fy))
    return _caber(novo, destino)


def _mesmo(a: Monitor, b: Monitor) -> bool:
    return a.indice == b.indice and a.handle == b.handle


def planejar(atual: Retangulo, origem: Monitor, destino: Monitor, posicao: str = "",
             x: int | None = None, y: int | None = None,
             largura: int | None = None, altura: int | None = None) -> Plano:
    """Calcula o destino da janela. x/y contam a partir do canto da área útil do monitor de destino."""
    posicao = normalizar_posicao(posicao)
    troca = not _mesmo(origem, destino)
    area = destino.area
    base = proporcional(atual, origem.area, area) if troca else atual
    if posicao == "minimizar":
        return Plano("minimizar")
    if posicao in ("maximizar", "restaurar"):
        return Plano(posicao, base if troca else None)
    meia_l, meia_a = area.largura // 2, area.altura // 2
    if posicao == "esquerda":
        return Plano("normal", Retangulo(area.x, area.y, meia_l, area.altura))
    if posicao == "direita":
        return Plano("normal", Retangulo(area.x + meia_l, area.y, area.largura - meia_l, area.altura))
    if posicao == "cima":
        return Plano("normal", Retangulo(area.x, area.y, area.largura, meia_a))
    if posicao == "baixo":
        return Plano("normal", Retangulo(area.x, area.y + meia_a, area.largura, area.altura - meia_a))
    if posicao == "tela cheia":
        return Plano("normal", destino.tela)
    larg = largura if largura and largura > 0 else base.largura
    alt = altura if altura and altura > 0 else base.altura
    if posicao == "centro":
        larg, alt = min(larg, area.largura), min(alt, area.altura)
        return Plano("normal", Retangulo(area.x + (area.largura - larg) // 2, area.y + (area.altura - alt) // 2,
                                         larg, alt))
    if not troca and x is None and y is None and not largura and not altura:
        raise ValueError("Diga para onde mover: um monitor, uma posição ou x/y/largura/altura.")
    nx = area.x + x if x is not None else base.x
    ny = area.y + y if y is not None else base.y
    return Plano("normal", _caber(Retangulo(nx, ny, larg, alt), area))


def com_bordas(visivel: Retangulo, margens: tuple[int, int, int, int]) -> Retangulo:
    """O Windows 10/11 tem bordas invisíveis: converte o retângulo visível no da janela."""
    esq, topo, dir_, baixo = margens
    return Retangulo(visivel.x - esq, visivel.y - topo, visivel.largura + esq + dir_, visivel.altura + topo + baixo)


# Win32 em funções pequenas: os testes trocam estas e nunca mexem numa janela real.

def _estado(hwnd: int) -> str:
    import ctypes

    if ctypes.windll.user32.IsIconic(hwnd):
        return "minimizada"
    if ctypes.windll.user32.IsZoomed(hwnd):
        return "maximizada"
    return "normal"


def _mostrar(hwnd: int, comando: str) -> None:
    import win32con
    import win32gui

    codigos = {"maximizar": win32con.SW_MAXIMIZE, "minimizar": win32con.SW_MINIMIZE,
               "restaurar": win32con.SW_RESTORE}
    win32gui.ShowWindow(hwnd, codigos[comando])


def _retangulos(hwnd: int) -> tuple[Retangulo, tuple[int, int, int, int]]:
    """Retângulo visível (DWM) e as margens invisíveis em relação ao GetWindowRect."""
    import ctypes
    from ctypes import wintypes

    import win32gui

    janela = Retangulo.de_bordas(*win32gui.GetWindowRect(hwnd))
    quadro = wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS = 9
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(quadro),
                                                   ctypes.sizeof(quadro)) != 0:
        return janela, (0, 0, 0, 0)
    visivel = Retangulo.de_bordas(quadro.left, quadro.top, quadro.right, quadro.bottom)
    margens = (visivel.x - janela.x, visivel.y - janela.y, janela.direita - visivel.direita,
               janela.baixo - visivel.baixo)
    return visivel, tuple(max(0, m) for m in margens)


def _colocar(hwnd: int, ret: Retangulo) -> None:
    import win32con
    import win32gui

    win32gui.SetWindowPos(hwnd, 0, ret.x, ret.y, ret.largura, ret.altura,
                          win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)


def mover(j: Janela, origem: Monitor, destino: Monitor, posicao: str = "",
          x: int | None = None, y: int | None = None,
          largura: int | None = None, altura: int | None = None) -> Plano:
    """Aplica o plano na janela real e devolve o plano aplicado (para a frase de resposta)."""
    monitores.ativar_dpi()
    canonica = normalizar_posicao(posicao)
    troca = not _mesmo(origem, destino)
    if canonica == "minimizar":
        _mostrar(j.hwnd, "minimizar")
        return Plano("minimizar")
    if canonica in ("maximizar", "restaurar") and not troca:
        _mostrar(j.hwnd, canonica)
        return Plano(canonica)
    # Valida o pedido antes de mexer na janela (frase de erro sem efeito colateral).
    planejar(Retangulo(0, 0, 1, 1), origem, destino, canonica, x, y, largura, altura)
    if _estado(j.hwnd) != "normal":
        # Maximizada ou minimizada não aceita retângulo: volta ao normal antes de medir e mover.
        _mostrar(j.hwnd, "restaurar")
    visivel, margens = _retangulos(j.hwnd)
    plano = planejar(visivel, origem, destino, canonica, x, y, largura, altura)
    if plano.ret is not None:
        alvo = com_bordas(plano.ret, margens)
        _colocar(j.hwnd, alvo)
        if troca:
            # Monitor com DPI diferente faz o programa se redimensionar ao chegar: reaplica o retângulo.
            _colocar(j.hwnd, alvo)
    if plano.estado == "maximizar":
        _mostrar(j.hwnd, "maximizar")
    return plano
