"""A allowlist [agent] tools do OpenJarvis também filtra MCP: ferramenta fora dela some do agente."""
import asyncio
import importlib
import tomllib
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "examples" / "openjarvis.example.toml"
# MCP -> quantas ferramentas. Cada tarefa que cria ferramenta atualiza aqui.
MCPS = {"mesa": 7, "oficina": 7, "consulta": 7, "memoria": 3, "reuniao": 6}


def _allowlist() -> set[str]:
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return {n.strip() for n in cfg["agent"]["tools"].split(",")}


def _ferramentas(nome: str) -> list:
    return asyncio.run(importlib.import_module(f"{nome}_mcp").mcp.list_tools())


@pytest.mark.parametrize("nome,qtd", MCPS.items())
def test_toda_ferramenta_do_mcp_esta_na_allowlist(nome, qtd):
    nomes = {t.name for t in _ferramentas(nome)}
    assert len(nomes) == qtd
    assert nomes <= _allowlist(), f"faltam na allowlist: {nomes - _allowlist()}"


def test_nomes_unicos_entre_os_mcps():
    todos = [t.name for nome in MCPS for t in _ferramentas(nome)]
    assert len(todos) == len(set(todos))


@pytest.mark.parametrize("nome", MCPS)
def test_descricoes_curtas(nome):
    # O Gemma roda com 16k de contexto e cada descrição entra em todo prompt.
    longas = [t.name for t in _ferramentas(nome) if len(t.description or "") > 140]
    assert not longas, f"descrição longa demais: {longas}"


def test_file_read_fora_da_allowlist():
    # file_read leria segredos.toml; só volta com diretório permitido.
    assert "file_read" not in _allowlist()
