import pytest

import consulta_mcp
from vard import config, consulta, tarefas
from vard.consulta import ErroConsulta


@pytest.fixture(autouse=True)
def _config_consulta(config_usuario):
    (config_usuario / "remoto.toml").write_text(
        '[remoto]\ndestino="agente@exemplo.com"\ncomando="assistente"\n', encoding="utf-8")


def test_agente_remoto_registra_e_lanca(loja, monkeypatch):
    lancados = []
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: lancados.append(n))
    assert consulta_mcp.agente_remoto("como está a tarefa 42?") == "Perguntei para o agente remoto (pedido 1); aviso quando responder."
    assert tarefas.obter(1).ferramenta == "agente_remoto" and lancados == [1]
    assert consulta_mcp.agente_remoto("   ") == "Diga o que perguntar para o agente remoto."


@pytest.mark.parametrize("tipo", ["agente_remoto", "liv"])  # Adaptador legado, somente leitura.
def test_relatorio_do_agente_remoto(loja, monkeypatch, tipo):
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: None)
    arq = config.arquivo_config("relatorios.toml")
    texto = f'[uso-ia]\ntipo="{tipo}"\napelidos=["uso de ia"]\npedido="Gere o relatorio-uso-ia"\n'
    arq.write_text(texto, encoding="utf-8")
    assert consulta_mcp.relatorio("uso de IA") == "Pedi para o agente remoto o relatório uso-ia (pedido 1); aviso quando chegar."
    assert "relatorio-uso-ia" in tarefas.obter(1).pedido
    assert tarefas.obter(1).ferramenta == "agente_remoto" and arq.read_text(encoding="utf-8") == texto


def test_relatorio_desconhecido_lista_os_nomes(monkeypatch):
    config.arquivo_config("relatorios.toml").write_text('[resumo]\ntipo="agente_remoto"\n', encoding="utf-8")
    assert "Conheço: resumo" in consulta_mcp.relatorio("vendas")


def test_erro_do_gh_vira_frase(monkeypatch):
    def falha(args, timeout=30):
        raise ErroConsulta("O gh falhou: autenticação expirada")

    monkeypatch.setattr(consulta, "rodar", falha)
    assert consulta_mcp.github_prs() == "O gh falhou: autenticação expirada"


def test_rotina_manha_marca_o_dia_e_lanca(loja, monkeypatch, tmp_path):
    from vard import manha
    monkeypatch.setattr(manha, "ULTIMA", tmp_path / "manha-ultima.txt")
    lancados = []
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: lancados.append(n))
    assert consulta_mcp.rotina_manha() == "Montando o resumo do dia; leio assim que ficar pronto."
    assert lancados == [1] and tarefas.obter(1).ferramenta == "manha" and (tmp_path / "manha-ultima.txt").exists()


def test_delegar_registra_e_lanca(loja, monkeypatch, tmp_path):
    from vard import delegada
    monkeypatch.setattr(delegada, "PASTA_NEUTRA", tmp_path)
    lancados = []
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: lancados.append(n))
    assert consulta_mcp.delegar("Claude", "veja as issues do Linear") == \
        "Perguntei ao Claude (consulta 1); aviso quando ele responder."
    t = tarefas.obter(1)
    assert (t.ferramenta, t.agente, t.pedido) == ("delegada", "claude", "veja as issues do Linear") and lancados == [1]
    assert consulta_mcp.delegar("claude", "veja as issues do Linear").startswith("Já perguntei ao Claude (consulta 1)")
    assert lancados == [1]
    assert consulta_mcp.delegar("Copilot", "x").startswith("Não conheço o agente 'Copilot'")
    assert consulta_mcp.delegar("", "") == "Diga o que perguntar."


