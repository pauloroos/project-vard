import codecs
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ.parent / "scripts" / "windows" / "vard-modo.ps1"
LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "rdl-vard" / "logs" / "vard-modo.log"
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só Windows")


def _rodar(verbo: str, timeout: int = 60, *, localappdata: Path | None = None) -> subprocess.CompletedProcess:
    """Com `localappdata` o script enxerga uma pasta de dados temporária (nunca a instalação real); sem ele, o real."""
    env = {**os.environ, "LOCALAPPDATA": str(localappdata)} if localappdata is not None else None
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), verbo],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def _status_com_raiz(local: Path, raiz: Path) -> dict:
    """Roda `status` com uma instalacao.json temporária (LOCALAPPDATA isolado em `local`) apontando para `raiz`."""
    pasta = local / "rdl-vard"
    pasta.mkdir(parents=True)
    (pasta / "instalacao.json").write_text(json.dumps({"raiz_codigo": str(raiz)}), encoding="utf-8")
    r = _rodar("status", localappdata=local)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_status_reconhece_o_formato_novo_e_o_antigo_da_raiz(tmp_path: Path):
    novo = tmp_path / "raiz nova"          # com espaço no caminho
    (novo / "nucleo").mkdir(parents=True)
    (novo / "nucleo" / "server.py").write_text("", encoding="utf-8")
    antigo = tmp_path / "raiz antiga"
    antigo.mkdir()
    (antigo / "server.py").write_text("", encoding="utf-8")
    assert _status_com_raiz(tmp_path / "l1", novo)["layout"] == "novo"
    assert _status_com_raiz(tmp_path / "l2", antigo)["layout"] == "antigo"


def test_instalacao_json_ilegivel_falha_com_mensagem(tmp_path: Path):
    pasta = tmp_path / "rdl-vard"
    pasta.mkdir()
    (pasta / "instalacao.json").write_text("{", encoding="utf-8")
    r = _rodar("status", localappdata=tmp_path)
    assert r.returncode != 0 and "instalacao.json" in (r.stderr + r.stdout)


def _cauda_log(n: int = 15) -> str:
    try:
        return chr(10).join(LOG.read_text(encoding="utf-8-sig", errors="replace").splitlines()[-n:])
    except OSError:
        return "(sem log)"


@pytest.mark.skipif(os.environ.get("VARD_TESTE_REAL") != "1", reason="lê a instalação real do Vard; rodar com VARD_TESTE_REAL=1")
@pytest.mark.pc_real
def test_status_reporta_variaveis():
    r = _rodar("status")
    assert r.returncode == 0, r.stderr
    dados = json.loads(r.stdout.strip().splitlines()[-1])
    assert set(dados) >= {"modo", "openjarvis", "ponte", "bandeja", "lmstudio_modelos", "variaveis_ok", "gui", "voz", "modelo", "reuniao"}
    assert dados["variaveis_ok"] is True   # neste PC as 4 variáveis de usuário existem


HARNESS_TEXTO_JOGO = """param([string]$Script)
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$d = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Jogo" }, $true) | Select-Object -First 1
[Console]::Out.Write($d.Extent.Text)
"""


