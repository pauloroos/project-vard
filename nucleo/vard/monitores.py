"""Monitores do Windows: listar, escolher pelo pedido falado e localizar um ponto ou uma janela.

Todas as coordenadas são pixels físicos da área de trabalho virtual (o processo fica "per-monitor
DPI aware"): batem com o print_da_tela, com os retângulos da UI Automation e com o clique.
A numeração é da esquerda para a direita (e de cima para baixo no empate), começando em 1.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Retangulo:
    x: int
    y: int
    largura: int
    altura: int

    @property
    def direita(self) -> int:
        return self.x + self.largura

    @property
    def baixo(self) -> int:
        return self.y + self.altura

    def contem(self, px: int, py: int) -> bool:
        return self.x <= px < self.direita and self.y <= py < self.baixo

    @classmethod
    def de_bordas(cls, esquerda: int, topo: int, direita: int, baixo: int) -> "Retangulo":
        return cls(int(esquerda), int(topo), int(direita) - int(esquerda), int(baixo) - int(topo))


@dataclass(frozen=True)
class Monitor:
    indice: int
    nome: str
    tela: Retangulo        # o monitor inteiro
    area: Retangulo        # área útil (sem a barra de tarefas)
    principal: bool
    escala: int = 100      # % do Windows (100, 125, 150...)
    handle: int = 0


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().strip().lower()


def numerar(brutos: list[Monitor]) -> list[Monitor]:
    """Ordena da esquerda para a direita e numera a partir de 1."""
    ordem = sorted(brutos, key=lambda m: (m.tela.x, m.tela.y))
    return [Monitor(i, m.nome, m.tela, m.area, m.principal, m.escala, m.handle) for i, m in enumerate(ordem, 1)]


ORDINAIS = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5, "sexto": 6}


def escolher(lista: list[Monitor], pedido: int | str | None, atual: Monitor | None = None) -> Monitor:
    """Resolve 'monitor' do pedido: número, 'principal', 'outro', 'esquerda', 'direita', ordinal.

    Vazio devolve o atual (ou o principal). Levanta ValueError com frase pronta se não existir.
    """
    if not lista:
        raise ValueError("Não encontrei nenhum monitor.")
    principal = next((m for m in lista if m.principal), lista[0])
    if pedido is None or (isinstance(pedido, str) and not pedido.strip()):
        return atual or principal
    if isinstance(pedido, bool):
        raise ValueError("Monitor inválido.")
    texto = _simples(pedido) if isinstance(pedido, str) else ""
    texto = texto.removeprefix("monitor").strip().removeprefix("do ").removeprefix("da ").strip()
    numero: int | None = pedido if isinstance(pedido, int) else None
    if numero is None and texto.isdigit():
        numero = int(texto)
    if numero is None and texto in ORDINAIS:
        numero = ORDINAIS[texto]
    if numero is not None:
        achado = next((m for m in lista if m.indice == numero), None)
        if achado is None:
            indices = ", ".join(str(m.indice) for m in lista)
            raise ValueError(f"Não há monitor {numero}; há {len(lista)} ({indices}).")
        return achado
    if texto in ("principal", "primario", "main"):
        return principal
    if texto in ("outro", "proximo", "seguinte", "o outro", "next"):
        base = atual or principal
        return lista[(lista.index(base) + 1) % len(lista)] if base in lista else lista[0]
    if texto in ("anterior",):
        base = atual or principal
        return lista[(lista.index(base) - 1) % len(lista)] if base in lista else lista[0]
    if texto in ("esquerda", "esquerdo", "left"):
        return lista[0]
    if texto in ("direita", "direito", "right"):
        return lista[-1]
    raise ValueError(f"Não entendi o monitor '{pedido}'. Use o número de listar_monitores, 'principal' ou 'outro'.")


def do_ponto(lista: list[Monitor], x: int, y: int) -> Monitor | None:
    return next((m for m in lista if m.tela.contem(x, y)), None)


def area_virtual(lista: list[Monitor]) -> Retangulo:
    esquerda = min(m.tela.x for m in lista)
    topo = min(m.tela.y for m in lista)
    direita = max(m.tela.direita for m in lista)
    baixo = max(m.tela.baixo for m in lista)
    return Retangulo.de_bordas(esquerda, topo, direita, baixo)


def descrever(m: Monitor) -> str:
    t, a = m.tela, m.area
    texto = (f"{m.indice}: {m.nome}, {t.largura}x{t.altura} em ({t.x},{t.y}), escala {m.escala}%, "
             f"área útil {a.largura}x{a.altura} em ({a.x},{a.y})")
    return texto + (", principal" if m.principal else "")


# --- Windows ---------------------------------------------------------------------------------

_DPI_ATIVO = False


def ativar_dpi() -> None:
    """Faz o processo enxergar pixels físicos em todos os monitores (uma vez; falha é inofensiva)."""
    global _DPI_ATIVO
    if _DPI_ATIVO:
        return
    _DPI_ATIVO = True
    try:
        import ctypes

        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass


def _escala(handle: int) -> int:
    try:
        import ctypes
        from ctypes import wintypes

        dx, dy = wintypes.UINT(), wintypes.UINT()
        if ctypes.windll.shcore.GetDpiForMonitor(wintypes.HMONITOR(handle), 0, ctypes.byref(dx), ctypes.byref(dy)) == 0:
            return round(dx.value * 100 / 96)
    except (AttributeError, OSError):
        pass
    return 100


def _nome_amigavel(dispositivo: str) -> str:
    curto = dispositivo.replace("\\\\.\\", "")
    try:
        import win32api

        amigavel = win32api.EnumDisplayDevices(dispositivo, 0).DeviceString
    except Exception:  # noqa: BLE001 — nome é só enfeite
        amigavel = ""
    return f"{curto} ({amigavel})" if amigavel else curto


def listar() -> list[Monitor]:
    import win32api

    ativar_dpi()
    brutos = []
    for handle, _dc, _ret in win32api.EnumDisplayMonitors(None, None):
        info = win32api.GetMonitorInfo(handle)
        h = int(handle)
        brutos.append(Monitor(0, _nome_amigavel(info.get("Device", "")), Retangulo.de_bordas(*info["Monitor"]),
                              Retangulo.de_bordas(*info["Work"]), bool(info.get("Flags", 0) & 1), _escala(h), h))
    return numerar(brutos)


def da_janela(lista: list[Monitor], hwnd: int) -> Monitor | None:
    """Monitor onde a maior parte da janela está."""
    import win32api

    ativar_dpi()
    h = int(win32api.MonitorFromWindow(hwnd, 2))  # MONITOR_DEFAULTTONEAREST
    return next((m for m in lista if m.handle == h), None)
