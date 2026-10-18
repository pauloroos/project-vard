import asyncio
import importlib
from pathlib import Path

import pytest

import mesa_mcp
from vard import janelas, uia
from vard.monitores import Monitor, Retangulo


def test_abrir_url_normaliza_e_chama_startfile(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    r = mesa_mcp.abrir_url("youtube")
    assert abertos == ["https://youtube.com"]
    assert "youtube.com" in r


def test_abrir_url_vazia_pede_o_site(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    assert mesa_mcp.abrir_url("   ") == "Diga qual site abrir."
    assert abertos == []


def test_abrir_programa_vazio_pede_o_programa(monkeypatch):
    abertos = []
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
    assert mesa_mcp.abrir_programa("") == "Diga qual programa abrir."
    assert abertos == []


def test_abrir_programa_desconhecido_explica(monkeypatch):
    monkeypatch.setattr(mesa_mcp.programas, "resolver_programa", lambda n, a: None)
    r = mesa_mcp.abrir_programa("xyz")
    assert "não encontrei" in r.lower()


def test_abrir_programa_conhecido(monkeypatch):
    chamados = []
    monkeypatch.setattr(mesa_mcp.programas, "resolver_programa", lambda n, a: "code")
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: chamados.append(alvo))
    r = mesa_mcp.abrir_programa("vscode")
    assert chamados == ["code"] and "vscode" in r


def test_focar_janela_inexistente(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "nenhuma janela" in mesa_mcp.focar_janela("qualquer").lower()


def test_focar_janela_existente(monkeypatch):
    j = janelas.Janela(7, "YouTube - Google Chrome", "chrome.exe")
    focadas = []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda x: focadas.append(x) or True)
    assert "YouTube" in mesa_mcp.focar_janela("youtube") and focadas == [j]


def test_focar_janela_recusada(monkeypatch):
    j = janelas.Janela(7, "YouTube - Google Chrome", "chrome.exe")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda x: False)
    assert "recusou" in mesa_mcp.focar_janela("youtube")


ESQ = Monitor(1, "A", Retangulo(-400, 0, 400, 200), Retangulo(-400, 0, 400, 180), False, 100, 1)
PRI = Monitor(2, "B", Retangulo(0, 0, 300, 100), Retangulo(0, 0, 300, 90), True, 150, 2)


@pytest.fixture
def telas(monkeypatch):
    monkeypatch.setattr(mesa_mcp.monitores, "listar", lambda: [ESQ, PRI])
    monkeypatch.setattr(mesa_mcp.monitores, "da_janela", lambda lista, hwnd: PRI)
    return [ESQ, PRI]


class _Shot:
    def __init__(self, regiao):
        self.size = (regiao["width"], regiao["height"])
        self.bgra = bytes(regiao["width"] * regiao["height"] * 4)


class _Mss:
    regioes: list = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def grab(self, regiao):
        _Mss.regioes.append(regiao)
        return _Shot(regiao)


@pytest.fixture
def mss_falso(monkeypatch):
    _Mss.regioes = []
    monkeypatch.setattr(mesa_mcp.mss, "mss", lambda: _Mss())
    return _Mss.regioes


def test_print_da_tela_grava_png_na_pasta_de_prints(tmp_path: Path, monkeypatch, telas, mss_falso):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path / "prints")
    r = mesa_mcp.print_da_tela()
    gravados = list((tmp_path / "prints").glob("tela-*.png"))
    assert len(gravados) == 1 and str(gravados[0]) in r
    assert gravados[0].read_bytes().startswith(b"\x89PNG")
    # Padrão: o monitor principal, sem redução.
    assert mss_falso == [{"left": 0, "top": 0, "width": 300, "height": 100}]
    assert "monitor 2, imagem 300x100" in r and "x = 0 + px*1," in r


