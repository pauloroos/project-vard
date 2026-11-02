"""Resolução do navegador com registro e disco simulados."""
import pytest

from vard import navegadores

APP = navegadores.APP_PATHS
SMI = navegadores.START_MENU[0]


@pytest.fixture
def registro(monkeypatch):
    valores: dict[tuple[str, str], str] = {}
    subchaves: dict[tuple[str, str], list[str]] = {}
    monkeypatch.setattr(navegadores, "_ler_valor", lambda raiz, caminho: valores.get((raiz, caminho)))
    monkeypatch.setattr(navegadores, "_subchaves", lambda raiz, caminho: subchaves.get((raiz, caminho), []))
    return valores, subchaves


@pytest.mark.parametrize("falado,chave", [
    ("Brave", "brave"), ("o navegador Brave", "brave"), ("Google Chrome", "chrome"), ("microsoft edge", "edge"),
    ("msedge.exe", "edge"), ("Mozilla Firefox", "firefox"), ("Opera GX", "opera gx"), ("no Vivaldi", "vivaldi"),
])
def test_normalizar_nome(falado, chave):
    assert navegadores.normalizar_nome(falado) == chave


def test_exe_do_comando():
    assert navegadores.exe_do_comando('"X:\\Apps\\Brave\\brave.exe" --single-argument %1') == "X:\\Apps\\Brave\\brave.exe"
    assert navegadores.exe_do_comando("X:\\Apps\\ff\\firefox.exe -osint -url %1") == "X:\\Apps\\ff\\firefox.exe"


def test_app_paths_primeiro(registro):
    valores, _ = registro
    valores[("HKLM", f"{APP}\\brave.exe")] = "X:\\Apps\\Brave\\brave.exe"
    r = navegadores.resolver("brave", ambiente={}, existe=lambda p: p == "X:\\Apps\\Brave\\brave.exe")
    assert r == ("Brave", "X:\\Apps\\Brave\\brave.exe")


def test_app_paths_com_exe_apagado_cai_no_menu_iniciar(registro):
    valores, subchaves = registro
    valores[("HKCU", f"{APP}\\chrome.exe")] = "X:\\velho\\chrome.exe"
    subchaves[("HKLM", SMI)] = ["Google Chrome"]
    valores[("HKLM", f"{SMI}\\Google Chrome\\shell\\open\\command")] = '"X:\\novo\\chrome.exe"'
    r = navegadores.resolver("chrome", ambiente={}, existe=lambda p: p == "X:\\novo\\chrome.exe")
    assert r == ("Google Chrome", "X:\\novo\\chrome.exe")


def test_opera_comum_nao_confunde_com_gx(registro):
    valores, subchaves = registro
    subchaves[("HKCU", SMI)] = ["Opera GXStable", "OperaStable"]
    valores[("HKCU", f"{SMI}\\Opera GXStable\\shell\\open\\command")] = '"X:\\gx\\launcher.exe"'
    valores[("HKCU", f"{SMI}\\OperaStable\\shell\\open\\command")] = '"X:\\opera\\launcher.exe"'
    assert navegadores.resolver("opera", ambiente={}, existe=lambda p: True)[1] == "X:\\opera\\launcher.exe"
    assert navegadores.resolver("opera gx", ambiente={}, existe=lambda p: True)[1] == "X:\\gx\\launcher.exe"


def test_pasta_padrao_sem_registro(registro):
    amb = {"LOCALAPPDATA": "X:\\Usuario\\Local", "PROGRAMFILES": "X:\\PF"}
    alvo = "X:\\Usuario\\Local\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    assert navegadores.resolver("brave", ambiente=amb, existe=lambda p: p == alvo) == ("Brave", alvo)


def test_navegador_ausente_devolve_none(registro):
    assert navegadores.resolver("firefox", ambiente={}, existe=lambda p: False) is None
    assert navegadores.resolver("", ambiente={}, existe=lambda p: True) is None


def test_navegador_desconhecido_procura_pelo_nome(registro):
    valores, _ = registro
    valores[("HKLM", f"{APP}\\librewolf.exe")] = "X:\\lw\\librewolf.exe"
    assert navegadores.resolver("LibreWolf", ambiente={}, existe=lambda p: True) == ("LibreWolf", "X:\\lw\\librewolf.exe")


def test_instalados_lista_nomes_bonitos(registro, monkeypatch):
    valores, subchaves = registro
    subchaves[("HKLM", SMI)] = ["Google Chrome", "IEXPLORE.EXE", "Microsoft Edge"]
    for sub in subchaves[("HKLM", SMI)]:
        valores[("HKLM", f"{SMI}\\{sub}\\shell\\open\\command")] = f'"X:\\{sub}\\x.exe"'
    monkeypatch.setattr(navegadores, "_existe", lambda p: True)
    assert navegadores.instalados() == ["Google Chrome", "Internet Explorer", "Microsoft Edge"]
