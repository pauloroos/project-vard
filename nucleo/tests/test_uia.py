"""UI Automation com árvore falsa: a busca, os filtros, os ids e o acionamento, sem tocar o Windows."""
import pytest

from vard import uia


class _Ret:
    def __init__(self, l, t, r, b):
        self.left, self.top, self.right, self.bottom = l, t, r, b


class _Padrao:
    def __init__(self, registro, nome):
        self.registro, self.nome = registro, nome

    def Invoke(self):
        self.registro.append(("Invoke", self.nome))

    def Toggle(self):
        self.registro.append(("Toggle", self.nome))


class Ctrl:
    def __init__(self, tipo, nome="", ret=(0, 0, 10, 10), fora=False, senha=False, padroes=(), filhos=()):
        self.ControlTypeName, self.Name = tipo, nome
        self.BoundingRectangle = _Ret(*ret)
        self.IsOffscreen, self.IsPassword = fora, senha
        self.padroes, self.filhos, self.irmao = padroes, list(filhos), None
        self.registro = []
        for a, b in zip(self.filhos, self.filhos[1:]):
            a.irmao = b

    def GetFirstChildControl(self):
        return self.filhos[0] if self.filhos else None

    def GetNextSiblingControl(self):
        return self.irmao

    def GetInvokePattern(self):
        return _Padrao(self.registro, self.Name) if "invoke" in self.padroes else None

    def GetSelectionItemPattern(self):
        return None

    def GetTogglePattern(self):
        return _Padrao(self.registro, self.Name) if "toggle" in self.padroes else None

    def GetExpandCollapsePattern(self):
        return None


def _arvore():
    return Ctrl("WindowControl", "Janela", filhos=[
        Ctrl("ButtonControl", "Voltar", (0, 0, 30, 30), padroes=("invoke",)),
        Ctrl("PaneControl", "conteúdo", filhos=[
            Ctrl("HyperlinkControl", "Vídeo  de  gatos", (100, 200, 400, 260), padroes=("invoke",)),
            Ctrl("HyperlinkControl", "Vídeo escondido", (0, 5000, 10, 5010), fora=True),
            Ctrl("TextControl", "só texto"),
            Ctrl("ButtonControl", "", (0, 0, 5, 5)),
            Ctrl("ButtonControl", "Zero", (5, 5, 5, 5)),
            Ctrl("EditControl", "Senha", (10, 10, 200, 30), senha=True),
            Ctrl("EditControl", "", (10, 40, 200, 60)),
            Ctrl("CheckBoxControl", "Lembrar", (10, 70, 30, 90), padroes=("toggle",)),
        ]),
    ])


def test_coletar_filtra_e_numera():
    lista = uia.coletar(_arvore())
    assert [(e.id, e.tipo, e.nome) for e in lista] == [
        ("e1", "Botão", "Voltar"), ("e2", "Link", "Vídeo de gatos"), ("e3", "Campo", "Senha"),
        ("e4", "Campo", "(campo sem nome)"), ("e5", "Caixa", "Lembrar")]
    assert lista[1].ret.x == 100 and lista[1].ret.largura == 300
    assert lista[2].senha and "(campo de senha)" in lista[2].linha()


def test_filtro_ignora_acento_e_caixa():
    assert [e.nome for e in uia.coletar(_arvore(), "VIDEO")] == ["Vídeo de gatos"]


def test_percorrer_respeita_limite_de_nos():
    assert len(list(uia._percorrer(_arvore(), limite_visitados=3))) == 2


def test_texto_da_lista_corta_quantidade_e_nome(monkeypatch):
    monkeypatch.setattr(uia, "LIMITE_ELEMENTOS", 2)
    lista = uia.coletar(_arvore())
    lista[0].nome = "x" * 200
    texto = uia.texto_da_lista("Janela", lista)
    assert texto.count("\n- ") == 2 and "(+3 não listados" in texto
    assert "x" * uia.LIMITE_NOME not in texto and "…" in texto
    assert "print_da_tela" in uia.texto_da_lista("Janela", [])
    assert "Nenhum elemento com 'zzz'" in uia.texto_da_lista("Janela", [], "zzz")


def test_escolher_por_id_nome_exato_e_trecho():
    lista = uia.coletar(_arvore())
    assert uia.escolher(lista, "E2")[0].nome == "Vídeo de gatos"
    assert uia.escolher(lista, "e99") == (None, 0)
    assert uia.escolher(lista, "voltar")[0].id == "e1"
    elemento, casados = uia.escolher(lista, "campo")
    assert elemento.id == "e4" and casados == 1
    assert uia.escolher(lista, "") == (None, 0)


@pytest.fixture
def janela_falsa(monkeypatch):
    arvore = _arvore()
    monkeypatch.setattr(uia, "_executar", lambda fn: fn())
    monkeypatch.setattr(uia, "_raiz", lambda hwnd: arvore)
    monkeypatch.setattr(uia, "_CACHE", {})
    return arvore


def test_acionar_por_id_precisa_de_lista(janela_falsa):
    assert uia.acionar(7, "e2") == (None, -1, "")
    lista = uia.listar(7, "gatos")
    assert [e.id for e in lista] == ["e1"]
    elemento, casados, como = uia.acionar(7, "e1")
    assert elemento.nome == "Vídeo de gatos" and como == "acionei"
    assert elemento.controle.registro == [("Invoke", "Vídeo  de  gatos")]


def test_acionar_por_nome_nao_troca_os_ids_da_lista(janela_falsa):
    uia.listar(7, "gatos")
    elemento, _, como = uia.acionar(7, "Lembrar")
    assert como == "alternei" and elemento.tipo == "Caixa"
    assert uia.acionar(7, "e1")[0].nome == "Vídeo de gatos"


def test_acionar_sem_padrao_pede_clique_fisico(janela_falsa):
    elemento, _, como = uia.acionar(7, "Senha")
    assert elemento.senha and como == ""


def test_janela_sumiu(monkeypatch):
    monkeypatch.setattr(uia, "_executar", lambda fn: fn())
    monkeypatch.setattr(uia, "_raiz", lambda hwnd: None)
    with pytest.raises(RuntimeError, match="não achou a janela"):
        uia.listar(7)
