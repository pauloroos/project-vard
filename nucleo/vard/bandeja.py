"""Partes puras da bandeja: cor, ícone, título, aviso e itens de menu por modo."""
from __future__ import annotations

from PIL import Image, ImageDraw

CORES = {
    "ligado": (242, 177, 52), "ligando": (242, 177, 52), "jogo": (90, 90, 90),
    "parado": (120, 40, 40), "erro": (200, 40, 40),
}
TITULO_MAX = 120   # a dica do ícone no Windows corta em 128 caracteres


def cor_do_modo(modo: str) -> tuple[int, int, int]:
    return CORES.get(modo, (90, 90, 90))


def desenhar_icone(modo: str, tamanho: int = 64) -> Image.Image:
    im = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = tamanho // 8
    d.ellipse((m, m, tamanho - m, tamanho - m), fill=cor_do_modo(modo) + (255,))
    return im


def titulo(estado: dict, voz: str | None = None) -> str:
    """Dica do ícone. No erro, o detalhe que o vard-modo.ps1 gravou. `voz`: ligado/aquecendo/desligado."""
    modo = estado.get("modo", "desconhecido")
    texto = f"Vard: erro: {estado.get('detalhe') or 'sem detalhe'}" if modo == "erro" else f"Vard: {modo}"
    if voz and modo != "erro":
        texto += f" · voz: {voz}"
    return texto if len(texto) <= TITULO_MAX else texto[: TITULO_MAX - 1] + "…"


def deve_avisar(anterior: dict | None, atual: dict) -> bool:
    """Balão do Windows ao entrar em erro (ou quando o erro muda de detalhe)."""
    if atual.get("modo") != "erro":
        return False
    return anterior is None or anterior.get("modo") != "erro" or anterior.get("detalhe") != atual.get("detalhe")


def itens_menu(modo: str) -> list[tuple[str, str | None]]:
    itens: list[tuple[str, str | None]] = [("Abrir aba", "aba")]
    if modo == "ligado":
        itens += [("Modo jogo", "jogo"), ("Recarregar OpenJarvis", "recarregar"), ("Parar tudo", "parar")]
    elif modo == "ligando":
        itens += [("Voltar", "voltar"), ("Parar tudo", "parar")]
    elif modo == "erro":
        itens += [("Tentar de novo", "voltar"), ("Abrir log", "log"), ("Parar tudo", "parar")]
    else:
        itens += [("Voltar", "voltar")]
    itens += [("Preflight", "preflight"), ("", None), ("Sair da bandeja", "sair")]
    return itens
