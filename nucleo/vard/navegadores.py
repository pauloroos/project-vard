"""Achar o executável de um navegador pelo nome falado (brave, chrome, edge, firefox, opera...).

Ordem: App Paths do registro, StartMenuInternet do registro e, por último, as pastas padrão de
instalação. Só leitura: quem abre o navegador é a mesa.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class Navegador:
    chave: str
    nome: str                      # nome para a frase de resposta
    exes: tuple[str, ...]          # nomes em App Paths
    marcas: tuple[str, ...]        # trechos do nome da subchave em StartMenuInternet
    pastas: tuple[str, ...]        # caminhos padrão com %VARIAVEL%


CONHECIDOS = (
    Navegador("brave", "Brave", ("brave.exe",), ("brave",), (
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")),
    Navegador("chrome", "Google Chrome", ("chrome.exe",), ("google chrome", "chrome"), (
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
    Navegador("edge", "Microsoft Edge", ("msedge.exe",), ("edge",), (
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")),
    Navegador("firefox", "Firefox", ("firefox.exe",), ("firefox",), (
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe")),
    Navegador("opera gx", "Opera GX", (), ("opera gx", "operagx"), (
        r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe",)),
    Navegador("opera", "Opera", ("opera.exe",), ("opera",), (
        r"%LOCALAPPDATA%\Programs\Opera\launcher.exe",
        r"%ProgramFiles%\Opera\launcher.exe")),
    Navegador("vivaldi", "Vivaldi", ("vivaldi.exe",), ("vivaldi",), (
        r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
        r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe")),
    Navegador("chromium", "Chromium", ("chromium.exe",), ("chromium",), (
        r"%LOCALAPPDATA%\Chromium\Application\chrome.exe",)),
)

APELIDOS = {"google chrome": "chrome", "google": "chrome", "microsoft edge": "edge", "msedge": "edge",
            "mozilla firefox": "firefox", "mozilla": "firefox", "brave browser": "brave", "operagx": "opera gx"}
_PALAVRAS_SOLTAS = ("o navegador", "navegador", "browser", "no ", "o ")

APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
START_MENU = (r"SOFTWARE\Clients\StartMenuInternet", r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet")


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().strip().lower()


def normalizar_nome(texto: str) -> str:
    t = _simples(texto)
    for palavra in _PALAVRAS_SOLTAS:
        if t.startswith(palavra):
            t = t[len(palavra):].strip()
    t = t.removesuffix(".exe").strip()
    return APELIDOS.get(t, t)


def conhecido(nome: str) -> Navegador | None:
    chave = normalizar_nome(nome)
    return next((n for n in CONHECIDOS if n.chave == chave), None)


# --- Registro: funções pequenas que os testes trocam ------------------------------------------

def _ler_valor(raiz: str, caminho: str) -> str | None:
    """Valor padrão de uma chave (raiz 'HKCU' ou 'HKLM'); None se não existir."""
    import winreg

    base = winreg.HKEY_CURRENT_USER if raiz == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        with winreg.OpenKey(base, caminho) as chave:
            valor, _tipo = winreg.QueryValueEx(chave, "")
            return str(valor) if valor else None
    except OSError:
        return None


def _subchaves(raiz: str, caminho: str) -> list[str]:
    import winreg

    base = winreg.HKEY_CURRENT_USER if raiz == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    nomes: list[str] = []
    try:
        with winreg.OpenKey(base, caminho) as chave:
            i = 0
            while True:
                try:
                    nomes.append(winreg.EnumKey(chave, i))
                except OSError:
                    break
                i += 1
    except OSError:
        return []
    return nomes


def _existe(caminho: str) -> bool:
    return Path(caminho).is_file()


def exe_do_comando(comando: str) -> str:
    """'"X:\\x\\brave.exe" --arg' ou 'X:\\x\\brave.exe --arg' -> caminho do exe."""
    c = comando.strip()
    if c.startswith('"'):
        return c[1:].split('"', 1)[0]
    baixo = c.lower()
    fim = baixo.find(".exe")
    return c[: fim + 4] if fim >= 0 else c


def _expandir(caminho: str, ambiente: dict[str, str]) -> str | None:
    """Troca %VAR% sem diferenciar maiúsculas (o Windows guarda PROGRAMFILES); None se faltar alguma."""
    valores = {k.upper(): v for k, v in ambiente.items() if v}
    faltou = False

    def trocar(m: re.Match) -> str:
        nonlocal faltou
        valor = valores.get(m.group(1).upper())
        if valor is None:
            faltou = True
            return ""
        return valor

    saida = re.sub(r"%([^%]+)%", trocar, caminho)
    return None if faltou else saida


def _start_menu() -> Iterable[tuple[str, str]]:
    """(nome da subchave, exe) de cada navegador registrado no menu Iniciar."""
    for raiz in ("HKCU", "HKLM"):
        for caminho in START_MENU:
            for sub in _subchaves(raiz, caminho):
                comando = _ler_valor(raiz, rf"{caminho}\{sub}\shell\open\command")
                if comando:
                    yield sub, exe_do_comando(comando)


def instalados() -> list[str]:
    """Nomes dos navegadores que o Windows conhece (para a frase de 'não encontrei')."""
    vistos: list[str] = []
    for sub, exe in _start_menu():
        if _existe(exe):
            n = next((c.nome for c in CONHECIDOS if any(m in _simples(sub) for m in c.marcas)), None)
            n = n or ("Internet Explorer" if _simples(sub) == "iexplore.exe" else sub)
            if n not in vistos:
                vistos.append(n)
    return vistos


def resolver(nome: str, ambiente: dict[str, str] | None = None,
             existe: Callable[[str], bool] | None = None) -> tuple[str, str] | None:
    """Devolve (nome bonito, caminho do exe) ou None se o navegador não estiver instalado."""
    existe = existe or _existe
    ambiente = dict(os.environ) if ambiente is None else ambiente
    chave = normalizar_nome(nome)
    if not chave:
        return None
    nav = conhecido(chave)
    exes = nav.exes if nav else (f"{chave.replace(' ', '')}.exe",)
    marcas = nav.marcas if nav else (chave,)
    bonito = nav.nome if nav else nome.strip()
    for exe in exes:
        for raiz in ("HKCU", "HKLM"):
            achado = _ler_valor(raiz, rf"{APP_PATHS}\{exe}")
            if achado and existe(exe_do_comando(achado)):
                return bonito, exe_do_comando(achado)
    for sub, exe in _start_menu():
        s = _simples(sub)
        # "opera" não pode casar com "Opera GX" quando o pedido é o Opera comum (e vice-versa).
        if nav and nav.chave == "opera" and "gx" in s:
            continue
        if any(m in s for m in marcas) and existe(exe):
            return bonito, exe
    for padrao in (nav.pastas if nav else ()):
        caminho = _expandir(padrao, ambiente)
        if caminho and existe(caminho):
            return bonito, caminho
    return None
