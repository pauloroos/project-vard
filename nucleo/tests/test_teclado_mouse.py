"""Montagem dos eventos de teclado/mouse. O SendInput é sempre um dublê: nada chega ao PC."""
import pytest

from vard import teclado_mouse as tm


@pytest.fixture
def enviados(monkeypatch):
    lote = {"eventos": [], "cursor": []}

    def enviar(ev):
        lote["eventos"].extend(ev)
        return len(ev)

    monkeypatch.setattr(tm, "_enviar", enviar)
    monkeypatch.setattr(tm, "_posicionar_cursor", lambda x, y: lote["cursor"].append((x, y)) or True)
    return lote


def test_guarda_bloqueia_envio_real():
    from guarda_pc import AcessoAoPcReal

    with pytest.raises(AcessoAoPcReal):
        tm._enviar([("tecla", 0x0D, False, False)])
    with pytest.raises(AcessoAoPcReal):
        tm._posicionar_cursor(1, 1)


def test_interpretar_combinacoes():
    c = tm.interpretar("ctrl+l")
    assert c.modificadores == (tm.VK_CONTROL,) and c.vk == ord("L")
    c = tm.interpretar("Ctrl + Shift + T")
    assert c.modificadores == (tm.VK_CONTROL, tm.VK_SHIFT) and c.vk == ord("T")
    assert tm.interpretar("enter").vk == tm.VK_RETURN
    assert tm.interpretar("alt+f4").vk == 0x73
    assert tm.interpretar("seta para baixo").vk == 0x28
    assert tm.interpretar("win").vk == tm.VK_LWIN and tm.interpretar("win").modificadores == ()
    assert tm.interpretar("ctrl+1").vk == ord("1")


def test_interpretar_recusa():
    with pytest.raises(ValueError, match="Diga qual tecla"):
        tm.interpretar("  ")
    with pytest.raises(ValueError, match="Ctrl\\+Alt\\+Del"):
        tm.interpretar("ctrl+alt+del")
    with pytest.raises(ValueError, match="não é ctrl"):
        tm.interpretar("hiper+a")
    with pytest.raises(ValueError, match="Não conheço a tecla"):
        tm.interpretar("ctrl+tecla mágica")


def test_caractere_de_pontuacao_usa_layout(monkeypatch):
    monkeypatch.setattr(tm, "_vk_do_caractere", lambda ch: (0xC1, True) if ch == "?" else None)
    c = tm.interpretar("ctrl+?")
    ev = tm.eventos_combinacao(c)
    assert ev[0] == ("tecla", tm.VK_CONTROL, False, False)
    assert ev[1] == ("tecla", tm.VK_SHIFT, False, False)
    assert ev[2:4] == [("tecla", 0xC1, False, False), ("tecla", 0xC1, True, False)]
    assert ev[-1] == ("tecla", tm.VK_CONTROL, True, False)


def test_eventos_combinacao_solta_na_ordem_inversa_e_marca_estendidas():
    ev = tm.eventos_combinacao(tm.interpretar("ctrl+shift+end"))
    assert [e[1] for e in ev] == [tm.VK_CONTROL, tm.VK_SHIFT, 0x23, 0x23, tm.VK_SHIFT, tm.VK_CONTROL]
    assert [e[2] for e in ev] == [False, False, False, True, True, True]
    assert ev[2][3] is True  # End é tecla estendida


def test_eventos_texto_unicode_acentos_emoji_e_enter():
    ev = tm.eventos_texto("é\n🔍")
    assert ev[0] == ("unicode", ord("é"), False) and ev[1] == ("unicode", ord("é"), True)
    assert ev[2] == ("tecla", tm.VK_RETURN, False, False) and ev[3] == ("tecla", tm.VK_RETURN, True, False)
    # Emoji fora do BMP vai como par substituto UTF-16 (duas descidas, duas subidas).
    assert [e[1] for e in ev[4:]] == [0xD83D, 0xDD0D, 0xD83D, 0xDD0D]


def test_clique_e_rolagem():
    assert tm.eventos_clique() == [("mouse", 0x0002), ("mouse", 0x0004)]
    assert len(tm.eventos_clique("direito", duplo=True)) == 4
    with pytest.raises(ValueError, match="Botão 'lateral'"):
        tm.eventos_clique("lateral")
    assert tm.eventos_rolagem(3) == [("roda", -120)] * 3
    assert tm.eventos_rolagem(-2) == [("roda", 120)] * 2
    with pytest.raises(ValueError):
        tm.eventos_rolagem(0)
    with pytest.raises(ValueError, match="no máximo"):
        tm.eventos_rolagem(51)


def test_clicar_move_o_cursor_e_envia(enviados):
    tm.clicar(-100, 200, "esquerdo", duplo=True)
    assert enviados["cursor"] == [(-100, 200)]
    assert len(enviados["eventos"]) == 4


def test_digitar_limite_e_contagem(enviados):
    assert tm.digitar("olá") == 3
    with pytest.raises(ValueError, match="longo demais"):
        tm.digitar("x" * (tm.LIMITE_TEXTO + 1))


def test_teclar_repete_e_valida(enviados):
    tm.teclar("tab", vezes=3)
    assert len(enviados["eventos"]) == 6
    with pytest.raises(ValueError, match="Repita de 1"):
        tm.teclar("tab", vezes=0)


def test_rolar_em_ponto(enviados):
    tm.rolar(2, 10, 20)
    assert enviados["cursor"] == [(10, 20)] and len(enviados["eventos"]) == 2


def test_windows_bloqueou_entrada(monkeypatch):
    monkeypatch.setattr(tm, "_enviar", lambda ev: 0)
    with pytest.raises(RuntimeError, match="bloqueou a entrada"):
        tm.teclar("enter")