def test_print_da_tela_de_outro_monitor_devolve_origem_e_fator(tmp_path, monkeypatch, telas, mss_falso):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path)
    monkeypatch.setattr(mesa_mcp, "PRINT_LADO_MAX", 200)
    r = mesa_mcp.print_da_tela(monitor=1)
    assert mss_falso == [{"left": -400, "top": 0, "width": 400, "height": 200}]
    assert "imagem 200x100" in r and "x = -400 + px*2, y = 0 + py*2" in r
    r = mesa_mcp.print_da_tela(monitor="todos")
    assert mss_falso[-1] == {"left": -400, "top": 0, "width": 700, "height": 200}
    assert "todos os monitores" in r


def test_fator_reducao():
    assert mesa_mcp.fator_reducao(1280, 720) == 1
    assert mesa_mcp.fator_reducao(3136, 1000) == 2
    assert round(1920 * 1080 / mesa_mcp.fator_reducao(1920, 1080) ** 2) <= mesa_mcp.PRINT_PIXELS_MAX


def test_print_da_tela_monitor_inexistente(tmp_path, monkeypatch, telas, mss_falso):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path)
    assert "Não há monitor 9" in mesa_mcp.print_da_tela(monitor=9)
    assert mss_falso == []


def test_print_da_tela_ignora_pasta_e_extensao_do_caminho(tmp_path: Path, monkeypatch, telas, mss_falso):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path / "prints")
    mesa_mcp.print_da_tela("X:/qualquer/coisa.docx")
    assert (tmp_path / "prints" / "coisa.png").exists()
    assert not Path("X:/qualquer/coisa.docx").exists()


def test_print_da_tela_nao_sobrescreve(tmp_path: Path, monkeypatch, telas, mss_falso):
    monkeypatch.setattr(mesa_mcp, "PASTA_PRINTS", tmp_path)
    (tmp_path / "x.png").write_bytes(b"antigo")
    mesa_mcp.print_da_tela("x.png"); mesa_mcp.print_da_tela("x.png")
    assert (tmp_path / "x.png").read_bytes() == b"antigo"
    assert (tmp_path / "x-2.png").exists() and (tmp_path / "x-3.png").exists()


def test_fechar_janela_existente_e_inexistente(monkeypatch):
    j = janelas.Janela(7, "Bloco de notas", "notepad.exe")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [j])
    monkeypatch.setattr(mesa_mcp.janelas, "fechar", lambda x: True)
    assert "Pedi para fechar" in mesa_mcp.fechar_janela("bloco")
    monkeypatch.setattr(mesa_mcp.janelas, "fechar", lambda x: False)
    assert "já não existe" in mesa_mcp.fechar_janela("bloco")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "Nenhuma janela" in mesa_mcp.fechar_janela("bloco")


def test_listar_janelas_vazio_e_truncado(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [])
    assert "Nenhuma janela" in mesa_mcp.listar_janelas()
    muitas = [janelas.Janela(i, f"Janela {i}", "x.exe") for i in range(45)]
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: muitas)
    saida = mesa_mcp.listar_janelas()
    assert saida.count("\n- ") == 39 and "(+5 janelas não listadas)" in saida


def test_ferramenta_nunca_levanta(monkeypatch):
    def explode(): raise RuntimeError("boom")
    monkeypatch.setattr(mesa_mcp.janelas, "listar", explode)
    r = mesa_mcp.listar_janelas()
    assert r.startswith("Não consegui listar as janelas") and "boom" in r


def test_hora_atual_em_portugues():
    import datetime as dt

    r = mesa_mcp.hora_atual()
    assert "Agora são" in r
    assert any(d in r for d in mesa_mcp.DIAS)
    assert str(dt.datetime.now().year) in r


