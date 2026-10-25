"""Decisão real do script com HUD fictício; nenhum serviço ou dado do usuário."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts/windows/vard-modo.ps1"
HARNESS = '''param([string]$Script, [string]$Pasta, [string]$Instalacao)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "DeveSubirOpenJarvis" }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
$Inst = Get-Content -LiteralPath $Instalacao -Raw -Encoding UTF8 | ConvertFrom-Json
[Console]::Out.Write((DeveSubirOpenJarvis | ConvertTo-Json -Compress))
'''


@pytest.mark.parametrize("hud,esperado", [
    (None, True), ({}, True), ({"cerebro": "openjarvis"}, True),
    ({"cerebro": "proprio"}, False),
    ({"cerebro": "proprio", "usar_openjarvis": False}, False),
    ({"cerebro": "proprio", "usar_openjarvis": True}, True),
    ({"cerebro": "proprio", "usar_openjarvis": "true"}, False),
    ("{invalido", True),
])
@pytest.mark.parametrize("pasta_hud", ["instalado", "dev"])
def test_decisao_le_hud_do_build_e_preserva_padrao_antigo(tmp_path, powershell_isolado, hud, esperado, pasta_hud):
    appdata = tmp_path / "roaming"
    identificador = "io.github.pauloroos.vard" + (".dev" if pasta_hud == "dev" else "")
    pasta = appdata / identificador
    pasta.mkdir(parents=True)
    if hud is not None:
        (pasta / "hud.config.json").write_text(hud if isinstance(hud, str) else json.dumps(hud), encoding="utf-8")
    # A escolha obsoleta na instalação e o caminho antigo não podem prevalecer.
    dados = tmp_path / "dados"
    (dados / "config").mkdir(parents=True)
    (dados / "config/hud.json").write_text('{"cerebro":"proprio"}', encoding="utf-8")
    instalacao = tmp_path / "instalacao.json"
    instalacao.write_text(json.dumps({"servicos": {"openjarvis": True}, "cerebro": "proprio", "usar_openjarvis": False}), encoding="utf-8")
    harness = tmp_path / "decisao.ps1"
    harness.write_text(HARNESS, encoding="utf-8")
    ambiente = {**os.environ, "APPDATA": str(appdata)}
    ambiente.pop("VARD_HUD_CONFIG_DIR", None)
    if pasta_hud == "dev":
        ambiente["VARD_HUD_CONFIG_DIR"] = str(pasta)
    resultado = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness), str(SCRIPT), str(dados), str(instalacao)], env=ambiente, capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
    assert json.loads(resultado.stdout) is esperado


HARNESS_CICLO = '''param([string]$Script, [string]$Verbo)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$nomes = @("DeveSubirOpenJarvis", "Recarregar", "Jogo")
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $nomes -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
$Inst = [pscustomobject]@{ servicos = [pscustomobject]@{ openjarvis = $true } }
$eventos = [System.Collections.Generic.List[string]]::new()
function Matar($nome) { $eventos.Add("parar:$nome") }
function Subir($nome) { $eventos.Add("iniciar:$nome") }
function ModoAtual { "ligado" }
function EstadoReuniao { "desligado" }
function Esperar { $true }
function Log {}
function GravarEstado {}
function Start-Sleep {}
function EncerrarReuniao {}
function InvocarLms { $global:LASTEXITCODE = 0 }
function AdotarVoz {}
function AdotarReuniao {}
& $Verbo
[Console]::Out.Write((ConvertTo-Json -InputObject @($eventos.ToArray()) -Compress))
'''


@pytest.mark.parametrize("verbo", ["Recarregar", "Jogo"])
def test_desligar_opcao_encerra_openjarvis_que_ja_estava_ativo(tmp_path, powershell_isolado, verbo):
    pasta = tmp_path / "hud"
    pasta.mkdir()
    (pasta / "hud.config.json").write_text('{"cerebro":"proprio","usar_openjarvis":false}', encoding="utf-8")
    harness = tmp_path / "ciclo.ps1"
    harness.write_text(HARNESS_CICLO, encoding="utf-8")
    resultado = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness), str(SCRIPT), verbo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
    eventos = json.loads(resultado.stdout)
    assert "parar:openjarvis" in eventos
    assert "parar:gui" in eventos
    assert "iniciar:openjarvis" not in eventos
    assert "iniciar:gui" not in eventos
