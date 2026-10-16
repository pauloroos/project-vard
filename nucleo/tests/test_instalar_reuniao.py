"""Estrutura de scripts/windows/instalar-reuniao.ps1 pelo AST do PowerShell (o instalador de verdade baixa modelos: não roda em teste)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
INSTALADOR = RAIZ.parent / "scripts" / "windows" / "instalar-reuniao.ps1"
DIARIZACAO = RAIZ.parent / "reuniao" / "vard_reuniao" / "diarizacao.py"
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="só Windows com PowerShell")

URLS = [
    "https://huggingface.co/pyannote/speaker-diarization-community-1",
    "https://huggingface.co/pyannote/segmentation-3.0",
    "https://huggingface.co/pyannote/speaker-diarization-3.1",
]

HARNESS = r"""param([string]$Script)
$erros = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$erros)
$cmds = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)
$saida = @{
  erros = @($erros | ForEach-Object { $_.Message })
  comandos = @($cmds | ForEach-Object { @{ nome = $_.GetCommandName(); texto = $_.Extent.Text } })
  variaveis = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) |
                ForEach-Object { $_.VariablePath.UserPath })
}
$saida | ConvertTo-Json -Depth 4 -Compress
"""


@pytest.fixture
def ast(tmp_path, powershell_isolado):
    arq = tmp_path / "harness.ps1"
    arq.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(arq), str(INSTALADOR)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def texto() -> str:
    return INSTALADOR.read_bytes().decode("utf-8-sig")


def test_tem_bom_e_nao_tem_erro_de_sintaxe(ast):
    assert INSTALADOR.read_bytes().startswith(b"\xef\xbb\xbf")
    assert ast["erros"] == []


def test_baixa_pelo_snapshot_download_com_as_tres_urls():
    t = texto()
    assert "snapshot_download" in t
    for u in URLS:
        assert u in t
    assert "Aceite as condições em" in t and "e rode de novo" in t


def test_modelos_do_instalador_sao_os_do_codigo():
    ids = re.findall(r"https://huggingface\.co/(pyannote/[\w.\-]+)", texto())
    fonte = DIARIZACAO.read_text(encoding="utf-8")
    for repo in dict.fromkeys(ids):
        assert f'"{repo}"' in fonte


def test_token_so_por_variavel_de_ambiente(ast):
    t = texto()
    assert "$env:HF_TOKEN" in t and "env:HF_TOKEN" in ast["variaveis"]
    # nenhum comando de saída, de arquivo ou de execução recebe o token
    for c in ast["comandos"]:
        if "HF_TOKEN" in c["texto"] or "$token" in c["texto"]:
            assert c["nome"] in {"Remove-Item", None}, c
    assert not re.search(r"Write-(Host|Output|Warning|Error|Verbose)[^\n]*\$(env:HF_TOKEN|token)\b", t)
    assert "--token" not in t and "-token" not in t.lower().replace("$token", "")


def test_le_o_token_pelo_segredos_e_isola_o_home_do_hf():
    t = texto()
    assert "from vard import segredos as s; print(s.huggingface())" in t
    assert "HF_HOME" in t and "HF_HUB_DISABLE_TELEMETRY" in t and "HF_HUB_OFFLINE" in t
    assert 'rdl-vard' in t and "modelos\\hf" in t


def test_grava_o_estado_dos_tres_desfechos():
    t = texto()
    assert "reuniao-modelos.json" in t
    assert 'modo = "community-1"' in t and '$modo = "reserva"' in t
    assert "condições não aceitas: " in t
    assert "sem token: scripts\\windows\\gravar-segredo.ps1 -Secao huggingface -Chave token" in t
    assert "uv sync --project" in t


def test_desliga_a_telemetria_do_pyannote_no_download_e_na_prova():
    t = texto()
    var = '$env:PYANNOTE_METRICS_ENABLED = "0"'
    assert t.count(var) == 2
    assert t.index(var) < t.index("snapshot_download") or t.index(var) < t.index("Baixando os modelos")
    assert t.rindex(var) > t.index("Prova offline")


@pytest.fixture(autouse=True)
def _harness_powershell(powershell_isolado):
    pass
