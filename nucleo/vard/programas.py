"""Abrir URLs e programas no Windows: só a lógica de decidir o quê. Quem abre é a mesa."""
from __future__ import annotations

import os
import shutil
import tomllib
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus

SITES = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
}


def _simples(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def normalizar_url(texto: str, sites: dict[str, str] | None = None) -> str:
    t = texto.strip()
    chave = _simples(t)
    if sites and chave in sites:
        return sites[chave]
    if chave in SITES:
        return SITES[chave]
    if t.startswith(("http://", "https://")):
        return t
    if " " not in t and "." in t:
        return f"https://{t}"
    return "https://www.google.com/search?q=" + quote_plus(t)


def _secao(caminho: Path, secao: str) -> dict[str, str]:
    """Lê uma seção de programas.toml com chaves normalizadas; sem o arquivo, dict vazio."""
    arquivo = Path(caminho)
    if not arquivo.exists():
        return {}
    with arquivo.open("rb") as f:
        dados = tomllib.load(f)
    return {_simples(str(k)): str(v) for k, v in dados.get(secao, {}).items()}


def carregar_apelidos(caminho: Path) -> dict[str, str]:
    """Apelidos de programas ([apelidos]); sem o arquivo, dict vazio."""
    return _secao(caminho, "apelidos")


def carregar_sites(caminho: Path) -> dict[str, str]:
    """Sites do usuário ([sites]): sobrescrevem e estendem os embutidos. Sem o arquivo, dict vazio."""
    return _secao(caminho, "sites")


def _atalho_menu_iniciar(nome: str) -> str | None:
    """Procura <nome>.lnk nos menus Iniciar do usuário e do sistema."""
    raizes = [
        Path(os.environ[var]) / "Microsoft/Windows/Start Menu/Programs"
        for var in ("APPDATA", "PROGRAMDATA")
        if os.environ.get(var)
    ]
    alvo = _simples(nome)
    try:
        for raiz in raizes:
            if not raiz.exists():
                continue
            for lnk in raiz.rglob("*.lnk"):
                if _simples(lnk.stem) == alvo:
                    return str(lnk)
    except OSError:
        return None
    return None


def resolver_programa(nome: str, apelidos: dict[str, str]) -> str | None:
    chave = _simples(nome)
    if chave in apelidos:
        return apelidos[chave]
    achado = shutil.which(chave) or shutil.which(nome)
    if achado:
        return achado
    return _atalho_menu_iniciar(nome)
