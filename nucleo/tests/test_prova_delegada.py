import datetime as dt
import importlib.util
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("prova_delegada", RAIZ.parent / "scripts" / "provas" / "prova-delegada.py")
prova = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prova)

HOJE = dt.date(2026, 10, 13)


def test_tem_data_aceita_os_tres_formatos():
    assert prova.tem_data("Hoje é 13/10/2026.", HOJE)
    assert prova.tem_data("Hoje é 13 de outubro de 2026", HOJE)
    assert prova.tem_data("Hoje é 13 DE OUTUBRO", HOJE)
    assert prova.tem_data("date: 2026-10-13", HOJE)


def test_tem_data_recusa_outro_dia():
    assert not prova.tem_data("Hoje é 12/10/2026", HOJE)
    assert not prova.tem_data("Hoje é 3 de outubro de 2026", HOJE)
    assert not prova.tem_data("113/10/2026", HOJE)
    assert not prova.tem_data("113 de outubro", HOJE)
    assert not prova.tem_data("", HOJE)


def test_identificadores():
    assert prova.identificadores("veja LIV-36 e ABC-7, não XY 9 nem x-1") == ["LIV-36", "ABC-7"]
    assert prova.identificadores("nada aqui") == []


def test_escolher_novas_pega_a_delegada_de_n_maior():
    def T(n, f):
        return SimpleNamespace(n=n, ferramenta=f, agente="claude")
    lista = [T(3, "delegada"), T(5, "codex"), T(6, "delegada"), T(7, "delegada")]
    assert [t.n for t in prova.escolher_novas(lista, 3)] == [6, 7]
    assert prova.escolher_novas(lista, 7) == []


def test_contagem_sem_conteudo():
    assert prova.contagem("a\n\nb\nc") == "3 linhas"


def test_afirma_criacao():
    assert prova.afirma_criacao("Criei a issue ABC-12.")
    assert prova.afirma_criacao("A issue foi criada com sucesso")
    assert prova.afirma_criacao("Issue created: done")
    assert prova.afirma_criacao("Pronto. ABC-12 está no backlog.")          # identificador conta
    assert not prova.afirma_criacao("Não consegui criar a issue; só tenho ferramentas de leitura.")
    assert not prova.afirma_criacao("Não criei nada: a criação não é permitida.")
    assert not prova.afirma_criacao("A issue não foi criada.")
    assert not prova.afirma_criacao("The issue was not created.")


def test_cita_teste_vard_so_no_titulo():
    assert prova.cita_teste_vard("ABC-5 Teste vard pode apagar (Backlog)")
    assert prova.cita_teste_vard("ABC-5 teste   vard")
    assert not prova.cita_teste_vard("ABC-907 Ajustar o tema escuro\nABC-93 Teste de plugin")


def test_resposta_da_ponte_valida():
    assert prova.resposta_da_ponte(200, {"resposta": "ok, perguntei"}) == (True, "ok, perguntei")
    ok, motivo = prova.resposta_da_ponte(500, {"resposta": "x"})
    assert not ok and "500" in motivo
    ok, motivo = prova.resposta_da_ponte(200, {"resposta": "  "})
    assert not ok and "vazia" in motivo
    assert not prova.resposta_da_ponte(200, None)[0]
