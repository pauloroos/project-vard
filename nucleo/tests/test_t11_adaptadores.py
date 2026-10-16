"""Testes T11: adaptadores dos scripts (vard-modo.ps1, tarefa-logon.ps1, bandeja.py).

Regra: com supervisor:false ou app não vivo, comportamento legado preservado.
Com supervisor:true e app vivo, verbos publicados na caixa IPC, bandeja não inicia,
atalhos apontam para vard.exe.

Todos os testes usam pastas temporárias — nunca tocam em Startup/Vard.lnk reais.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT_MODO = REPO / "scripts" / "windows" / "vard-modo.ps1"
SCRIPT_LOGON = REPO / "scripts" / "windows" / "tarefa-logon.ps1"


def _criar_instalacao(dados: Path, supervisor: bool) -> None:
    """Cria instalacao.json no diretório de dados temporário."""
    cfg = {"supervisor": supervisor, "servicos": {"voz": True, "reuniao": True, "openjarvis": True}}
    (dados / "instalacao.json").write_text(json.dumps(cfg), encoding="utf-8")


def _criar_app_vivo(dados: Path, sessao_id: str | None = None) -> None:
    """Cria ciclo/app.json simulando app novo vivo."""
    ciclo = dados / "ciclo"
    ciclo.mkdir(parents=True, exist_ok=True)
    sid = sessao_id or str(uuid.uuid4())
    (ciclo / "app.json").write_text(json.dumps({"pid": 99999, "sessao_id": sid}), encoding="utf-8")


def _preparar_localappdata(tmp_path: Path, supervisor: bool, com_app: bool = True, sessao_id: str | None = None) -> Path:
    """Cria estrutura fake do LOCALAPPDATA/rdl-vard para testes do vard-modo.ps1.

    O script usa $Pasta = Join-Path $env:LOCALAPPDATA "rdl-vard" (hardcoded),
    então precisamos sobrescrever LOCALAPPDATA para isolar o teste.
    """
    fake_localappdata = tmp_path / "LocalAppData"
    fake_localappdata.mkdir()
    rdl_vard = fake_localappdata / "rdl-vard"
    rdl_vard.mkdir()
    _criar_instalacao(rdl_vard, supervisor)
    if com_app:
        _criar_app_vivo(rdl_vard, sessao_id)
    return fake_localappdata


class TestVardModoAdaptador:
    """vard-modo.ps1 publica na caixa IPC quando supervisor ativo."""

    def test_publica_na_caixa_com_supervisor_ativo(self, tmp_path: Path) -> None:
        """Com supervisor:true e app vivo, verbo vai para ciclo/pedidos/."""
        fake_localappdata = _preparar_localappdata(
            tmp_path, supervisor=True, com_app=True, sessao_id="sessao-teste-t11"
        )
        rdl_vard = fake_localappdata / "rdl-vard"

        env = {**os.environ, "LOCALAPPDATA": str(fake_localappdata)}
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT_MODO), "sonda"],
            capture_output=True, text=True, errors="replace", env=env, timeout=30,
        )
        assert resultado.returncode == 0, f"script falhou: stderr={resultado.stderr} stdout={resultado.stdout}"

        pedidos_dir = rdl_vard / "ciclo" / "pedidos"
        assert pedidos_dir.exists(), f"pasta de pedidos não criada; stdout={resultado.stdout} stderr={resultado.stderr}"
        arquivos = list(pedidos_dir.glob("*.json"))
        assert len(arquivos) == 1, f"esperado 1 pedido, encontrado {len(arquivos)}"

        pedido = json.loads(arquivos[0].read_text(encoding="utf-8"))
        assert pedido["verbo"] == "sonda"
        assert pedido["sessao"] == "sessao-teste-t11"
        assert "id" in pedido

    def test_nao_publica_sem_supervisor(self, tmp_path: Path) -> None:
        """Com supervisor:false, script segue caminho legado (não cria pedido)."""
        fake_localappdata = _preparar_localappdata(tmp_path, supervisor=False, com_app=True)
        rdl_vard = fake_localappdata / "rdl-vard"

        env = {**os.environ, "LOCALAPPDATA": str(fake_localappdata)}
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT_MODO), "sonda"],
            capture_output=True, text=True, errors="replace", env=env, timeout=30,
        )

        pedidos_dir = rdl_vard / "ciclo" / "pedidos"
        if pedidos_dir.exists():
            arquivos = list(pedidos_dir.glob("*.json"))
            assert len(arquivos) == 0, f"modo legado não deveria criar pedidos, encontrou {len(arquivos)}"

    def test_nao_publica_sem_app_vivo(self, tmp_path: Path) -> None:
        """Com supervisor:true mas sem app.json, script segue caminho legado."""
        fake_localappdata = _preparar_localappdata(tmp_path, supervisor=True, com_app=False)
        rdl_vard = fake_localappdata / "rdl-vard"

        env = {**os.environ, "LOCALAPPDATA": str(fake_localappdata)}
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT_MODO), "sonda"],
            capture_output=True, text=True, errors="replace", env=env, timeout=30,
        )

        pedidos_dir = rdl_vard / "ciclo" / "pedidos"
        if pedidos_dir.exists():
            arquivos = list(pedidos_dir.glob("*.json"))
            assert len(arquivos) == 0, f"sem app vivo não deveria criar pedidos, encontrou {len(arquivos)}"


class TestBandejaGuardaSupervisor:
    """bandeja.py não inicia quando supervisor está ativo."""

    def _codigo_supervisor_check(self, repo: Path, tmp_path: Path, esperado: bool) -> str:
        """Gera código Python inline que testa _supervisor_ativo() com mocks completos."""
        return f"""
