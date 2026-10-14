from pathlib import Path

import pytest

from vard import config


def test_padrao_fica_na_pasta_do_usuario(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("VARD_CONFIG", raising=False)
    monkeypatch.delenv("VARD_DADOS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.pasta_config() == tmp_path / "rdl-vard" / "config"
    assert config.pasta_dados() == tmp_path / "rdl-vard"
    assert config.arquivo_segredos() == tmp_path / "rdl-vard" / "segredos.toml"


def test_ambiente_sobrescreve_e_aceita_espacos(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "minha config"
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "meus dados"))
    assert config.pasta_config() == cfg
    assert config.pasta_dados() == tmp_path / "meus dados"
    assert config.arquivo_config("oficina.toml") == cfg / "oficina.toml"
    assert config.arquivo_segredos() == tmp_path / "segredos.toml"


def test_arquivo_ausente_nao_e_criado_nem_procurado_no_checkout(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "vazia"))
    assert not config.arquivo_config("repos.toml").exists()
    assert not (tmp_path / "vazia").exists()


@pytest.mark.parametrize("nome", ["", "..", "../x.toml", "a/b.toml", "a\\b.toml"])
def test_nome_invalido_recusado(nome):
    with pytest.raises(ValueError):
        config.arquivo_config(nome)


def test_exemplos_nao_viram_config_ativa(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path))
    exemplo = Path(__file__).resolve().parents[2] / "config" / "examples"
    assert config.pasta_config() != exemplo
