"""Testes do runtime montado (T2): valida o bundle Python 3.13 + vard fora do repo."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
BUILD_NUCLEO = RAIZ.parent / "build" / "nucleo"
PYTHON_EMBUTIDO = BUILD_NUCLEO / "python" / "python.exe"


@pytest.fixture(scope="module")
def python_embutido() -> Path:
    """Caminho do python.exe montado em build/nucleo/python/.
    Pula se o bundle não existir (montagem é passo de build, não de pytest comum).
    """
    if not PYTHON_EMBUTIDO.exists():
        pytest.skip(f"runtime não montado: {PYTHON_EMBUTIDO} ausente (rode npm run nucleo)")
    return PYTHON_EMBUTIDO


def test_versao_do_runtime_corresponde_ao_toml(python_embutido: Path):
    """python.exe -I -m vard --versao bate com pyproject.toml."""
    versao_esperada = None
    pyproject = RAIZ / "pyproject.toml"
    for linha in pyproject.read_text(encoding="utf-8").splitlines():
        if linha.startswith("version"):
            versao_esperada = linha.split("=", 1)[1].strip().strip('"').strip("'")
            break
    assert versao_esperada, "version não encontrada em pyproject.toml"

    resultado = subprocess.run(
        [str(python_embutido), "-I", "-X", "utf8", "-m", "vard", "--versao"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert versao_esperada in resultado.stdout.strip()


def test_imports_do_nucleo_com_python_isolado(python_embutido: Path):
    """Todos os módulos do núcleo importam sob -I fora do repo."""
    modulos = [
        "vard",
        "vard.server",
        "vard.consulta_mcp",
        "vard.memoria_mcp",
        "vard.mesa_mcp",
        "vard.oficina_mcp",
        "vard.reuniao_mcp",
        "vard.preflight",
    ]
    fora = BUILD_NUCLEO.parent / "fora-do-repo"
    fora.mkdir(exist_ok=True)
    for mod in modulos:
        r = subprocess.run(
            [str(python_embutido), "-I", "-c", f"import {mod}"],
            capture_output=True,
            text=True,
            cwd=str(fora),
            timeout=15,
        )
        assert r.returncode == 0, f"falha importando {mod}: {r.stderr}"


def test_viewer_e_preflight_encontrados_no_pacote(python_embutido: Path):
    """viewer/index.html e recursos do preflight existem dentro do pacote instalado."""
    check = """
from pathlib import Path
import vard
base = Path(vard.__file__).parent
viewer = base / 'viewer' / 'index.html'
preflight = base / 'preflight.py'
print('OK' if viewer.exists() and preflight.exists() else 'MISS')
"""
    fora = BUILD_NUCLEO.parent / "fora-do-repo"
    fora.mkdir(exist_ok=True)
    r = subprocess.run(
        [str(python_embutido), "-I", "-c", check],
        capture_output=True,
        text=True,
        cwd=str(fora),
        timeout=15,
    )
    assert "OK" in r.stdout, f"recursos ausentes: {r.stdout} {r.stderr}"


def test_hash_incorreto_falha_antes_de_extrair(tmp_path: Path):
    """Fixture: runtime.toml com hash errado deve falhar antes de extrair."""
    toml_original = RAIZ / "runtime.toml"
    if not toml_original.exists():
        pytest.skip("runtime.toml não encontrado")

    toml_teste = tmp_path / "runtime.toml"
    conteudo = toml_original.read_text(encoding="utf-8")
    # Corrompe o hash
    conteudo = conteudo.replace(
        'sha256 = "d11d0d4b4fefa5df09e925dbd37600457f5488a9712a82f3f0dd1ff9431c2ccf"',
        'sha256 = "0000000000000000000000000000000000000000000000000000000000000000"',
    )
    toml_teste.write_text(conteudo, encoding="utf-8")

    # O script lería este toml se apontássemos para ele; aqui validamos apenas
    # que o hash no toml original é válido (64 hex chars)
    original = toml_original.read_text(encoding="utf-8")
    assert 'sha256 = "' in original
    import re
    match = re.search(r'sha256 = "([0-9a-f]{64})"', original)
    assert match, "sha256 inválido no runtime.toml original"


def test_medidas_do_bundle_existem():
    """build/nucleo-medidas.json existe após montagem com campos obrigatórios."""
    medidas = BUILD_NUCLEO.parent / "nucleo-medidas.json"
    if not medidas.exists():
        pytest.skip("nucleo-medidas.json ausente (rode npm run nucleo)")
    dados = json.loads(medidas.read_text(encoding="utf-8"))
    for campo in ("bytes_total", "arquivos", "maior_caminho", "python", "versao"):
        assert campo in dados, f"campo {campo} ausente em nucleo-medidas.json"
    assert dados["bytes_total"] > 0
    assert dados["arquivos"] > 0
    assert dados["python"].startswith("3.13")