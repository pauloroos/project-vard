"""Testes da integração da seleção de modelo (T9) no despacho de tarefas (T10).

Valida resolver_modelo_agente e despachar_tarefa conforme spec D6:
pedido > padrão > sugestão > erro. Nada aqui imprime segredos.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from vard import config as _config
from vard.delegada import resolver_modelo_agente, despachar_tarefa, ErroDelegada


@pytest.fixture
def paineis_tmp(tmp_path, monkeypatch):
    """Configura VARD_CONFIG/VARD_DADOS temporários e escreve paineis.json."""
    cfg_dir = tmp_path / "config"
    dados_dir = tmp_path / "dados"
    cfg_dir.mkdir()
    dados_dir.mkdir()
    monkeypatch.setenv("VARD_CONFIG", str(cfg_dir))
    monkeypatch.setenv("VARD_DADOS", str(dados_dir))
    return cfg_dir, dados_dir


def _escrever_paineis(cfg_dir: Path, agentes: dict) -> None:
    cfg = {
        "versao": 1,
        "provedores": [],
        "ativo": None,
        "reserva": None,
        "agentes": agentes,
        "mcps": [],
    }
    (cfg_dir / "paineis.json").write_text(json.dumps(cfg), encoding="utf-8")


class TestResolverModeloAgente:
    def test_resolver_com_pedido_valido_retorna_modelo(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "sonnet", "modelos": ["sonnet", "opus"]},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        modelo, aviso = resolver_modelo_agente("claude", "opus")
        assert modelo == "opus"
        assert aviso is None

    def test_resolver_com_pedido_invalido_levanta_erro(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "sonnet", "modelos": ["sonnet", "opus"]},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        with pytest.raises(ValueError, match="não está na lista"):
            resolver_modelo_agente("claude", "haiku")

    def test_resolver_sem_pedido_usa_padrao(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "sonnet", "modelos": ["sonnet", "opus"]},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        modelo, aviso = resolver_modelo_agente("claude")
        assert modelo == "sonnet"
        assert aviso is None

    def test_resolver_sem_padrao_lista_vazia_levanta_erro(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "", "modelos": []},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        with pytest.raises(ValueError, match="nenhum modelo configurado"):
            resolver_modelo_agente("claude")

    def test_resolver_sem_padrao_lista_varios_sugere_primeiro(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "", "modelos": ["sonnet", "opus", "haiku"]},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        modelo, aviso = resolver_modelo_agente("claude")
        assert modelo == "sonnet"
        assert aviso is not None
        assert "sugestão" in aviso


class TestDespacharTarefa:
    def test_despachar_falha_se_modelo_indisponivel(self, paineis_tmp):
        cfg_dir, _ = paineis_tmp
        _escrever_paineis(cfg_dir, {
            "claude": {"padrao": "sonnet", "modelos": ["sonnet"]},
            "codex": {"padrao": "", "modelos": []},
            "opencode": {"padrao": "", "modelos": []},
            "agy": {"padrao": "", "modelos": []},
        })
        with pytest.raises(ValueError, match="não está na lista"):
            despachar_tarefa("claude", "tarefa teste", modelo_pedido="opus")