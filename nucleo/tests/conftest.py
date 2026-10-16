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


@pytest.fixture(autouse=True, scope="session")
def _d3_garantia_sem_cli_falsa_orfa():
    """D3: suíte inteira encerra a ÁRVORE de toda CLI falsa que abrir.

    - Dublê de `_encerrar_arvore` usando psutil (a guarda dos testes proíbe taskkill).
    - Verificação ao fim da sessão que FALHA se sobrar processo com cli_viva.py/cli_falsa.py.
    """
    import psutil
    import vard.cerebro.cli_processos as cli_mod

    def _encerrar_arvore_psutil(pid: int) -> None:
        if pid <= 0:
            return
        try:
            raiz = psutil.Process(pid)
            filhos = raiz.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            return
        for proc in filhos + [raiz]:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass

    original = cli_mod._encerrar_arvore
    cli_mod._encerrar_arvore = _encerrar_arvore_psutil  # type: ignore[assignment]
    yield
    cli_mod._encerrar_arvore = original  # type: ignore[assignment]

    # Verificação final: nenhum processo cli_viva.py/cli_falsa.py pode sobreviver.
    import subprocess as _sp
    try:
        ps = _sp.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cli_(viva|falsa)\\.py' } | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=15,
        )
        pids = [int(p.strip()) for p in ps.stdout.splitlines() if p.strip().isdigit()]
    except Exception:
        pids = []
    if pids:
        # Tenta limpar para não contaminar o ambiente do desenvolvedor.
        for pid in pids:
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass
        raise AssertionError(f"D3: processos cli_falsa/cli_viva órfãos ao fim da suíte: {pids}")


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