def test_jogo_encerra_reuniao_antes_do_unload(tmp_path: Path):
    # Só lê o texto da função Jogo pelo AST; nunca a executa.
    h = tmp_path / "texto-jogo.ps1"
    h.write_text(HARNESS_TEXTO_JOGO, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(SCRIPT)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    jogo = r.stdout
    assert "function Jogo" in jogo, r.stderr
    assert 0 <= jogo.index("EncerrarReuniao") < jogo.index("InvocarLms unload")
    assert jogo.index('Matar "voz"') < jogo.index('Matar "reuniao"') < jogo.index('Matar "ponte"')


def test_verbo_invalido_falha_alto(tmp_path: Path):
    r = _rodar("explodir", localappdata=tmp_path)
    assert r.returncode == 1 and "verbo" in (r.stderr + r.stdout).lower()


@pytest.mark.skipif(os.environ.get("VARD_TESTE_CICLO") != "1", reason="derruba e sobe serviços; rodar com VARD_TESTE_CICLO=1")
@pytest.mark.pc_real
def test_jogo_duas_vezes():
    # jogo é idempotente: a segunda chamada não falha nem trava
    for _ in range(2):
        assert _rodar("jogo", timeout=120).returncode == 0, _cauda_log()
    dados = json.loads(_rodar("status").stdout.strip().splitlines()[-1])
    assert dados["modo"] == "jogo" and dados["openjarvis"] is None and dados["ponte"] is None
    assert dados["lmstudio_modelos"] == 0
    for porta in (8000, 4700):
        with socket.socket() as s:
            s.settimeout(1)
            assert s.connect_ex(("127.0.0.1", porta)) != 0, f"porta {porta} ainda ocupada"
    # deixa os serviços de volta no ar
    # voltar deixa filhos de longa vida (lms, Chrome): não prender o pipe de saída deles
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "voltar"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=240)
    assert r.returncode == 0, _cauda_log()
    dados = json.loads(_rodar("status").stdout.strip().splitlines()[-1])
    assert dados["modo"] == "ligado" and dados["openjarvis"] and dados["ponte"]


# Funções reais do vard-modo.ps1, extraídas pelo AST do PowerShell e rodadas com estado e log
# numa pasta temporária: prova Falhar/Recusar sem tocar no estado vivo do Vard.
HARNESS = """param([string]$Script, [string]$Pasta, [string]$Funcao)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$nomes = @("Log", "Falhar", "Recusar", "GravarEstado")
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $nomes -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
$Logs = $Pasta
$Estado = Join-Path $Pasta "estado.json"
& $Funcao "falha de teste"
"""


def _harness(tmp_path: Path, funcao: str) -> subprocess.CompletedProcess:
    h = tmp_path / "harness.ps1"
    h.write_text(HARNESS, encoding="utf-8")
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(SCRIPT), str(tmp_path), funcao],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )


def test_falhar_grava_modo_erro_com_detalhe(tmp_path: Path):
    r = _harness(tmp_path, "Falhar")
    assert r.returncode == 1, r.stderr
    dados = json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))
    assert dados["modo"] == "erro" and dados["detalhe"] == "falha de teste"
    assert "ERRO: falha de teste" in (tmp_path / "vard-modo.log").read_text(encoding="utf-8-sig")


def test_recusar_nao_mexe_no_estado(tmp_path: Path):
    r = _harness(tmp_path, "Recusar")
    assert r.returncode == 1, r.stderr
    assert not (tmp_path / "estado.json").exists()
    assert "RECUSADO: falha de teste" in (tmp_path / "vard-modo.log").read_text(encoding="utf-8-sig")


HARNESS_RECARREGAR = """param([string]$Script, [string]$Pasta)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$nomes = @("Log", "Recusar", "ModoAtual", "Recarregar")
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $nomes -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
$Logs = $Pasta
$Estado = Join-Path $Pasta "estado.json"
function Matar($nome) { Add-Content -Path (Join-Path $Pasta "matou.txt") -Value $nome }
Recarregar
"""


