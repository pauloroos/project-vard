"""T7 (0.9): importar instalação anterior sem alterar a origem.

Origem sintética em pasta temporária (config/*.toml, perfil.json/persona.md,
instalacao.json, hud.config.json e segredos.toml); destino isolado por
VARD_CONFIG/VARD_DADOS do conftest. Nenhum segredo real: valores fictícios
sem prefixo sensível, sem e-mail, sem IP e sem letra de unidade.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import tomli_w
from fastapi.testclient import TestClient

import server
from vard import config as modulo_config
from vard import segredos as modulo_segredos
from vard.primeiro_uso import importacao

SEGREDO_ORIGEM = "ficticio-origem-001"
SEGREDO_DESTINO = "ficticio-destino-002"
TOKEN_ORIGEM = "ficticio-token-origem-003"


def _sha(pasta: Path) -> dict[str, str]:
    """SHA-256 de todos os arquivos da origem (prova de que ela ficou intacta)."""
    mapa = {}
    for arq in sorted(pasta.rglob("*")):
        if arq.is_file():
            mapa[str(arq.relative_to(pasta))] = hashlib.sha256(arq.read_bytes()).hexdigest()
    return mapa


def _origem_legada(raiz: Path, *, com_perfil_json: bool = True) -> Path:
    """Monta uma origem sintética completa no estilo da fusão (0.5)."""
    origem = raiz / "origem-antiga"
    (origem / "config").mkdir(parents=True)
    hud = {
        "nome": "Coruja", "variantes": ["coruja", "curuja"], "usuario": "Visitante",
        "voz": "pm_sara", "velocidade": 1.1, "idioma": "pt",
        "voz_provedor": "propria", "voz_propria": "",
        "elevenlabs_chave": "ficticio-hud-antiga-004",
    }
    (origem / "hud.config.json").write_text(json.dumps(hud), encoding="utf-8")
    segredos = {
        "lmstudio": {"chave": SEGREDO_ORIGEM},
        "telegram": {"token": TOKEN_ORIGEM, "chat_id": "ficticio-chat-005"},
        "omniroute": {"url": "", "chave": ""},
    }
    (origem / "segredos.toml").write_text(tomli_w.dumps(segredos), encoding="utf-8")
    instalacao = {
        "raiz_codigo": "X:/ANTIGA/repo", "openjarvis_src": "X:/ANTIGA/oj",
        "openjarvis_home": "X:/ANTIGA/oj-home", "modelo": "modelo-antigo",
        "contexto": 8000, "servicos": {},
    }
    (origem / "instalacao.json").write_text(json.dumps(instalacao), encoding="utf-8")
    (origem / "config" / "delegada.toml").write_text("[geral]\nlimite = 3\n", encoding="utf-8")
    (origem / "config" / "memoria.toml").write_text("[geral]\nretencao_dias = 30\n", encoding="utf-8")
    if com_perfil_json:
        perfil = {"tom": "direto", "personalidade": "objetiva",
                  "instrucoes": "Fale pouco.", "sobre_usuario": "Gosta de aves.", "versao": 1}
        (origem / "config" / "perfil.json").write_text(json.dumps(perfil), encoding="utf-8")
    else:
        (origem / "config" / "persona.md").write_text("Persona legada da Coruja.", encoding="utf-8")
    return origem


def _hud_atual() -> dict:
    return {"nome": "vard", "variantes": ["vard"], "usuario": "",
            "voz": "pm_alex", "velocidade": 1.05, "idioma": "pt",
            "voz_provedor": "propria", "voz_propria": ""}


def test_previa_lista_as_seis_categorias_sem_chaves(tmp_path: Path):
    origem = _origem_legada(tmp_path)
    antes = _sha(origem)
    pv = importacao.previa(origem, _hud_atual())
    assert pv["schema"] == 1 and pv["previa_id"]
    ids = [c["id"] for c in pv["categorias"]]
    assert ids == ["chamada", "voz", "cerebro", "persona", "config_toml", "segredos"]
    assert all(c["estado"] == "pronta" for c in pv["categorias"])
    texto = json.dumps(pv)
    assert SEGREDO_ORIGEM not in texto and TOKEN_ORIGEM not in texto
    assert _sha(origem) == antes  # a prévia não toca na origem


def test_previa_mostra_nome_e_conflito(tmp_path: Path):
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    chamada = next(c for c in pv["categorias"] if c["id"] == "chamada")
    nome = next(i for i in chamada["itens"] if i["campo"] == "nome")
    assert nome["origem"] == "Coruja" and nome["destino"] == "vard" and nome["conflito"] is True


def test_origem_igual_ao_destino_e_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "dados").mkdir(parents=True)
    pv = importacao.previa(tmp_path / "dados", _hud_atual())
    assert pv["ja_ativo"] is True and pv["categorias"] == []
    resultado = importacao.aplicar(pv["previa_id"], {})
    assert resultado["ok"] is True and resultado["aplicadas"] == []
    assert list((tmp_path / "dados").iterdir()) == []


def test_origem_inexistente_recusa():
    with pytest.raises(importacao.OrigemInvalida):
        importacao.previa(Path("X:/origem-que-nao-existe-xyz"))


def test_aplicar_tudo_preserva_nome_voz_provedor_e_caminhos(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    antes = _sha(origem)
    pv = importacao.previa(origem, _hud_atual())
    escolhas = {c["id"]: "importar" for c in pv["categorias"]}
    resultado = importacao.aplicar(pv["previa_id"], escolhas)
    assert resultado["ok"] is True and sorted(resultado["aplicadas"]) == sorted(escolhas)
    assert resultado["hud"]["nome"] == "Coruja"
    assert resultado["hud"]["variantes"] == ["coruja", "curuja"]
    assert resultado["hud"]["voz"] == "pm_sara"
    perfil = json.loads((tmp_path / "config" / "perfil.json").read_text(encoding="utf-8"))
    assert perfil["tom"] == "direto" and perfil["sobre_usuario"] == "Gosta de aves."
    assert (tmp_path / "config" / "delegada.toml").exists()
    destino_inst = json.loads((tmp_path / "dados" / "instalacao.json").read_text(encoding="utf-8"))
    assert destino_inst["modelo"] == "modelo-antigo" and destino_inst["contexto"] == 8000
    assert "ANTIGA" not in json.dumps(destino_inst)  # a raiz ativa nunca vem do repo antigo
    assert _sha(origem) == antes  # origem byte a byte intacta


def test_repetir_importacao_e_idempotente(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    escolhas = {c["id"]: "importar" for c in pv["categorias"]}
    primeira = importacao.aplicar(pv["previa_id"], escolhas)
    assert primeira["ok"] is True
    segunda = importacao.aplicar(pv["previa_id"], escolhas)
    assert segunda["ok"] is True and segunda["aplicadas"] == [] and segunda["operacao_id"] is None


def test_conflito_manter_preserva_destino(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "delegada.toml").write_text("[geral]\nlimite = 9\n", encoding="utf-8")
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    toml = next(c for c in pv["categorias"] if c["id"] == "config_toml")
    item = next(i for i in toml["itens"] if i["campo"] == "delegada.toml")
    assert item["conflito"] is True
    resultado = importacao.aplicar(pv["previa_id"], {"config_toml": "manter"})
    assert resultado["ok"] is True and "config_toml" not in resultado["aplicadas"]
    assert (tmp_path / "config" / "delegada.toml").read_text(encoding="utf-8") == "[geral]\nlimite = 9\n"


def test_conflito_importar_faz_backup_e_retorno(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "delegada.toml").write_text("[geral]\nlimite = 9\n", encoding="utf-8")
    origem = _origem_legada(tmp_path)
    antes = _sha(origem)
    pv = importacao.previa(origem, _hud_atual())
    resultado = importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})
    assert (tmp_path / "config" / "delegada.toml").read_text(encoding="utf-8") == "[geral]\nlimite = 3\n"
    volta = importacao.reverter(resultado["operacao_id"])
    assert volta["ok"] is True
    assert (tmp_path / "config" / "delegada.toml").read_text(encoding="utf-8") == "[geral]\nlimite = 9\n"
    assert _sha(origem) == antes


def test_credencial_presente_no_destino_nunca_sai(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    (tmp_path / "config").mkdir(parents=True)
    destino_seg = {"lmstudio": {"chave": SEGREDO_DESTINO}, "telegram": {"token": "", "chat_id": ""}}
    (tmp_path / "segredos.toml").write_text(tomli_w.dumps(destino_seg), encoding="utf-8")
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    seg = next(c for c in pv["categorias"] if c["id"] == "segredos")
    lm = next(i for i in seg["itens"] if i["campo"] == "lmstudio")
    assert lm["conflito"] is True and "chave" not in json.dumps(seg)
    resultado = importacao.aplicar(pv["previa_id"], {"segredos": "importar"})
    assert resultado["ok"] is True
    import tomllib
    gravados = tomllib.loads((tmp_path / "segredos.toml").read_text(encoding="utf-8"))
    assert gravados["lmstudio"]["chave"] == SEGREDO_DESTINO  # a do destino fica
    assert gravados["telegram"]["token"] == TOKEN_ORIGEM  # vazio no destino preenche


def test_chave_na_hud_antiga_vira_aviso_e_nao_importa(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    assert any("cofre" in a.lower() or "painel" in a.lower() for a in pv["avisos"])
    resultado = importacao.aplicar(pv["previa_id"], {"chamada": "importar", "voz": "importar"})
    assert "elevenlabs_chave" not in json.dumps(resultado["hud"])
    assert "ficticio-hud-antiga-004" not in json.dumps(resultado)


def test_toml_invalido_nao_trava_o_resto(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    (origem / "config" / "memoria.toml").write_text("[geral\nquebrado = ", encoding="utf-8")
    pv = importacao.previa(origem, _hud_atual())
    toml = next(c for c in pv["categorias"] if c["id"] == "config_toml")
    item = next(i for i in toml["itens"] if i["campo"] == "memoria.toml")
    assert item["estado"] == "erro"
    resultado = importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})
    assert resultado["ok"] is True
    assert (tmp_path / "config" / "delegada.toml").exists()
    assert not (tmp_path / "config" / "memoria.toml").exists()


def test_persona_md_legada_vira_perfil(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path, com_perfil_json=False)
    pv = importacao.previa(origem, _hud_atual())
    persona = next(c for c in pv["categorias"] if c["id"] == "persona")
    assert persona["estado"] == "pronta"
    resultado = importacao.aplicar(pv["previa_id"], {"persona": "importar"})
    assert resultado["ok"] is True
    perfil = json.loads((tmp_path / "config" / "perfil.json").read_text(encoding="utf-8"))
    assert perfil["instrucoes"] == "Persona legada da Coruja."


def test_previa_obsoleta_rejeita_origem_alterada(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    (origem / "config" / "delegada.toml").write_text("[geral]\nlimite = 42\n", encoding="utf-8")
    with pytest.raises(importacao.PreviaObsoleta):
        importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})


def test_falha_de_gravacao_retorna_ao_destino(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "delegada.toml").write_text("[geral]\nlimite = 9\n", encoding="utf-8")
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    real_replace = os.replace

    def quebrar(src, dst, *args, **kwargs):
        if str(dst).endswith("delegada.toml"):
            raise OSError("disco fictício cheio")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", quebrar)
    with pytest.raises(importacao.FalhaAplicacao):
        importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})
    assert (tmp_path / "config" / "delegada.toml").read_text(encoding="utf-8") == "[geral]\nlimite = 9\n"
    assert list((tmp_path / "config").glob("*.tmp")) == []


def test_reverter_preserva_dado_novo_de_uso(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    resultado = importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})
    assert resultado["ok"] is True
    (tmp_path / "config" / "delegada.toml").write_text("[geral]\nlimite = 77\n", encoding="utf-8")
    (tmp_path / "dados" / "tarefas.json").write_text("[]", encoding="utf-8")
    volta = importacao.reverter(resultado["operacao_id"])
    assert volta["ok"] is True
    assert (tmp_path / "config" / "delegada.toml").read_text(encoding="utf-8") == "[geral]\nlimite = 77\n"
    assert (tmp_path / "dados" / "tarefas.json").read_text(encoding="utf-8") == "[]"
    assert any("77" in a or "alterado" in a.lower() or "mantido" in a.lower() for a in volta["avisos"])


def test_reverter_remove_arquivo_criado_pela_importacao(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    resultado = importacao.aplicar(pv["previa_id"], {"cerebro": "importar", "config_toml": "importar"})
    assert (tmp_path / "dados" / "instalacao.json").exists()
    assert (tmp_path / "config" / "delegada.toml").exists()
    volta = importacao.reverter(resultado["operacao_id"])
    assert volta["ok"] is True
    assert not (tmp_path / "dados" / "instalacao.json").exists()
    assert not (tmp_path / "config" / "delegada.toml").exists()
    assert volta["avisos"] == []


def test_reverter_operacao_desconhecida_recusa():
    with pytest.raises(importacao.OperacaoDesconhecida):
        importacao.reverter("operacao-que-nao-existe")


def test_oauth_da_origem_e_ignorado_com_aviso(tmp_path: Path):
    origem = _origem_legada(tmp_path)
    segredos = (origem / "segredos.toml").read_text(encoding="utf-8")
    segredos += '\n[conta_externa]\ntoken = "ficticio-oauth-006"\n'
    (origem / "segredos.toml").write_text(segredos, encoding="utf-8")
    pv = importacao.previa(origem, _hud_atual())
    assert any("OAuth" in a or "oauth" in a.lower() for a in pv["avisos"])
    assert "ficticio-oauth-006" not in json.dumps(pv)


def test_comando_antigo_em_toml_vira_aviso(tmp_path: Path):
    origem = _origem_legada(tmp_path)
    (origem / "config" / "delegada.toml").write_text(
        '[geral]\nlimite = 3\n[mcp_antigo]\ncommand = "X:/ANTIGA/legado.exe"\n', encoding="utf-8")
    pv = importacao.previa(origem, _hud_atual())
    toml = next(c for c in pv["categorias"] if c["id"] == "config_toml")
    assert any("revis" in a.lower() or "painel" in a.lower() for a in toml["avisos"])


def test_mesclar_segredos_novos_so_preenche_vazio():
    destino = {"a": {"x": "fica", "y": ""}, "b": {"z": "fica"}}
    origem = {"a": {"x": "sai", "y": "entra", "w": "entra"}, "c": {"k": "entra"}}
    mesclado, preenchidos = modulo_segredos.mesclar_novos(destino, origem, ("a", "c"))
    assert mesclado["a"] == {"x": "fica", "y": "entra", "w": "entra"}
    assert mesclado["b"] == {"z": "fica"} and mesclado["c"] == {"k": "entra"}
    assert preenchidos == {"a": ["w", "y"], "c": ["k"]}
    assert "sai" not in json.dumps(mesclado)


@pytest.fixture
def cliente_http(monkeypatch, tmp_path):
    server.HISTORICO.clear()
    monkeypatch.setattr(server, "_reuniao_ativa", lambda: False)
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    return TestClient(server.app, base_url="http://127.0.0.1:4700")


def test_http_previa_aplicar_reverter(cliente_http, tmp_path: Path):
    origem = _origem_legada(tmp_path)
    antes = _sha(origem)
    r = cliente_http.post("/primeiro-uso/importacao/previa",
                          json={"origem": str(origem), "hud_atual": _hud_atual()})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["schema"] == 1 and len(corpo["categorias"]) == 6
    assert SEGREDO_ORIGEM not in r.text and TOKEN_ORIGEM not in r.text
    escolhas = {c["id"]: "importar" for c in corpo["categorias"]}
    r = cliente_http.post("/primeiro-uso/importacao/aplicar",
                          json={"previa_id": corpo["previa_id"], "escolhas": escolhas})
    assert r.status_code == 200, r.text
    aplicado = r.json()
    assert aplicado["ok"] is True and aplicado["hud"]["nome"] == "Coruja"
    assert SEGREDO_ORIGEM not in r.text and TOKEN_ORIGEM not in r.text
    r = cliente_http.post("/primeiro-uso/importacao/reverter",
                          json={"operacao_id": aplicado["operacao_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert _sha(origem) == antes


def test_http_erros_tem_codigo_curto(cliente_http):
    r = cliente_http.post("/primeiro-uso/importacao/previa", json={"origem": "X:/nao-existe-xyz"})
    assert r.status_code == 422 and r.json()["erro"] == "origem_invalida"
    r = cliente_http.post("/primeiro-uso/importacao/aplicar",
                          json={"previa_id": "previa-que-nao-existe", "escolhas": {}})
    assert r.status_code == 404 and r.json()["erro"] == "previa_desconhecida"
    r = cliente_http.post("/primeiro-uso/importacao/reverter", json={"operacao_id": "nada-aqui"})
    assert r.status_code == 404 and r.json()["erro"] == "operacao_desconhecida"


def test_destino_usa_vard_config_e_dados(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    assert modulo_config.pasta_config() == tmp_path / "config"
    assert modulo_config.pasta_dados() == tmp_path / "dados"
    origem = _origem_legada(tmp_path)
    pv = importacao.previa(origem, _hud_atual())
    resultado = importacao.aplicar(pv["previa_id"], {"config_toml": "importar"})
    assert resultado["ok"] is True
    assert (tmp_path / "config" / "delegada.toml").exists()
