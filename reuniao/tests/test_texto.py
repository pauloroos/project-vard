import pytest

from vard_reuniao.armazenamento import Fala
from vard_reuniao import texto


@pytest.mark.parametrize("frase", [
    "Vard, encerra a reunião", "vard encerra a reuniao.", "Vard, para a reunião", "Vard, termina essa reunião",
    "ok pessoal... Vard, encerre a reunião, obrigado",
    "Aurora, encerra a reunião.", "aurora termina a reunião", "Bard, encerra a reunião.", "Vard. Encerra a reunião", "Vardi, terminou a reunião", "Ward, acabou a reunião",
    "Varde, pare a reunião", "Vard, encerrar a reunião", "vard acaba aqui a reunião", "Vard! Termina reunião",
])
def test_encerramento_reconhece(frase):
    assert texto.e_encerramento(frase)


@pytest.mark.parametrize("frase", [
    "a gente encerra a reunião às cinco", "quando é a reunião, Vard?", "Vard, marca a reunião", "encerra a reunião",
    "Vard, a reunião encerrou cedo", "Bard, a reunião terminou cedo", "o vard acha que a gente encerra a reunião",
    "Vardão, encerra a reunião", "Vard, quando acaba a reunião?",
])
def test_encerramento_exige_vard_e_verbo(frase):
    assert not texto.e_encerramento(frase)


def test_similaridade_ignora_acento_e_pontuacao():
    assert texto.similaridade("Então, vamos decidir o prazo!", "entao vamos decidir o prazo") == 1.0
    assert texto.similaridade("bom dia", "o orçamento do projeto") < 0.5


def test_eco_so_com_sobreposicao():
    eu = Fala(t0=10.0, t1=13.0, trilha="eu", texto="vamos decidir o prazo da entrega")
    igual_sobreposta = Fala(t0=9.9, t1=12.9, trilha="outros", texto="Vamos decidir o prazo da entrega.")
    igual_longe = Fala(t0=40.0, t1=43.0, trilha="outros", texto="Vamos decidir o prazo da entrega.")
    assert texto.eco(eu, [igual_sobreposta]) is True
    assert texto.eco(eu, [igual_longe]) is False
    assert texto.eco(eu, []) is False


def test_eco_respeita_limiar():
    eu = Fala(t0=10.0, t1=13.0, trilha="eu", texto="vamos decidir o prazo da entrega")
    parecida = Fala(t0=10.0, t1=13.0, trilha="outros", texto="vamos decidir o preço da venda hoje")
    assert texto.eco(eu, [parecida], limiar=0.8) is False
    assert texto.eco(eu, [parecida], limiar=0.5) is True


def test_mmss():
    assert texto.mmss(0) == "00:00" and texto.mmss(72.4) == "01:12" and texto.mmss(3725) == "62:05"
