import json
from pathlib import Path

import httpx
import pytest

from vard import consulta, oficina
from vard.consulta import ErroConsulta

RAIZ = Path(__file__).resolve().parent.parent
REPOS = oficina.carregar_repos(RAIZ / "tests" / "fixtures" / "config" / "repos.toml")
RELATORIOS = {"uso-ia": {"tipo": "agente_remoto", "apelidos": ["uso de ia", "cotas"], "pedido": "x"}}


def test_comando_gh_com_e_sem_repo():
    assert consulta.comando_gh("pr", REPOS["demo"]) == [
        "gh", "pr", "list", "-R", "seu-usuario/demo-app", "--state", "open", "--limit", "10",
        "--json", consulta.CAMPOS_PR]
    assert "search" not in consulta.comando_gh("issue", REPOS["demo"])


def test_github_sem_repo_consulta_so_os_repos_do_repos_toml():
    chamadas = []

    def fake(args, timeout=30):
        chamadas.append(args)
        return json.dumps([{"number": 12, "title": "Paginação", "isDraft": True}]) if "seu-usuario/demo-app" in args else "[]"

    r = consulta.github("pr", "", repos=REPOS, dono="seu-usuario", rodar_fn=fake)
    assert r.startswith("1 PR(s) aberto(s) nos projetos da oficina:")
    assert "- demo #12 Paginação (rascunho)" in r
    assert all(c[:3] == ["gh", "pr", "list"] and "search" not in c for c in chamadas)
    assert {c[c.index("-R") + 1] for c in chamadas} == {r.github for r in REPOS.values() if r.github}


def test_github_sem_nada_e_repos_ruins():
    vazio = lambda args, timeout=30: "[]"  # noqa: E731
    assert consulta.github("issue", "demo", repos=REPOS, dono="p", rodar_fn=vazio) == "Nenhuma issue aberta no demo."
    with pytest.raises(ErroConsulta, match="não está no GitHub"):
        consulta.github("pr", "demo-team", repos=REPOS, dono="p", rodar_fn=vazio)
    with pytest.raises(ErroConsulta, match="Não conheço o projeto"):
        consulta.github("pr", "xpto", repos=REPOS, dono="p", rodar_fn=vazio)


def test_saida_do_gh_que_nao_e_json_vira_frase():
    with pytest.raises(ErroConsulta, match="resposta estranha"):
        consulta.github("pr", "demo", repos=REPOS, dono="p", rodar_fn=lambda a, timeout=30: "<html>")


def test_erro_do_gh_vira_frase_curta(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "HTTP 401: Bad credentials (https://api.github.com/graphql)"

    monkeypatch.setattr(consulta.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(ErroConsulta, match="não está logado"):
        consulta.rodar(["gh", "pr", "list"])


def test_saudavel_e_resumo_do_coolify():
    assert consulta.saudavel("running:healthy") and not consulta.saudavel("running:unhealthy")
    assert not consulta.saudavel("exited:unhealthy")
    itens = [{"name": "agente", "status": "running:healthy"}, {"name": "portal", "status": "exited:unhealthy"}]
    r = consulta.resumir_coolify("exemplo", itens, [{"application_name": "site"}])
    assert r == "Coolify exemplo: 2 apps e serviços; 1 fora do normal: portal (exited:unhealthy); 1 deploy(s) em andamento: site."


def test_deploys_sem_painel_e_sem_vercel():
    r = consulta.deploys({}, vercel="")
    assert "sem a seção [coolify]" in r and "Vercel: a CLI não está instalada" in r


def test_deploys_painel_sem_token():
    r = consulta.deploys({"exemplo": {"url": "https://p", "token": ""}}, vercel="")
    assert "Coolify exemplo: falta token" in r


def test_deploys_com_painel_que_cai_nao_vaza_token():
    def get(url, token, rota):
        raise httpx.ConnectError(f"falhou com {token}")

    r = consulta.deploys({"exemplo": {"url": "https://p", "token": "SEGREDO"}}, vercel="", get=get)
    assert "Coolify exemplo: não respondeu (ConnectError)" in r and "SEGREDO" not in r


def test_deploys_com_painel_ok():
    dados = {"applications": [{"name": "a", "status": "running:healthy"}], "services": [], "deployments": []}
    r = consulta.deploys({"exemplo": {"url": "https://p", "token": "t"}}, vercel="", get=lambda u, t, rota: dados[rota])
    assert "Coolify exemplo: 1 apps e serviços; todos no ar." in r


def test_relatorio_por_apelido_e_desconhecido():
    nome, rel = consulta.achar_relatorio("Uso de IA", RELATORIOS)
    assert nome == "uso-ia" and rel["tipo"] == "agente_remoto"
    with pytest.raises(ErroConsulta, match="Conheço: uso-ia"):
        consulta.achar_relatorio("vendas", RELATORIOS)


def test_relatorio_sem_nenhum_cadastrado():
    with pytest.raises(ErroConsulta, match="não conheço esse relatório"):
        consulta.achar_relatorio("vendas", {})


def test_relatorios_toml_real_carrega_vazio():
    assert consulta.carregar_relatorios() == {}


def test_gerar_local_abre_o_pdf(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    abertos = []
    r = consulta.gerar_local("x", {"comando": ["gerar"], "pdf": str(pdf)}, rodar_fn=lambda a, timeout=30: "",
                             abrir=abertos.append)
    assert r == "Abri o relatório x." and abertos == [str(pdf)]


def test_coolify_get_ignora_proxy_do_ambiente(monkeypatch):
    visto = {}

    class FakeClient:
        def __init__(self, **kw):
            visto.update(kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            import httpx
            return httpx.Response(200, json=[{"name": "x"}], request=httpx.Request("GET", url))

    monkeypatch.setattr(consulta.httpx, "Client", FakeClient)
    assert consulta.coolify_get("http://h", "t", "applications") == [{"name": "x"}]
    assert visto["trust_env"] is False


def test_deploys_diz_exatamente_o_que_falta():
    r = consulta.deploys({"exemplo": {"token": "t"}, "outro": {"url": "https://h"}, "x": {}}, vercel="")
    assert "Coolify exemplo: falta url" in r and "Coolify outro: falta token" in r
    assert "Coolify x: falta url e token" in r
    assert "falta url e token" not in r.split("Coolify x")[0]
    assert "sem a seção [coolify]" in consulta.deploys({}, vercel="")



def test_relatorio_sem_config_responde_sem_erro():
    assert consulta.relatorio("vendas") == "A consulta de relatórios não está configurada."


def test_relatorio_remoto_usa_pedido_configurado(monkeypatch):
    pedidos = []
    monkeypatch.setattr("vard.remoto.perguntar_com_trava", lambda pedido: pedidos.append(pedido) or "Resumo remoto.")
    assert consulta.relatorio("cotas", relatorios=RELATORIOS) == "Resumo remoto."
    assert pedidos == ["x"]


def test_carregar_relatorios_respeita_vard_config(config_usuario):
    (config_usuario / "relatorios.toml").write_text('[demo]\ntipo="agente_remoto"\npedido="Resumo."\n', encoding="utf-8")
    assert consulta.carregar_relatorios() == {"demo": {"tipo": "agente_remoto", "pedido": "Resumo."}}