def test_apelidos_e_sites_vem_da_config_do_usuario(tmp_path: Path, monkeypatch):
    """VARD_CONFIG apontando para outra pasta muda o que a mesa resolve (caminho com espaço de propósito)."""
    pasta = tmp_path / "pasta com espaço"
    pasta.mkdir()
    (pasta / "programas.toml").write_text(
        '[apelidos]\nvscode = "code"\n\n[sites]\nmeuapp = "https://app.exemplo.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("VARD_CONFIG", str(pasta))
    abertos: list[str] = []
    try:
        importlib.reload(mesa_mcp)
        monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: abertos.append(alvo))
        r_programa = mesa_mcp.abrir_programa("vscode")
        r_site = mesa_mcp.abrir_url("meuapp")
    finally:
        # Volta para a config vazia do isolamento de testes para não contaminar os próximos.
        monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
        importlib.reload(mesa_mcp)
    assert abertos == ["code", "https://app.exemplo.com"]
    assert "vscode" in r_programa and "app.exemplo.com" in r_site


# --- Navegador pedido ---------------------------------------------------------------------------

class _Popen:
    chamados: list = []

    def __init__(self, args, **kw):
        _Popen.chamados.append((args, kw))


def test_abrir_url_no_navegador_pedido(monkeypatch):
    _Popen.chamados = []
    monkeypatch.setattr(mesa_mcp.navegadores, "resolver", lambda n: ("Brave", "X:\\Apps\\brave.exe"))
    monkeypatch.setattr(mesa_mcp.subprocess, "Popen", _Popen)
    monkeypatch.setattr(mesa_mcp.os, "startfile", lambda alvo: pytest.fail("não usa o padrão"))
    r = mesa_mcp.abrir_url("youtube", navegador="brave")
    assert r == "Abri https://youtube.com no Brave."
    args, kw = _Popen.chamados[0]
    assert args == ["X:\\Apps\\brave.exe", "https://youtube.com"]
    assert kw["stdin"] is mesa_mcp.subprocess.DEVNULL and kw["stdout"] is mesa_mcp.subprocess.DEVNULL


def test_abrir_url_navegador_ausente_lista_os_instalados(monkeypatch):
    monkeypatch.setattr(mesa_mcp.navegadores, "resolver", lambda n: None)
    monkeypatch.setattr(mesa_mcp.navegadores, "instalados", lambda: ["Google Chrome", "Microsoft Edge"])
    monkeypatch.setattr(mesa_mcp.subprocess, "Popen", lambda *a, **k: pytest.fail("não abre nada"))
    r = mesa_mcp.abrir_url("youtube", navegador="opera")
    assert "Não encontrei o navegador 'opera'" in r and "Google Chrome, Microsoft Edge" in r


def test_abrir_url_recusa_argumento_disfarcado(monkeypatch):
    monkeypatch.setattr(mesa_mcp.programas, "normalizar_url", lambda u, s: "--remote-debugging-port=9")
    monkeypatch.setattr(mesa_mcp.navegadores, "resolver", lambda n: pytest.fail("nem procura"))
    assert "inválido" in mesa_mcp.abrir_url("x", navegador="brave")


def test_abrir_url_com_navegador_real_barrado_pela_guarda(monkeypatch):
    monkeypatch.setattr(mesa_mcp.navegadores, "resolver", lambda n: ("Brave", "X:\\Apps\\brave.exe"))
    r = mesa_mcp.abrir_url("youtube", navegador="brave")
    assert r.startswith("Não consegui abrir o site: AcessoAoPcReal")


# --- Monitores e janelas ------------------------------------------------------------------------

J = janelas.Janela(7, "Bloco de notas", "notepad.exe")


def test_listar_monitores(telas):
    texto = mesa_mcp.listar_monitores()
    assert texto.splitlines()[0].startswith("1: A, 400x200 em (-400,0)")
    assert texto.splitlines()[1].endswith("principal")


def test_listar_janelas_mostra_monitor_com_mais_de_um(monkeypatch, telas):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    assert mesa_mcp.listar_janelas() == "- Bloco de notas (notepad.exe) [monitor 2]"


def test_mover_janela_para_o_outro_monitor(monkeypatch, telas):
    pedidos = []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])

    def mover(j, origem, destino, posicao, x, y, largura, altura):
        pedidos.append((j, origem.indice, destino.indice, posicao))
        return janelas.Plano("normal", Retangulo(-400, 0, 200, 180))

    monkeypatch.setattr(mesa_mcp.janelas, "mover", mover)
    r = mesa_mcp.mover_janela("bloco", monitor="outro", posicao="esquerda")
    assert pedidos == [(J, 2, 1, "esquerda")]
    assert r == "Coloquei 'Bloco de notas' no monitor 1, esquerda: 200x180 em (-400,0)."


