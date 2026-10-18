"""Cálculo de posição das janelas e aplicação com Win32 simulado (nenhuma janela real se mexe)."""
import pytest

from vard import janelas
from vard.monitores import Monitor, Retangulo

ESQ = Monitor(1, "A", Retangulo(-1920, 0, 1920, 1080), Retangulo(-1920, 0, 1920, 1040), False, 100, 1)
PRI = Monitor(2, "B", Retangulo(0, 0, 2560, 1440), Retangulo(0, 0, 2560, 1400), True, 150, 2)


@pytest.mark.parametrize("falado,canonica", [
    ("Maximizar", "maximizar"), ("metade esquerda", "esquerda"), ("em cima", "cima"), ("embaixo", "baixo"),
    ("centralizar", "centro"), ("tela cheia", "tela cheia"), ("", ""), ("restaura", "restaurar"),
])
def test_normalizar_posicao(falado, canonica):
    assert janelas.normalizar_posicao(falado) == canonica


def test_posicao_desconhecida_explica():
    with pytest.raises(ValueError, match="Não conheço a posição 'diagonal'"):
        janelas.normalizar_posicao("diagonal")


def test_metades_usam_a_area_util_do_destino():
    atual = Retangulo(100, 100, 800, 600)
    assert janelas.planejar(atual, PRI, PRI, "esquerda").ret == Retangulo(0, 0, 1280, 1400)
    assert janelas.planejar(atual, PRI, PRI, "direita").ret == Retangulo(1280, 0, 1280, 1400)
    assert janelas.planejar(atual, PRI, PRI, "cima").ret == Retangulo(0, 0, 2560, 700)
    assert janelas.planejar(atual, PRI, PRI, "baixo").ret == Retangulo(0, 700, 2560, 700)
    assert janelas.planejar(atual, PRI, ESQ, "esquerda").ret == Retangulo(-1920, 0, 960, 1040)


def test_tela_cheia_cobre_o_monitor_inteiro():
    assert janelas.planejar(Retangulo(0, 0, 10, 10), PRI, ESQ, "tela cheia").ret == ESQ.tela


def test_centro_mantem_tamanho_e_cabe_na_area():
    p = janelas.planejar(Retangulo(5, 5, 800, 600), PRI, PRI, "centro")
    assert p.ret == Retangulo(880, 400, 800, 600)
    grande = janelas.planejar(Retangulo(0, 0, 5000, 3000), PRI, ESQ, "centro")
    assert grande.ret == Retangulo(-1920, 0, 1920, 1040)


def test_outro_monitor_mantem_proporcao():
    # Metade direita do principal (2560 de largura) vira metade direita do da esquerda (1920).
    atual = Retangulo(1280, 0, 1280, 1400)
    p = janelas.planejar(atual, PRI, ESQ)
    assert p.estado == "normal" and p.ret == Retangulo(-960, 0, 960, 1040)


def test_maximizar_em_outro_monitor_leva_antes_de_maximizar():
    p = janelas.planejar(Retangulo(0, 0, 1280, 700), PRI, ESQ, "maximizar")
    assert p.estado == "maximizar" and p.ret == Retangulo(-1920, 0, 960, 520)
    assert janelas.planejar(Retangulo(0, 0, 1, 1), PRI, PRI, "maximizar") == janelas.Plano("maximizar")
    assert janelas.planejar(Retangulo(0, 0, 1, 1), PRI, PRI, "minimizar") == janelas.Plano("minimizar")


def test_x_y_relativos_a_area_util_e_contidos():
    atual = Retangulo(10, 10, 800, 600)
    p = janelas.planejar(atual, PRI, ESQ, x=100, y=50, largura=1000, altura=500)
    assert p.ret == Retangulo(-1820, 50, 1000, 500)
    # Fora da área: empurra para dentro e limita o tamanho.
    p = janelas.planejar(atual, PRI, PRI, x=2400, y=1300, largura=4000)
    assert p.ret == Retangulo(0, 800, 2560, 600)
    # Só tamanho: mantém a posição.
    assert janelas.planejar(atual, PRI, PRI, largura=400).ret == Retangulo(10, 10, 400, 600)


def test_sem_destino_pede_um():
    with pytest.raises(ValueError, match="Diga para onde mover"):
        janelas.planejar(Retangulo(0, 0, 10, 10), PRI, PRI)


def test_bordas_invisiveis():
    assert janelas.com_bordas(Retangulo(0, 0, 1280, 1400), (7, 0, 7, 7)) == Retangulo(-7, 0, 1294, 1407)


class _Win32:
    def __init__(self, monkeypatch, estado="normal", visivel=Retangulo(100, 100, 800, 600), margens=(7, 0, 7, 7)):
        self.chamadas = []
        monkeypatch.setattr(janelas.monitores, "ativar_dpi", lambda: None)
        monkeypatch.setattr(janelas, "_estado", lambda h: estado)
        monkeypatch.setattr(janelas, "_mostrar", lambda h, c: self.chamadas.append(("mostrar", c)))
        monkeypatch.setattr(janelas, "_retangulos", lambda h: (visivel, margens))
        monkeypatch.setattr(janelas, "_colocar", lambda h, r: self.chamadas.append(("colocar", r)))


J = janelas.Janela(7, "Bloco de notas", "notepad.exe")


def test_mover_metade_esquerda_compensa_bordas(monkeypatch):
    w = _Win32(monkeypatch)
    plano = janelas.mover(J, PRI, PRI, "esquerda")
    assert plano.ret == Retangulo(0, 0, 1280, 1400)
    assert w.chamadas == [("colocar", Retangulo(-7, 0, 1294, 1407))]


def test_mover_maximizada_restaura_antes_e_reaplica_ao_trocar_de_monitor(monkeypatch):
    w = _Win32(monkeypatch, estado="maximizada", margens=(0, 0, 0, 0))
    plano = janelas.mover(J, PRI, ESQ, "maximizar")
    assert plano.estado == "maximizar"
    assert [c[0] for c in w.chamadas] == ["mostrar", "colocar", "colocar", "mostrar"]
    assert w.chamadas[0] == ("mostrar", "restaurar") and w.chamadas[-1] == ("mostrar", "maximizar")


def test_maximizar_e_minimizar_no_mesmo_monitor_so_mudam_o_estado(monkeypatch):
    w = _Win32(monkeypatch)
    janelas.mover(J, PRI, PRI, "maximizar")
    janelas.mover(J, PRI, ESQ, "minimizar")
    assert w.chamadas == [("mostrar", "maximizar"), ("mostrar", "minimizar")]


def test_pedido_invalido_nao_mexe_na_janela(monkeypatch):
    w = _Win32(monkeypatch, estado="maximizada")
    with pytest.raises(ValueError):
        janelas.mover(J, PRI, PRI)
    with pytest.raises(ValueError):
        janelas.mover(J, PRI, PRI, "diagonal")
    assert w.chamadas == []
