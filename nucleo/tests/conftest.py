"""Fixtures comuns. Config e dados do usuário nunca são os reais: o ambiente é isolado ANTES de qualquer import do vard."""
import os
import shutil
import tempfile
from pathlib import Path

_RAIZ_TESTE = Path(tempfile.mkdtemp(prefix="vard-teste-"))
CONFIG_TESTE = Path(__file__).parent / "fixtures" / "config"
os.environ["VARD_CONFIG"] = str(_RAIZ_TESTE / "config")
os.environ["VARD_DADOS"] = str(_RAIZ_TESTE / "dados")
os.environ.setdefault("VARD_SEM_VIGIA", "1")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _ambiente_isolado(tmp_path: Path, monkeypatch):
    """Cada teste enxerga config/dados vazios em pasta temporária (processos filhos herdam o ambiente)."""
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))
    monkeypatch.delenv("OPENJARVIS_HOME", raising=False)   # a instalação real do PC nunca entra nos testes
    monkeypatch.delenv("VARD_INSTALACAO", raising=False)


@pytest.fixture
def config_usuario(tmp_path: Path) -> Path:
    """Configuração fictícia do usuário (delegada.toml, pasta delegada/ e memoria.toml) na pasta isolada."""
    destino = tmp_path / "config"
    shutil.copytree(CONFIG_TESTE, destino, dirs_exist_ok=True)
    return destino


@pytest.fixture(autouse=True)
def _marca_telegram_isolada(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_MARCA_TELEGRAM", str(tmp_path / "ultimo-telegram.json"))


@pytest.fixture
def loja(tmp_path: Path, monkeypatch) -> Path:
    """Loja de tarefas numa pasta temporária (nunca no %LOCALAPPDATA% real)."""
    from vard import tarefas  # entra em T4

    arq = tmp_path / "tarefas.json"
    monkeypatch.setattr(tarefas, "ARQUIVO", arq)
    monkeypatch.setattr(tarefas, "PASTA_RESULTADOS", tmp_path / "tarefas")
    return arq
