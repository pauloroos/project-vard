"""Higiene dos scripts em scripts/windows: caminhos do repositório, instalacao.json e segredos."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO = RAIZ / "scripts" / "windows"
PATCHES = RAIZ / "scripts" / "openjarvis" / "patches"
INSTALADOR = CAMINHO / "instalar-openjarvis.ps1"
PIN = "ccf02ec7bdda2e2b344eeb8dd986d742ff458acc"

HARNESS_INSTALACAO = """param([string]$Script)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$d = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "LerInstalacao" }, $true) | Select-Object -First 1
. ([scriptblock]::Create($d.Extent.Text))
$r = LerInstalacao
if ($null -eq $r) { Write-Output "VAZIO" } else { Write-Output ("{0}|{1}" -f $r.openjarvis_src, $r.openjarvis_home) }
"""


def test_aplicar_config_nao_reescreve_o_segredos_inteiro():
    texto = (CAMINHO / "aplicar-config.ps1").read_text(encoding="utf-8-sig")
    assert "WriteAllText($segredos" not in texto and "s.gravar(" in texto


def test_gravar_segredo_ps1_nao_ecoa_e_tem_bom():
    bruto = (CAMINHO / "gravar-segredo.ps1").read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")
    texto = bruto.decode("utf-8-sig")
    assert "-AsSecureString" in texto and "VARD_SEGREDO_VALOR" in texto


def test_instalar_openjarvis_usa_os_patches_ao_lado_do_script():
    texto = (CAMINHO / "instalar-openjarvis.ps1").read_text(encoding="utf-8-sig")
    assert "$PSScriptRoot/../openjarvis/patches" in texto
    assert PIN in texto and "X:\\openjarvis" not in texto   # pin fixado e sem pasta fixa
    for nome in ("openjarvis-telegram-allowed-chat-ids", "openjarvis-telegram-marca",
                 "openjarvis-chat-extra", "openjarvis-open-browser"):
        assert (PATCHES / f"{nome}.patch").exists(), nome


def test_nenhum_script_aponta_para_a_antiga_pasta_deploy():
    for arq in sorted(CAMINHO.glob("*.ps1")):
        texto = arq.read_bytes().decode("utf-8-sig")
        if arq.name == "vard-modo.ps1":   # só ele conhece o formato antigo da raiz (retorno em um passo)
            texto = texto.replace("deploy" + chr(92) + "bandeja.py", "")
        assert "deploy\\" not in texto and "deploy/" not in texto, arq.name


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="só Windows com PowerShell")
def test_instalar_openjarvis_le_o_instalacao_json(tmp_path: Path):
    """VARD_INSTALACAO vence; depois a pasta de dados; sem arquivo, fica vazio (o script pede -Src/-Home)."""
    h = tmp_path / "harness.ps1"
    h.write_text(HARNESS_INSTALACAO, encoding="utf-8")

    def rodar(**env: str) -> str:
        base = {k: v for k, v in os.environ.items() if k not in ("VARD_INSTALACAO", "VARD_DADOS")}
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(INSTALADOR)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                           env={**base, **env})
        assert r.returncode == 0, r.stderr
        return r.stdout.strip().splitlines()[-1]

    fora = tmp_path / "instalacao-fora.json"
    fora.write_text(json.dumps({"openjarvis_src": "X:/oj/src", "openjarvis_home": "X:/oj/home"}), encoding="utf-8")
    assert rodar(VARD_INSTALACAO=str(fora), VARD_DADOS=str(tmp_path / "outro")) == "X:/oj/src|X:/oj/home"

    dados = tmp_path / "dados"
    dados.mkdir()
    (dados / "instalacao.json").write_text(json.dumps({"openjarvis_src": "X:/outro/src"}), encoding="utf-8")
    assert rodar(VARD_DADOS=str(dados)) == "X:/outro/src|"

    assert rodar(VARD_INSTALACAO=str(tmp_path / "nao-existe.json")) == "VAZIO"