def test_mover_janela_ativa_e_estados(monkeypatch, telas):
    monkeypatch.setattr(mesa_mcp.janelas, "ativa", lambda: J)
    monkeypatch.setattr(mesa_mcp.janelas, "mover", lambda *a: janelas.Plano("maximizar"))
    assert mesa_mcp.mover_janela(posicao="maximizar") == "Maximizei 'Bloco de notas' no monitor 2."
    monkeypatch.setattr(mesa_mcp.janelas, "mover", lambda *a: janelas.Plano("minimizar"))
    assert mesa_mcp.mover_janela("", posicao="minimizar") == "Minimizei 'Bloco de notas'."


def test_mover_janela_erros_viram_frase(monkeypatch, telas):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    assert mesa_mcp.mover_janela("bloco", monitor=5) == "Não há monitor 5; há 2 (1, 2)."
    assert "Não conheço a posição" in mesa_mcp.mover_janela("bloco", posicao="diagonal")
    assert mesa_mcp.mover_janela("planilha") == "Nenhuma janela com 'planilha' no título."
    monkeypatch.setattr(mesa_mcp.janelas, "ativa", lambda: None)
    assert "Não há janela ativa" in mesa_mcp.mover_janela()


def test_mover_janela_real_bloqueado_pela_guarda(monkeypatch, telas):
    """Sem dublê do Win32, a guarda do PC real impede mexer numa janela de verdade."""
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(janelas.monitores, "ativar_dpi", lambda: None)
    monkeypatch.setattr(janelas, "_estado", lambda h: "normal")
    monkeypatch.setattr(janelas, "_retangulos", lambda h: (Retangulo(0, 0, 100, 50), (0, 0, 0, 0)))
    r = mesa_mcp.mover_janela("bloco", posicao="esquerda")
    assert r.startswith("Não consegui mover a janela: AcessoAoPcReal")


# --- Elementos, clique e teclado ----------------------------------------------------------------

def _elemento(id_="e1", nome="Vídeo de gatos", tipo="Link"):
    return uia.Elemento(id_, nome, tipo, Retangulo(100, 200, 300, 60))


def test_elementos_da_janela(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.uia, "listar", lambda hwnd, filtro: [_elemento()])
    r = mesa_mcp.elementos_da_janela("bloco", "gatos")
    assert "- e1 Link \"Vídeo de gatos\" [100,200 300x60]" in r


def test_elementos_sem_uiautomation_explica(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])

    def sem_pacote(hwnd, filtro):
        raise ModuleNotFoundError("No module named 'uiautomation'", name="uiautomation")

    monkeypatch.setattr(mesa_mcp.uia, "listar", sem_pacote)
    assert "falta o pacote uiautomation" in mesa_mcp.elementos_da_janela("bloco")


def test_clicar_elemento_aciona_pela_uia(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.uia, "acionar", lambda hwnd, pedido: (_elemento(), 3, "acionei"))
    r = mesa_mcp.clicar_elemento("bloco", "gatos")
    assert r.startswith("Acionei link \"Vídeo de gatos\" em 'Bloco de notas'.") and "havia 3 parecidos" in r


def test_clicar_elemento_sem_padrao_clica_no_centro(monkeypatch):
    cliques, focos = [], []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda j: focos.append(j) or True)
    monkeypatch.setattr(mesa_mcp.uia, "acionar", lambda hwnd, pedido: (_elemento(), 1, ""))
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "clicar", lambda x, y, *a: cliques.append((x, y)))
    assert mesa_mcp.clicar_elemento("bloco", "e1").startswith("Cliquei link")
    assert cliques == [(250, 230)] and focos == [J]


