import sys

import pytest

from vard import janelas


def test_escolher_por_trecho_sem_acento_e_caixa():
    lista = [
        janelas.Janela(1, "Projeto — Visual Studio Code", "Code.exe"),
        janelas.Janela(2, "YouTube - Google Chrome", "chrome.exe"),
    ]
    assert janelas.escolher(lista, "visual studio").hwnd == 1
    assert janelas.escolher(lista, "YOUTUBE").hwnd == 2
    assert janelas.escolher(lista, "nada disso") is None


def test_escolher_prefere_titulo_mais_curto_quando_empata():
    lista = [
        janelas.Janela(1, "Chrome - perfil 2 - Google Chrome", "chrome.exe"),
        janelas.Janela(2, "Google Chrome", "chrome.exe"),
    ]
    assert janelas.escolher(lista, "chrome").hwnd == 2


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
def test_listar_devolve_janelas_visiveis_com_titulo():
    lista = janelas.listar()
    assert lista, "o PC deve ter pelo menos uma janela aberta durante o teste"
    assert all(j.titulo for j in lista)


def test_escolher_trecho_vazio_devolve_none():
    lista = [janelas.Janela(1, "Google Chrome", "chrome.exe")]
    assert janelas.escolher(lista, "") is None
    assert janelas.escolher(lista, "   ") is None


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
def test_fechar_hwnd_inexistente_devolve_false():
    assert janelas.fechar(janelas.Janela(0x7FFFFFFF, "fantasma", "x")) is False
