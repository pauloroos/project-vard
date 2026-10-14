import pytest

import oficina_mcp
from tests.fakes import FakeOrca
from vard import tarefas


@pytest.fixture(autouse=True)
def _config_oficina(config_usuario):
    pass


@pytest.fixture
def lancados(monkeypatch):
    lista = []
    monkeypatch.setattr(oficina_mcp.trabalhador, "lancar", lambda n: lista.append(n) or 99)
    return lista


def test_disparar_lanca_o_trabalhador(loja, lancados):
    r = oficina_mcp.disparar_tarefa("codex", "demo", "paginar clientes")
    assert r == "Disparei a tarefa 1 no Codex (demo); aviso quando terminar."
    assert lancados == [1] and tarefas.obter(1).estado == "preparando"


def test_disparar_repo_desconhecido_pergunta_sem_lancar(loja, lancados):
    assert oficina_mcp.disparar_tarefa("codex", "xpto", "x").startswith("Não conheço o projeto 'xpto'")
    assert lancados == [] and tarefas.listar() == []


def test_pesquisa(loja, lancados):
    assert oficina_mcp.disparar_tarefa("pesquisa", "", "preço do gás") == "Abri a pesquisa 1; aviso quando terminar."


def test_listar_e_status_vazios(loja):
    assert oficina_mcp.listar_tarefas() == "Nenhuma tarefa ainda."
    assert oficina_mcp.status_tarefa(9) == "Não existe tarefa 9."


def test_status_de_codigo_observa_o_orca_e_marca_avisado(loja, monkeypatch):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando", terminal="term_1", iniciada_em="2026-01-01T00:00:00-04:00")
    monkeypatch.setattr(oficina_mcp, "_orca", lambda t=None: FakeOrca(idle=True, tela="RESUMO: pronto"))
    r = oficina_mcp.status_tarefa(t.n)
    assert "terminou" in r and "pronto" in r
    assert tarefas.obter(t.n).avisado == "terminou"     # o usuário já ouviu: a vigia não repete


def test_ferramenta_nunca_levanta(loja, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(oficina_mcp.oficina, "registrar", explode)
    r = oficina_mcp.disparar_tarefa("codex", "demo", "x")
    assert r.startswith("Não consegui disparar a tarefa") and "boom" in r


def test_pedido_identico_em_60s_nao_duplica(loja, lancados):
    a = oficina_mcp.disparar_tarefa("codex", "demo", "paginar clientes")
    b = oficina_mcp.disparar_tarefa("Codex", "Demo", " paginar clientes ")
    assert a.startswith("Disparei a tarefa 1") and b.startswith("Já disparei a tarefa 1")
    assert lancados == [1] and len(tarefas.listar()) == 1
    assert oficina_mcp.disparar_tarefa("codex", "demo", "outra coisa").startswith("Disparei a tarefa 2")


def test_pedido_identico_antigo_ou_fechado_dispara_de_novo(loja, lancados):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="descartada")
    assert oficina_mcp.disparar_tarefa("codex", "demo", "x").startswith("Disparei a tarefa 2")


def test_config_trocada_apos_importacao(loja, lancados, tmp_path, monkeypatch):
    outra = tmp_path / "outra-config"
    outra.mkdir()
    (outra / "repos.toml").write_text('[repos.novo]\ncaminho="X:/dev/novo"\n', encoding="utf-8")
    monkeypatch.setenv("VARD_CONFIG", str(outra))
    assert oficina_mcp.disparar_tarefa("codex", "novo", "x").startswith("Disparei a tarefa 1")
    assert tarefas.obter(1).repo == "novo" and lancados == [1]


def test_oficina_sem_config_nao_lanca(loja, lancados, tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "ausente"))
    assert "não está configurada" in oficina_mcp.disparar_tarefa("codex", "demo", "x")
    assert tarefas.listar() == [] and lancados == []