def test_recarregar_fora_do_modo_ligado_recusa_sem_mexer(tmp_path: Path):
    estado = tmp_path / "estado.json"
    estado.write_text('{"modo":"jogo","desde":"x","detalhe":"GPU livre"}', encoding="utf-8")
    h = tmp_path / "harness.ps1"
    h.write_text(HARNESS_RECARREGAR, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(SCRIPT), str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 1
    assert not (tmp_path / "matou.txt").exists()   # não derrubou o OpenJarvis
    assert json.loads(estado.read_text(encoding="utf-8"))["modo"] == "jogo"
    assert "RECUSADO: recarregar só com o Vard ligado (modo atual: jogo)" in (tmp_path / "vard-modo.log").read_text(encoding="utf-8-sig")


def test_garantir_modelo_so_no_texto_do_script():
    # Nada de lms real aqui: só confere a estrutura do script (BOM, função, contexto, -Corrigir).
    bruto = SCRIPT.read_bytes()
    assert bruto.startswith(codecs.BOM_UTF8)
    texto = bruto.decode("utf-8-sig")
    assert "Cfg $Inst.contexto 16384" in texto
    assert "function GarantirModelo" in texto and "function DiagnosticoModelo" in texto
    assert "[switch]$Corrigir" in texto
    assert "--context-length $Contexto" in texto and "--context-length 16384" not in texto
    assert "--parallel 2" in texto and "--no-speculative-draft-mtp" in texto
    corpo_iniciar = texto.split("function Iniciar()")[1].split("function Jogo()")[0]
    assert "GarantirModelo" in corpo_iniciar and "InvocarLms load" not in corpo_iniciar
    corpo_status = texto.split("function Status()")[1].split("function Sonda()")[0]
    assert "GarantirModelo" not in corpo_status   # status é só leitura


def test_recarregar_pausa_e_reinicia_a_ponte():
    # Estrutura do script: 15 s entre parar e subir o OpenJarvis (409 do Telegram) e a ponte também reinicia.
    texto = SCRIPT.read_bytes().decode("utf-8-sig")
    corpo = texto[texto.index("function Recarregar"):texto.index("function Status")]
    assert 'Matar "openjarvis"' in corpo and "Start-Sleep -Seconds 15" in corpo
    assert corpo.index("Start-Sleep -Seconds 15") < corpo.index('Subir "openjarvis"')
    assert 'Matar "ponte"' in corpo and 'Subir "ponte"' in corpo


HARNESS_RECARREGAR_REUNIAO = """param([string]$Script, [string]$Pasta, [string]$Reuniao)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$nomes = @("Log", "Recusar", "ModoAtual", "Recarregar")
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $nomes -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
$Logs = $Pasta
$Estado = Join-Path $Pasta "estado.json"
function EstadoReuniao() { return $Reuniao }
function Matar($nome) { Add-Content -Path (Join-Path $Pasta "matou.txt") -Value $nome }
Recarregar
"""


def test_recarregar_recusa_com_reuniao_ativa_antes_de_matar(tmp_path: Path):
    (tmp_path / "estado.json").write_text('{"modo":"ligado","desde":"x","detalhe":""}', encoding="utf-8")
    h = tmp_path / "harness.ps1"
    h.write_text(HARNESS_RECARREGAR_REUNIAO, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(SCRIPT), str(tmp_path), "ativa"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 1
    assert not (tmp_path / "matou.txt").exists()
    assert "RECUSADO: encerre a reunião antes de recarregar" in (tmp_path / "vard-modo.log").read_text(encoding="utf-8-sig")


def test_recarregar_consulta_a_reuniao_antes_de_qualquer_matar(tmp_path: Path):
    # Estrutura (AST): em Recarregar, EstadoReuniao -eq "ativa" aparece antes do primeiro Matar.
    ps = "param($Script); " + "; ".join([
        '$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)',
        '$f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Recarregar" }, $true)',
        '$cmds = $f.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)',
        '($cmds | ForEach-Object { $_.GetCommandName() }) -join ","',
    ])
    h = tmp_path / "ast.ps1"
    h.write_text(ps, encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h), str(SCRIPT)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    nomes = r.stdout.strip().split(",")
    assert "EstadoReuniao" in nomes and "Matar" in nomes and nomes.index("EstadoReuniao") < nomes.index("Matar"), r.stdout + r.stderr


@pytest.fixture(autouse=True)
def _harness_powershell(powershell_isolado):
    pass


@pytest.fixture(autouse=True)
def _modo_sem_sondas(script_modo_isolado, monkeypatch, request):
    if request.node.get_closest_marker("pc_real"):
        return
    import sys
    monkeypatch.setattr(sys.modules[__name__], "SCRIPT", script_modo_isolado)
