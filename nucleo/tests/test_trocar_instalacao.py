"""trocar-instalacao.ps1: estrutura e o que dá para provar sem mexer na instalação real (nada de jogo/parar)."""
import codecs
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "trocar-instalacao.ps1"
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só Windows")


def _texto() -> str:
    bruto = SCRIPT.read_bytes()
    assert bruto.startswith(codecs.BOM_UTF8)
    return bruto.decode("utf-8-sig")


def test_sintaxe_valida():
    cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($env:SCRIPT_ALVO,[ref]$null,[ref]$e); $e.Count")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, env={**os.environ, "SCRIPT_ALVO": str(SCRIPT)})
    assert r.stdout.strip() == "0", r.stdout + r.stderr


def test_nao_usa_os_verbos_destrutivos_do_modo():
    texto = _texto()
    assert not re.search(r"vard-modo\.ps1\"?\)?\s+(jogo|parar)\b", texto)
    assert "recarregar" in texto            # a troca é por recarregar (OpenJarvis e ponte), nunca desligando tudo


def test_tem_os_quatro_modos_e_o_retorno_restaura_do_backup():
    texto = _texto()
    for modo in ("-Candidato", "-Promover", "-Reverter", "-Status"):
        assert modo in texto
    assert "Restaurar-Backup" in texto and "variaveis.json" in texto
    assert "Move-Item -Force" in texto       # gravações atômicas (tmp + move)


def test_status_com_pasta_temporaria(tmp_path: Path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path / "pasta com espaço")}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Status", "-Raiz", str(tmp_path / "raiz x")],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    dados = json.loads(r.stdout.strip().splitlines()[-1])
    assert dados["promovida"] is False and dados["instalacao"] is False


def test_promover_sem_candidato_recusa(tmp_path: Path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Promover"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode != 0
    assert not (tmp_path / "rdl-vard" / "instalacao.json").exists()


def test_reverter_sem_promocao_recusa(tmp_path: Path):
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Reverter"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode != 0
