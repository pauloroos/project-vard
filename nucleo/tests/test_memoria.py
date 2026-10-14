import datetime as dt
import json

import pytest

import memoria_mcp
from vard import memoria, segredos
from vard.seguro import Frase

pytestmark = pytest.mark.usefixtures("config_usuario")   # memoria.toml fictício (projeto demo) em todo teste


class FakeCliente:
    def __init__(self, resposta: str = "{}"):
        self.resposta = resposta
        self.chamadas: list[tuple] = []

    def chamar(self, nome, argumentos):
        self.chamadas.append((nome, argumentos))
        return self.resposta


def test_consulta_fts_tira_palavras_vazias_e_pontuacao():
    assert memoria.consulta_fts("O que decidimos sobre os combos do OmniRouter?") == "decidimos OR combos OR OmniRouter"


def test_buscar_e_global_e_le_global_hits():
    resposta = json.dumps({"hits": [], "global_hits": [{
        "project_name": "projeto-exemplo", "path": "notas/2026-09-22-2.md", "title": "combos",
        "snippet": "<mark>OmniRouter</mark> combos table"}]})
    c = FakeCliente(resposta)
    r = memoria.buscar(c, "combos do OmniRouter")
    assert c.chamadas[0] == ("memory_query", {"query": "combos OR OmniRouter", "global": True, "limit": 5})
    assert "OmniRouter combos table" in r and "<mark>" not in r and "projeto-exemplo" in r


def test_buscar_sem_nada():
    assert memoria.buscar(FakeCliente('{"hits": [], "global_hits": []}'), "x y z") == "Não achei nada na memória sobre isso."


def test_configurar_ler_workspace_e_projeto():
    assert memoria.configurar() == ("default", "demo")


def test_config_sem_arquivo_ou_sem_projeto_vira_frase(tmp_path, monkeypatch):
    pasta = tmp_path / "sem proj"
    pasta.mkdir()
    (pasta / "memoria.toml").write_text('[memoria]\nworkspace = "default"\n', encoding="utf-8")
    monkeypatch.setenv("VARD_CONFIG", str(pasta))
    with pytest.raises(Frase, match="falta o projeto em memoria.toml"):
        memoria.configurar()
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "nem existe"))
    with pytest.raises(Frase, match="A memória não está configurada"):
        memoria.configurar()


def test_sem_config_devolve_a_frase_e_nao_chama_rede(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "nem existe"))
    monkeypatch.setattr(segredos, "ai_memory", lambda *a, **k: pytest.fail("não deveria ler os segredos"))
    assert memoria_mcp.memoria_buscar("x") == memoria.SEM_CONFIG
    assert memoria_mcp.memoria_ler("notes/x.md") == memoria.SEM_CONFIG
    assert memoria_mcp.memoria_gravar("Modo jogo", "deve descarregar o modelo") == memoria.SEM_CONFIG


def test_gravar_usa_o_projeto_da_configuracao():
    c = FakeCliente()
    assert memoria.gravar(c, "Modo jogo", "deve descarregar o Gemma", hoje=dt.date(2026, 10, 13)) == \
        "Anotei na memória: Modo jogo."
    nome, args = c.chamadas[-1]
    assert nome == "memory_write_page"
    assert (args["workspace"], args["project"]) == ("default", "demo")
    assert args["path"] == "notes/2026-10-13-modo-jogo.md" and args["body"].startswith("# Modo jogo\n")
    assert "scope" not in args


def test_gravar_vazio_recusa():
    with pytest.raises(Frase):
        memoria.gravar(FakeCliente(), "  ", "x")


def test_ler_usa_o_projeto_da_configuracao_quando_nao_vem_projeto():
    c = FakeCliente(json.dumps({"title": "Nota", "body": "texto"}))
    assert memoria.ler(c, "notes/x.md") == "Nota\ntexto"
    assert c.chamadas[0][1] == {"workspace": "default", "project": "demo", "path": "notes/x.md"}


def test_sem_token_vira_frase_no_mcp(monkeypatch):
    monkeypatch.setattr(segredos, "ai_memory", lambda segredos=None: ("http://h/mcp", ""))
    assert memoria_mcp.memoria_buscar("x").startswith("A memória ainda não está ligada")
    assert memoria_mcp.memoria_gravar("a", "b").startswith("A memória ainda não está ligada")


def test_gravar_limita_titulo_e_texto():
    with pytest.raises(Frase, match="título"):
        memoria.gravar(FakeCliente(), "t" * 121, "x")
    with pytest.raises(Frase, match="texto"):
        memoria.gravar(FakeCliente(), "t", "x" * 4001)
    memoria.gravar(FakeCliente(), "t" * 120, "x" * 4000)


def test_gravar_nao_sobrescreve_o_mesmo_titulo_no_dia():
    class Existentes(FakeCliente):
        def chamar(self, nome, argumentos):
            self.chamadas.append((nome, argumentos))
            if nome == "memory_read_page" and argumentos["path"].endswith(("-modo.md", "-modo-2.md")):
                return json.dumps({"title": "Modo", "body": "antigo"})
            return "{}"

    c = Existentes()
    memoria.gravar(c, "Modo", "novo", hoje=dt.date(2026, 10, 13))
    assert c.chamadas[-1][1]["path"] == "notes/2026-10-13-modo-3.md"


def test_gravar_pagina_inexistente_vira_ErroMCP_e_grava_no_caminho_base():
    from vard.mcp_http import ErroMCP

    class Novo(FakeCliente):
        def chamar(self, nome, argumentos):
            self.chamadas.append((nome, argumentos))
            if nome == "memory_read_page":
                raise ErroMCP("page not found")
            return "{}"

    c = Novo()
    memoria.gravar(c, "Modo", "novo", hoje=dt.date(2026, 10, 13))
    assert c.chamadas[-1][1]["path"] == "notes/2026-10-13-modo.md"

def test_gravar_com_tags_e_padrao_vard():
    hoje = dt.date(2026, 10, 13)
    assert memoria.argumentos_gravacao("T", "x", hoje)["tags"] == ["vard"]
    assert memoria.argumentos_gravacao("T", "x", hoje, tags=["vard", "reuniao"])["tags"] == ["vard", "reuniao"]
    c = FakeCliente()
    memoria.gravar(c, "Reunião", "texto", hoje=hoje, tags=["vard", "reuniao"])
    assert c.chamadas[-1][1]["tags"] == ["vard", "reuniao"]