def test_clicar_elemento_nao_achado_e_id_sem_lista(monkeypatch):
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.uia, "acionar", lambda hwnd, pedido: (None, 0, ""))
    assert "Não achei 'cachorro'" in mesa_mcp.clicar_elemento("bloco", "cachorro")
    monkeypatch.setattr(mesa_mcp.uia, "acionar", lambda hwnd, pedido: (None, -1, ""))
    assert "Liste antes com elementos_da_janela" in mesa_mcp.clicar_elemento("bloco", "e4")
    assert "Diga qual elemento" in mesa_mcp.clicar_elemento("bloco", " ")


def test_clicar_confere_o_ponto(monkeypatch, telas):
    cliques = []
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "clicar", lambda *a: cliques.append(a))
    assert mesa_mcp.clicar(-10, 50) == "Cliquei com o botão esquerdo em (-10, 50), monitor 1."
    assert mesa_mcp.clicar(10, 10, "direito", True).startswith("Dei clique duplo com o botão direito")
    fora = mesa_mcp.clicar(10, 150)
    assert "fora dos monitores" in fora and "(-400,0) a (299,199)" in fora
    assert cliques == [(-10, 50, "esquerdo", False), (10, 10, "direito", True)]


def test_clicar_sem_dubles_e_barrado_pela_guarda(telas):
    r = mesa_mcp.clicar(10, 10)
    assert r.startswith("Não consegui clicar: AcessoAoPcReal")


def test_digitar_nao_repete_o_texto(monkeypatch):
    digitados = []
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "digitar", lambda t: digitados.append(t) or len(t))
    r = mesa_mcp.digitar("senha-ficticia-123")
    assert r == "Digitei 18 caracteres." and "senha" not in r
    assert digitados == ["senha-ficticia-123"]
    assert mesa_mcp.digitar("") == "Diga o que digitar."


def test_digitar_foca_a_janela_antes_ou_desiste(monkeypatch):
    digitados = []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "digitar", lambda t: digitados.append(t) or len(t))
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda j: True)
    assert mesa_mcp.digitar("oi", janela="bloco") == "Digitei 2 caracteres em 'Bloco de notas'."
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda j: False)
    assert "nada foi digitado" in mesa_mcp.digitar("oi", janela="bloco")
    assert digitados == ["oi"]


def test_teclar_valida_antes_de_focar(monkeypatch):
    focos, teclas = [], []
    monkeypatch.setattr(mesa_mcp.janelas, "listar", lambda: [J])
    monkeypatch.setattr(mesa_mcp.janelas, "focar", lambda j: focos.append(j) or True)
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "teclar", lambda c, v: teclas.append((c, v)))
    assert "Não conheço a tecla" in mesa_mcp.teclar("ctrl+tecla mágica", janela="bloco")
    assert focos == [] and teclas == []
    assert mesa_mcp.teclar("ctrl+l", janela="bloco") == "Apertei ctrl+l em 'Bloco de notas'."
    assert mesa_mcp.teclar("tab", vezes=3) == "Apertei tab 3 vezes."
    assert teclas == [("ctrl+l", 1), ("tab", 3)]


def test_rolar(monkeypatch, telas):
    rolagens = []
    monkeypatch.setattr(mesa_mcp.teclado_mouse, "rolar", lambda q, x, y: rolagens.append((q, x, y)))
    assert mesa_mcp.rolar(3) == "Rolei 3 para baixo."
    assert mesa_mcp.rolar(-2, -10, 10) == "Rolei 2 para cima."
    assert "juntos" in mesa_mcp.rolar(1, x=5)
    assert "fora dos monitores" in mesa_mcp.rolar(1, 5000, 5)
    assert rolagens == [(3, None, None), (-2, -10, 10)]


def test_schema_explica_coordenadas_do_clique():
    ferramentas = {t.name: t for t in asyncio.run(mesa_mcp.mcp.list_tools())}
    x = ferramentas["clicar"].input_schema["properties"]["x"]["description"]
    assert "pixels físicos" in x and "origem_x + px * fator" in x
    assert "fator" in ferramentas["print_da_tela"].description
