"""Janelas do Windows: listar, escolher por trecho do título, focar, fechar."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


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