def test_delegar_com_modelo(loja, monkeypatch):
    lancados = []
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: lancados.append(n))
    assert consulta_mcp.delegar("Claude", "veja as issues do Linear", "Opus") == \
        "Perguntei ao Claude com Opus (consulta 1); aviso quando ele responder."
    assert tarefas.obter(1).modelo == "opus"
    consulta_mcp.delegar("", "com Fable veja as issues do Linear de novo")
    t = tarefas.obter(2)
    assert (t.agente, t.modelo, t.pedido) == ("claude", "fable", "veja as issues do Linear de novo")
    assert consulta_mcp.delegar("codex", "quais e-mails chegaram?", "opus") == "E-mail está desligado por enquanto."
    assert tarefas.obter(3) is None and lancados == [1, 2]


def test_delegar_com_config_invalida_devolve_frase_e_nao_cria_tarefa(loja, monkeypatch):
    from vard import delegada

    def ruim(*a, **k):
        raise ValueError("toml quebrado")
    monkeypatch.setattr(delegada, "carregar", ruim)
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: pytest.fail("não deveria lançar"))
    assert consulta_mcp.delegar("claude", "veja o Linear") ==         "A configuração da consulta delegada está com erro; veja config/delegada.toml."
    assert tarefas.listar() == []


def test_nome_remoto_lido_por_chamada(loja, monkeypatch):
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: None)
    arq = config.arquivo_config("remoto.toml")
    for nome in ("Aurora", "Estrela"):
        arq.write_text(f'[remoto]\nnome="{nome}"\ndestino="agente@exemplo.com"\ncomando="assistente"\n', encoding="utf-8")
        assert f"para {nome}" in consulta_mcp.agente_remoto("oi")


def test_consulta_sem_config_nao_lanca(loja, tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "ausente"))
    monkeypatch.setattr(consulta_mcp.trabalhador, "lancar", lambda n: pytest.fail("não deveria lançar"))
    assert consulta_mcp.agente_remoto("oi") == "O agente remoto não está configurado."
    assert "não está configurada" in consulta_mcp.relatorio("vendas")
    assert "não está configurada" in consulta_mcp.github_prs()
    assert "não está configurada" in consulta_mcp.github_issues()
    assert "[coolify]" in consulta_mcp.deploys()
    assert tarefas.listar() == []


def test_github_le_repos_e_dono_apos_importacao(tmp_path, monkeypatch):
    outra = tmp_path / "outra-config"
    outra.mkdir()
    (outra / "repos.toml").write_text(
        '[github]\ndono="outro-usuario"\n[repos.novo]\ncaminho="X:/dev/novo"\ngithub="outro-usuario/novo"\n', encoding="utf-8")
    monkeypatch.setenv("VARD_CONFIG", str(outra))
    vistos = []
    def rodar(args, timeout=30):
        vistos.append(args)
        return '[{"number": 7, "title": "Correção"}]'
    monkeypatch.setattr(consulta, "rodar", rodar)
    assert "#7 Correção" in consulta_mcp.github_prs("novo")
    assert "#7 Correção" in consulta_mcp.github_issues("novo")
    assert [args[4] for args in vistos] == ["outro-usuario/novo"] * 2


def test_resposta_remota_chega_ao_resultado_e_evento(loja, monkeypatch, tmp_path):
    import oficina_mcp
    from vard import avisos, central, remoto, trabalhador
    lancados = []
    monkeypatch.setattr(trabalhador, "lancar", lambda n: lancados.append(n))
    monkeypatch.setattr(remoto, "perguntar_com_trava", lambda pedido: "A tarefa está pronta.")
    monkeypatch.setattr(avisos, "resumo_curto", lambda texto: texto)
    assert "aviso quando responder" in consulta_mcp.agente_remoto("  consulte   a tarefa ")
    assert tarefas.obter(1).estado == "preparando" and lancados == [1]
    assert tarefas.obter(1).pedido == "consulte a tarefa"
    trabalhador.executar(1)
    t = tarefas.obter(1)
    assert t.estado == "terminou" and oficina_mcp.resultado_tarefa(1) == "A tarefa está pronta."
    arquivo = tmp_path / "avisos.jsonl"
    monkeypatch.setattr(avisos, "publicar", lambda ev: central.registrar(ev, arquivo) is not None)
    assert avisos.avisar(t)
    assert central.listar(arquivo)[0]["resumo"] == "O agente remoto respondeu: A tarefa está pronta."
