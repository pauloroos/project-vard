import pytest

from vard import monitores
from vard.monitores import Monitor, Retangulo


def _tres():
    # Fora de ordem de propósito: a numeração é da esquerda para a direita.
    brutos = [
        Monitor(0, "DISPLAY1", Retangulo(0, 0, 1920, 1080), Retangulo(0, 0, 1920, 1040), True, 100, 11),
        Monitor(0, "DISPLAY2", Retangulo(-2560, 0, 2560, 1440), Retangulo(-2560, 0, 2560, 1400), False, 150, 22),
        Monitor(0, "DISPLAY3", Retangulo(1920, -200, 1080, 1920), Retangulo(1920, -200, 1080, 1880), False, 100, 33),
    ]
    return monitores.numerar(brutos)


def test_numera_da_esquerda_para_a_direita():
    lista = _tres()
    assert [m.nome for m in lista] == ["DISPLAY2", "DISPLAY1", "DISPLAY3"]
    assert [m.indice for m in lista] == [1, 2, 3]


@pytest.mark.parametrize("pedido,esperado", [
    (1, "DISPLAY2"), ("2", "DISPLAY1"), ("monitor 3", "DISPLAY3"), ("segundo", "DISPLAY1"),
    ("principal", "DISPLAY1"), ("Primário", "DISPLAY1"), ("esquerda", "DISPLAY2"), ("da direita", "DISPLAY3"),
])
def test_escolher_por_pedido(pedido, esperado):
    assert monitores.escolher(_tres(), pedido).nome == esperado


def test_vazio_devolve_atual_ou_principal():
    lista = _tres()
    assert monitores.escolher(lista, None).nome == "DISPLAY1"
    assert monitores.escolher(lista, "", lista[2]).nome == "DISPLAY3"


def test_outro_avanca_em_ciclo():
    lista = _tres()
    assert monitores.escolher(lista, "outro", lista[0]).indice == 2
    assert monitores.escolher(lista, "outro", lista[2]).indice == 1
    assert monitores.escolher(lista, "anterior", lista[0]).indice == 3


def test_monitor_inexistente_explica():
    with pytest.raises(ValueError, match=r"Não há monitor 5; há 3 \(1, 2, 3\)"):
        monitores.escolher(_tres(), 5)
    with pytest.raises(ValueError, match="Não entendi o monitor"):
        monitores.escolher(_tres(), "da cozinha")
    with pytest.raises(ValueError, match="nenhum monitor"):
        monitores.escolher([], 1)


def test_ponto_e_area_virtual():
    lista = _tres()
    assert monitores.do_ponto(lista, -10, 10).nome == "DISPLAY2"
    assert monitores.do_ponto(lista, 1919, 1079).nome == "DISPLAY1"
    assert monitores.do_ponto(lista, 1920, 1079).nome == "DISPLAY3"
    assert monitores.do_ponto(lista, 0, 1500) is None
    v = monitores.area_virtual(lista)
    assert (v.x, v.y, v.direita, v.baixo) == (-2560, -200, 3000, 1720)


def test_descrever():
    texto = monitores.descrever(_tres()[1])
    assert texto.startswith("2: DISPLAY1, 1920x1080 em (0,0), escala 100%")
    assert "área útil 1920x1040" in texto and texto.endswith("principal")
