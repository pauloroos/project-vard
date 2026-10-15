"""Testes da T2 — estado do assistente de primeiro uso retomável.

Cobre: config vazia abre assistente; reinício retoma etapa; voltar não apaga escolha;
pular preserva pendência; concluir não reabre sozinho; reabrir funciona; JSON inválido
não sobrescreve; nome vazio/só espaços é recusado; instalação preexistente pula assistente.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vard.primeiro_uso import estado


@pytest.fixture(autouse=True)
def _isolar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dados = tmp_path / "dados"
    cfg = tmp_path / "config"
    dados.mkdir()
    cfg.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    yield


def test_config_vazia_abre_assistente():
    s = estado.ler()
    assert s["concluido"] is False
    assert s["etapa"] == "importar"


def test_reinicio_retoma_etapa():
    estado.atualizar({"etapa": "nome"})
    s = estado.ler()
    assert s["etapa"] == "nome"
    assert s["concluido"] is False


def test_voltar_nao_apaga_escolha():
    estado.atualizar({"etapa": "cerebro", "cerebro_id": "local"})
    estado.atualizar({"etapa": "nome"})
    s = estado.ler()
    assert s["etapa"] == "nome"
    assert s.get("cerebro_id") == "local"


def test_pular_preserva_pendencia():
    estado.atualizar({"etapa": "voz", "pendencias": ["microfone_nao_testado"]})
    s = estado.ler()
    assert "microfone_nao_testado" in s["pendencias"]


def test_concluir_nao_reabre_sozinho():
    estado.atualizar({"concluido": True})
    s = estado.ler()
    assert s["concluido"] is True
    # Nova leitura continua concluída
    s2 = estado.ler()
    assert s2["concluido"] is True


def test_reabrir_funciona():
    estado.atualizar({"concluido": True, "nome_chamada": "Aurora"})
    s = estado.reabrir()
    assert s["concluido"] is False
    assert s.get("nome_chamada") == "Aurora"


def test_json_invalido_nao_sobrescreve():
    arq = estado._caminho()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("{invalido", encoding="utf-8")
    s = estado.ler()
    assert s["etapa"] == "importar"
    assert s["concluido"] is False


def test_nome_vazio_eh_recusado():
    with pytest.raises(ValueError, match="nome_vazio"):
        estado.validar_nome("")
    with pytest.raises(ValueError, match="nome_vazio"):
        estado.validar_nome("   ")


def test_nome_valido_retorna_limpo():
    assert estado.validar_nome("  Aurora  ") == "Aurora"


def test_instalacao_preexistente_pula_assistente():
    """Config.toml com nome não vazio marca concluido=True automaticamente.
    A fixture autouse _isolar já prepara VARD_CONFIG; escrevemos config.toml lá."""
    from vard import config as modulo_config
    cfg_arq = modulo_config.arquivo_config("config.toml")
    cfg_arq.parent.mkdir(parents=True, exist_ok=True)
    cfg_arq.write_text('nome = "Aurora"\n', encoding="utf-8")
    s = estado.ler()
    assert s["concluido"] is True


def test_atualizar_ignora_campos_desconhecidos():
    estado.atualizar({"etapa": "nome", "campo_inventado": "x"})
    s = estado.ler()
    assert "campo_inventado" not in s
    assert s["etapa"] == "nome"


def test_gravacao_atomica(tmp_path: Path):
    estado.atualizar({"etapa": "detectar"})
    arq = estado._caminho()
    assert arq.exists()
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert dados["etapa"] == "detectar"
    # Arquivo temporário não deve existir após gravação
    tmp = arq.with_suffix(".tmp")
    assert not tmp.exists()