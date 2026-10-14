from vard import bandeja


def test_cor_por_modo():
    assert bandeja.cor_do_modo("ligado") == (242, 177, 52)
    assert bandeja.cor_do_modo("jogo") == (90, 90, 90)
    assert bandeja.cor_do_modo("parado") == (120, 40, 40)
    assert bandeja.cor_do_modo("desconhecido") == (90, 90, 90)


def test_icone_e_imagem_quadrada():
    im = bandeja.desenhar_icone("ligado", 64)
    assert im.size == (64, 64) and im.mode == "RGBA"
    assert im.getpixel((32, 32))[:3] == (242, 177, 52)


def test_menu_por_modo():
    ligado = dict(i for i in bandeja.itens_menu("ligado") if i[1])
    assert "Modo jogo" in ligado and "Voltar" not in ligado and "Abrir aba" in ligado
    jogo = dict(i for i in bandeja.itens_menu("jogo") if i[1])
    assert "Voltar" in jogo and "Modo jogo" not in jogo
    assert ("Sair da bandeja", "sair") in bandeja.itens_menu("parado")


def test_erro_vermelho_com_tentar_de_novo_e_log():
    assert bandeja.cor_do_modo("erro") == (200, 40, 40)
    erro = dict(i for i in bandeja.itens_menu("erro") if i[1])
    assert erro.get("Tentar de novo") == "voltar" and erro.get("Abrir log") == "log"
    assert "Modo jogo" not in erro and "Recarregar OpenJarvis" not in erro


def test_ligando_mostra_voltar_e_nao_modo_jogo():
    ligando = dict(i for i in bandeja.itens_menu("ligando") if i[1])
    assert ligando.get("Voltar") == "voltar"
    assert "Modo jogo" not in ligando and "Recarregar OpenJarvis" not in ligando


def test_titulo_mostra_detalhe_do_erro_e_corta():
    assert bandeja.titulo({"modo": "ligado", "detalhe": "x"}) == "Vard: ligado"
    t = bandeja.titulo({"modo": "erro", "detalhe": "LM Studio não respondeu"})
    assert t == "Vard: erro: LM Studio não respondeu"
    assert len(bandeja.titulo({"modo": "erro", "detalhe": "x" * 500})) <= 128


def test_aviso_so_ao_entrar_em_erro_ou_mudar_detalhe():
    erro = {"modo": "erro", "detalhe": "a"}
    assert bandeja.deve_avisar(None, erro)
    assert bandeja.deve_avisar({"modo": "ligando", "detalhe": ""}, erro)
    assert not bandeja.deve_avisar(erro, dict(erro))
    assert bandeja.deve_avisar(erro, {"modo": "erro", "detalhe": "b"})
    assert not bandeja.deve_avisar(erro, {"modo": "ligado", "detalhe": ""})


def test_titulo_mostra_voz():
    from vard import bandeja
    assert bandeja.titulo({"modo": "ligado"}, "ligado").endswith("voz: ligado")
    assert "voz" not in bandeja.titulo({"modo": "ligado"})
    assert "voz" not in bandeja.titulo({"modo": "erro", "detalhe": "x"}, "ligado")
