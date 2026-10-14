from vard.seguro import Frase, seguro


@seguro("abrir a tarefa")
def _funcao(modo):
    if modo == "frase":
        raise Frase("Não conheço esse projeto.")
    if modo == "erro":
        raise KeyError("x" * 1000)
    return "tudo certo"


def test_retorno_normal_passa():
    assert _funcao("ok") == "tudo certo"


def test_frase_vira_a_propria_frase():
    assert _funcao("frase") == "Não conheço esse projeto."


def test_outra_excecao_vira_frase_com_a_acao_e_cabe_em_400():
    r = _funcao("erro")
    assert r.startswith("Não consegui abrir a tarefa: KeyError") and len(r) <= 400


def test_mantem_nome_da_funcao():
    assert _funcao.__name__ == "_funcao"


def test_erro_mcp_vira_frase_curta_em_portugues():
    from vard.mcp_http import ErroMCP

    @seguro("anotar")
    def cai():
        raise ErroMCP("token recusado (401)")

    r = cai()
    assert r.startswith("Não consegui anotar: o serviço de memória") and "401" in r and "ErroMCP" not in r
