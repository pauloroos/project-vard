"""Fixtures comuns. Config e dados do usuário nunca são os reais: o ambiente é isolado ANTES de qualquer import do vard."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from guarda_pc import (instalar, guarda_pc, powershell_isolado, pytest_addoption,
                      pytest_configure, pytest_collection_modifyitems)

instalar()

import os
import atexit
import shutil
import tempfile
from pathlib import Path

_RAIZ_TESTE = Path(tempfile.mkdtemp(prefix="vard-teste-"))
atexit.register(shutil.rmtree, _RAIZ_TESTE, ignore_errors=True)
CONFIG_TESTE = Path(__file__).parent / "fixtures" / "config"
if "--pc-real" not in sys.argv:
    os.environ["VARD_CONFIG"] = str(_RAIZ_TESTE / "config")
    os.environ["VARD_DADOS"] = str(_RAIZ_TESTE / "dados")
os.environ.setdefault("VARD_SEM_VIGIA", "1")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _ambiente_isolado(tmp_path: Path, monkeypatch, request):
    """Cada teste enxerga config/dados vazios em pasta temporária (processos filhos herdam o ambiente)."""
    if request.node.get_closest_marker("pc_real") and request.config.getoption("--pc-real"):
        return
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


@pytest.fixture
def script_modo_isolado(tmp_path):
    fonte = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "vard-modo.ps1"
    texto = fonte.read_text(encoding="utf-8-sig")
    texto = texto.replace('[Environment]::GetEnvironmentVariable($n, "User")', "''")
    dubles = '\n# Sondas ficticias; fluxo e publicacao IPC preservados.\nfunction EstadoVoz { "desligado" }\nfunction EstadoReuniao { "desligado" }\nfunction ModelosCarregados { 0 }\nfunction DiagnosticoModelo { "modelo-ficticio" }\nfunction LerPid($nome) { $null }\n'
    texto = texto.replace('if (PublicarNaCaixa $Verbo)', dubles + '\nif (PublicarNaCaixa $Verbo)')
    alvo = tmp_path / "vard-modo.ps1"
    alvo.write_text(texto, encoding="utf-8-sig")
    return alvo