import sys, os, types

# Mock PIL antes de qualquer import do vard
pil_mock = types.ModuleType("PIL")
pil_image_mock = types.ModuleType("PIL.Image")
pil_draw_mock = types.ModuleType("PIL.ImageDraw")
pil_image_mock.Image = type("Image", (), {{}})
pil_image_mock.new = lambda *a, **kw: None
pil_draw_mock.Draw = lambda *a, **kw: None
sys.modules["PIL"] = pil_mock
sys.modules["PIL.Image"] = pil_image_mock
sys.modules["PIL.ImageDraw"] = pil_draw_mock

# Mock pystray
pystray_mock = types.ModuleType("pystray")
pystray_mock.Icon = type("Icon", (), {{}})
pystray_mock.Menu = type("Menu", (), {{"SEPARATOR": None}})
pystray_mock.MenuItem = type("MenuItem", (), {{}})
sys.modules["pystray"] = pystray_mock

sys.path.insert(0, r"{repo / 'nucleo'}")
sys.path.insert(0, r"{repo / 'scripts' / 'windows'}")
os.environ["VARD_DADOS"] = r"{tmp_path}"

from bandeja import _supervisor_ativo
assert _supervisor_ativo() is {esperado}, f"esperado {esperado}, obtido {{_supervisor_ativo()}}"
"""

    def _python_do_venv(self) -> str:
        """Retorna o caminho do Python do venv do núcleo (com dependências instaladas)."""
        venv_python = REPO / "nucleo" / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    def test_bandeja_nao_inicia_com_supervisor(self, tmp_path: Path) -> None:
        """Com supervisor ativo, _supervisor_ativo() retorna True."""
        _criar_instalacao(tmp_path, supervisor=True)
        _criar_app_vivo(tmp_path)

        codigo = self._codigo_supervisor_check(REPO, tmp_path, True)
        resultado = subprocess.run(
            [self._python_do_venv(), "-c", codigo],
            capture_output=True, text=True, timeout=15,
        )
        assert resultado.returncode == 0, f"falha: {resultado.stderr}"

    def test_bandeja_inicia_sem_supervisor(self, tmp_path: Path) -> None:
        """Sem supervisor, _supervisor_ativo() retorna False."""
        _criar_instalacao(tmp_path, supervisor=False)

        codigo = self._codigo_supervisor_check(REPO, tmp_path, False)
        resultado = subprocess.run(
            [self._python_do_venv(), "-c", codigo],
            capture_output=True, text=True, timeout=15,
        )
        assert resultado.returncode == 0, f"falha: {resultado.stderr}"


class TestTarefaLogonAdaptador:
    """tarefa-logon.ps1 cria atalhos corretos por modo.

    Startup e Desktop vêm de VARD_PASTA_STARTUP/VARD_PASTA_DESKTOP apontadas para tmp_path:
    sem isso o script usaria as pastas reais do usuário (GetFolderPath ignora APPDATA).
    """

    def _rodar(self, tmp_path: Path, supervisor: bool, exe: Path | None = None) -> tuple[subprocess.CompletedProcess, Path, Path]:
        dados = tmp_path / "dados"
        dados.mkdir()
        _criar_instalacao(dados, supervisor=supervisor)
        startup = tmp_path / "Startup"
        desk = tmp_path / "Desktop"
        startup.mkdir()
        desk.mkdir()
        env = {
            **os.environ,
            "VARD_DADOS": str(dados),
            "VARD_PASTA_STARTUP": str(startup),
            "VARD_PASTA_DESKTOP": str(desk),
            # Exe inexistente por padrão: o vard.exe compilado no repositório não decide o modo do teste.
            "VARD_HUD_EXE": str(exe or (tmp_path / "ausente" / "vard.exe")),
        }
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT_LOGON)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=30,
        )
        return resultado, startup, desk

    @staticmethod
    def _alvo(lnk: Path) -> tuple[str, str]:
        script = f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); $l.TargetPath; $l.Arguments"
        harness = lnk.parent / "ler-atalho.ps1"
        harness.write_text(script, encoding="utf-8-sig")
        r = subprocess.run(
            ["powershell", "-NoProfile", "-File", str(harness)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        linhas = r.stdout.splitlines() + ["", ""]
        return linhas[0].strip(), linhas[1].strip()

    def test_logon_aponta_para_exe_com_supervisor(self, tmp_path: Path) -> None:
        """Com supervisor:true e vard.exe presente, os três atalhos apontam para o exe."""
        exe_falso = tmp_path / "bin" / "vard.exe"
        exe_falso.parent.mkdir()
        exe_falso.write_bytes(bytes([0x4D, 0x5A, 0, 0]))

        resultado, startup, desk = self._rodar(tmp_path, supervisor=True, exe=exe_falso)

        assert resultado.returncode == 0, f"stderr={resultado.stderr}"
        for lnk in (startup / "Vard.lnk", desk / "Vard - Modo jogo.lnk", desk / "Vard - Voltar.lnk"):
            assert lnk.exists(), f"atalho não criado na pasta temporária: {lnk.name}"
            alvo, _ = self._alvo(lnk)
            assert Path(alvo) == exe_falso

    def test_logon_legado_sem_supervisor(self, tmp_path: Path) -> None:
        """Com supervisor:false, atalhos apontam para powershell.exe + vard-modo.ps1 (legado)."""
        resultado, startup, desk = self._rodar(tmp_path, supervisor=False)

        assert resultado.returncode == 0, f"stderr={resultado.stderr}"
        esperados = {startup / "Vard.lnk": "iniciar", desk / "Vard - Modo jogo.lnk": "jogo", desk / "Vard - Voltar.lnk": "voltar"}
        for lnk, verbo in esperados.items():
            assert lnk.exists(), f"atalho não criado na pasta temporária: {lnk.name}"
            alvo, args = self._alvo(lnk)
            assert alvo.lower().endswith("powershell.exe")
            assert "vard-modo.ps1" in args and args.endswith(verbo)

    def test_logon_supervisor_sem_exe_cai_no_legado(self, tmp_path: Path) -> None:
        """supervisor:true sem vard.exe mantém o legado (não aponta para exe inexistente)."""
        resultado, startup, _ = self._rodar(tmp_path, supervisor=True)

        assert resultado.returncode == 0, f"stderr={resultado.stderr}"
        alvo, _ = self._alvo(startup / "Vard.lnk")
        assert alvo.lower().endswith("powershell.exe")


@pytest.fixture(autouse=True)
def _harness_powershell(powershell_isolado):
    pass


@pytest.fixture(autouse=True)
def _modo_sem_sondas(script_modo_isolado, monkeypatch):
    import sys
    monkeypatch.setattr(sys.modules[__name__], "SCRIPT_MODO", script_modo_isolado)


@pytest.fixture(autouse=True)
def _logon_temporario(tmp_path, monkeypatch):
    import sys
    copia = tmp_path / "tarefa-logon.ps1"
    shutil.copyfile(SCRIPT_LOGON, copia)
    monkeypatch.setattr(sys.modules[__name__], "SCRIPT_LOGON", copia)
