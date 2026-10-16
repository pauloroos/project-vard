"""AplicarPatch do instalar-openjarvis.ps1 num repositório git temporário (nunca no clone real).

A função real é extraída pelo AST do PowerShell. Prova: aplica no commit fixado, pula quando o
upstream já tem a correção e, no -Atualizar, volta ao commit fixado com o patch se não couber.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
INSTALADOR = RAIZ.parent / "scripts" / "windows" / "instalar-openjarvis.ps1"
PATCH = RAIZ.parent / "scripts" / "openjarvis" / "patches" / "openjarvis-telegram-allowed-chat-ids.patch"
REL = "src/openjarvis/system/_channel_kwargs.py"
pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("git"), reason="só Windows com git")

# Começo do arquivo do upstream no commit fixado (contexto que o patch exige).
ORIGINAL = '''"""Per-channel config->kwargs mappers for ChannelRegistry.create()."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def _telegram(c: Any) -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if c.bot_token:
        kw["bot_token"] = c.bot_token
    if c.parse_mode:
        kw["parse_mode"] = c.parse_mode
    return kw


def _discord(c: Any) -> Dict[str, Any]:
    return {"bot_token": c.bot_token} if c.bot_token else {}
'''
# Versão nova do upstream que mexeu na função (o patch não cabe mais).
MUDADO = ORIGINAL.replace('''    if c.parse_mode:
        kw["parse_mode"] = c.parse_mode
    return kw''', '''    kw["parse_mode"] = c.parse_mode or "HTML"
    kw["timeout"] = 30
    return dict(kw)''')
# Versão nova do upstream que já repassa allowed_chat_ids.
ABSORVIDO = ORIGINAL.replace("    return kw\n", '    kw["allowed_chat_ids"] = c.allowed_chat_ids\n    return kw\n', 1)

HARNESS = """param([string]$Script, [string]$Repo, [string]$Patch, [string]$Fixado, [string]$Atualizando)
$ErrorActionPreference = "Stop"
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$nomes = @("Exigir", "AplicarPatch")
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $nomes -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
try { $r = AplicarPatch $Repo $Patch $Fixado ($Atualizando -eq "1"); Write-Output "OK: $r" }
catch { Write-Output "ERRO: $($_.Exception.Message)" }
"""


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _commit(repo: Path, conteudo: str, msg: str) -> str:
    arq = repo / REL
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(conteudo, encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=teste", "-c", "user.email=teste@exemplo", "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "oj"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "core.autocrlf", "false")
    return r


def _aplicar(tmp_path: Path, repo: Path, fixado: str, atualizando: bool) -> str:
    h = tmp_path / "harness.ps1"
    h.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(h),
         str(INSTALADOR), str(repo), str(PATCH), fixado, "1" if atualizando else "0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    return r.stdout + r.stderr


def _tem_patch(repo: Path) -> bool:
    return 'kw["allowed_chat_ids"]' in (repo / REL).read_text(encoding="utf-8")


def test_aplica_no_commit_fixado(tmp_path: Path, repo: Path):
    fixado = _commit(repo, ORIGINAL, "fixado")
    assert "OK: aplicado" in _aplicar(tmp_path, repo, fixado, atualizando=False)
    assert _tem_patch(repo)


def test_pula_quando_o_upstream_ja_tem(tmp_path: Path, repo: Path):
    fixado = _commit(repo, ORIGINAL, "fixado")
    _commit(repo, ABSORVIDO, "upstream absorveu")
    saida = _aplicar(tmp_path, repo, fixado, atualizando=True)
    assert "OK: pulado" in saida
    assert _git(repo, "status", "--porcelain") == ""   # nada aplicado por cima


def test_atualizar_sem_patch_que_cabe_volta_ao_fixado(tmp_path: Path, repo: Path):
    fixado = _commit(repo, ORIGINAL, "fixado")
    novo = _commit(repo, MUDADO, "upstream mudou a função")
    _git(repo, "checkout", "-q", "--detach", novo)   # como o -Atualizar deixa o clone
    saida = _aplicar(tmp_path, repo, fixado, atualizando=True)
    assert "ERRO:" in saida and "VOLTOU" in saida, saida
    assert _git(repo, "rev-parse", "HEAD") == fixado
    assert _tem_patch(repo)


def test_sem_atualizar_patch_que_nao_cabe_falha_alto(tmp_path: Path, repo: Path):
    _commit(repo, ORIGINAL, "fixado")
    novo = _commit(repo, MUDADO, "mexido à mão")
    saida = _aplicar(tmp_path, repo, novo, atualizando=False)
    assert "ERRO:" in saida and "fixado" in saida, saida
    assert _git(repo, "rev-parse", "HEAD") == novo and not _tem_patch(repo)


@pytest.fixture(autouse=True)
def _harness_powershell(powershell_isolado):
    pass
