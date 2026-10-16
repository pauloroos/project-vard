"""Testes do runtime montado (T2): valida o bundle Python 3.13 + vard fora do repo."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
REPO_RAIZ = RAIZ.parent
SCRIPT_MONTAR = REPO_RAIZ / "scripts" / "windows" / "montar-nucleo.ps1"
BUILD_NUCLEO = REPO_RAIZ / "build" / "nucleo"
BUILD_CACHE = REPO_RAIZ / "build" / "cache"
PYTHON_EMBUTIDO = BUILD_NUCLEO / "python" / "python.exe"


def _rodar_script(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Executa montar-nucleo.ps1 com os argumentos fornecidos."""
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(SCRIPT_MONTAR), *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="module")
def python_embutido() -> Path:
    """Caminho do python.exe montado em build/nucleo/python/.

    Pula se o bundle não existir (montagem é passo de build, não de pytest comum).
    """
    if not PYTHON_EMBUTIDO.exists():
        pytest.skip(f"runtime não montado: {PYTHON_EMBUTIDO} ausente (rode npm run nucleo)")
    return PYTHON_EMBUTIDO


@pytest.mark.pc_real
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


@pytest.mark.pc_real
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


@pytest.mark.pc_real
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
    """Script falha com hash errado no toml e NAO extrai o destino."""
    toml_original = RAIZ / "runtime.toml"
    if not toml_original.exists():
        pytest.skip("runtime.toml não encontrado")

    # Cache e destino devem estar dentro de build/ para passar na validação de caminho
    cache_dir = BUILD_CACHE / "teste-hash"
    destino = BUILD_NUCLEO / "teste-hash"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)

        conteudo_toml = toml_original.read_text(encoding="utf-8")
        m_url = re.search(r'url = "(.+)"', conteudo_toml)
        assert m_url, "url não encontrada no runtime.toml"
        url = m_url.group(1)
        nome_arquivo = url.split("/")[-1]

        arquivo_falso = cache_dir / nome_arquivo
        arquivo_falso.write_bytes(b"conteudo-falso-para-hash-errado")

        toml_teste = tmp_path / "runtime.toml"
        toml_teste.write_text(conteudo_toml, encoding="utf-8")

        r = _rodar_script(
            "-Toml", str(toml_teste),
            "-Cache", str(cache_dir),
            "-Destino", str(destino),
        )
        assert r.returncode != 0, \
            f"script deveria falhar com hash errado, mas saiu 0. stdout={r.stdout}"
        assert "sha256" in r.stderr.lower() or "sha256" in r.stdout.lower(), \
            f"mensagem de erro deve mencionar sha256. stderr={r.stderr}, stdout={r.stdout}"
        assert not destino.exists(), "destino NÃO deve ser criado quando hash falha"
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
        shutil.rmtree(destino, ignore_errors=True)


def test_destino_fora_do_build_e_recusado(tmp_path: Path):
    """Script recusa destino fora de build/nucleo e NADA é apagado."""
    toml_original = RAIZ / "runtime.toml"
    if not toml_original.exists():
        pytest.skip("runtime.toml não encontrado")

    destino_proibido = tmp_path / "fora-do-build"
    destino_proibido.mkdir()
    sentinela = destino_proibido / "sentinela.txt"
    sentinela.write_text("nao-apagar", encoding="utf-8")

    # Cache dentro de build/cache para passar na validação; destino é que deve ser recusado
    cache_dir = BUILD_CACHE / "teste-fora"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        r = _rodar_script(
            "-Toml", str(toml_original),
            "-Cache", str(cache_dir),
            "-Destino", str(destino_proibido),
            "-SoVerificar",
        )
        assert r.returncode != 0, \
            f"script deveria recusar destino fora de build/nucleo. stdout={r.stdout}"
        assert "recusado" in r.stderr.lower() or "recusado" in r.stdout.lower() or \
               "dentro" in r.stderr.lower() or "dentro" in r.stdout.lower(), \
            f"mensagem deve indicar recusa de caminho. stderr={r.stderr}, stdout={r.stdout}"
        assert sentinela.exists(), "arquivo-sentinela deve sobreviver (nada pode ser apagado)"
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def test_segredo_no_destino_falha(tmp_path: Path):
    """Segredo plantado no destino faz o script falhar com mensagem clara."""
    toml_original = RAIZ / "runtime.toml"
    if not toml_original.exists():
        pytest.skip("runtime.toml não encontrado")

    destino_valido = BUILD_NUCLEO / "teste-segredo"
    cache_dir = BUILD_CACHE / "teste-segredo"
    try:
        destino_valido.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        segredo = destino_valido / "segredos.toml"
        segredo.write_text("[fake]\nchave = 'valor'\n", encoding="utf-8")

        r = _rodar_script(
            "-Toml", str(toml_original),
            "-Cache", str(cache_dir),
            "-Destino", str(destino_valido),
            "-SoVerificar",
        )
        assert r.returncode != 0, \
            f"script deveria falhar ao encontrar segredos.toml. stdout={r.stdout}"
        assert "proibido" in r.stderr.lower() or "proibido" in r.stdout.lower() or \
               "segredos" in r.stderr.lower() or "segredos" in r.stdout.lower(), \
            f"mensagem deve mencionar arquivos proibidos. stderr={r.stderr}, stdout={r.stdout}"
    finally:
        shutil.rmtree(destino_valido, ignore_errors=True)
        shutil.rmtree(cache_dir, ignore_errors=True)


@pytest.mark.pc_real
def test_caminho_com_espacos_e_somente_leitura_funciona(python_embutido: Path, tmp_path: Path):
    """Bundle copiado para pasta com espacos e somente leitura funciona sem __pycache__."""
    destino_espacos = tmp_path / "pasta com espacos" / "nucleo"
    origem = python_embutido.parent  # build/nucleo/python/
    shutil.copytree(str(origem), str(destino_espacos))

    # Remove qualquer __pycache__ pre-existente na copia
    for pc in destino_espacos.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)

    # Marca somente leitura recursivo
    subprocess.run(
        ["attrib", "+R", str(destino_espacos / "*"), "/S", "/D"],
        capture_output=True, timeout=30,
    )

    py_espacos = destino_espacos / "python.exe"
    assert py_espacos.exists(), "python.exe deve existir na copia"

    env_no_bytecode = os.environ.copy()
    env_no_bytecode["PYTHONDONTWRITEBYTECODE"] = "1"

    r = subprocess.run(
        [str(py_espacos), "-I", "-B", "-X", "utf8", "-m", "vard", "--versao"],
        capture_output=True,
        text=True,
        timeout=15,
        env=env_no_bytecode,
    )
    assert r.returncode == 0, f"vard --versao falhou em caminho so-leitura: {r.stderr}"
    assert r.stdout.strip(), "saida de versao nao pode ser vazia"

    r2 = subprocess.run(
        [str(py_espacos), "-I", "-B", "-c", "import vard.server; print('OK')"],
        capture_output=True,
        text=True,
        timeout=15,
        env=env_no_bytecode,
    )
    assert r2.returncode == 0, f"import vard.server falhou: {r2.stderr}"
    assert "OK" in r2.stdout

    pycaches = list(destino_espacos.rglob("__pycache__"))
    assert not pycaches, f"__pycache__ nao deve ser criado em pasta so-leitura: {pycaches}"


@pytest.mark.pc_real
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


@pytest.mark.pc_real
def test_bundle_nao_contem_segredos_ou_perfil(python_embutido: Path):
    """Presença acidental de segredos/perfil/config no bundle interrompe a montagem."""
    base = python_embutido.parent / "Lib" / "site-packages" / "vard"
    # Lista alinhada com Validar-Segredos-No-Destino do script montar-nucleo.ps1
    proibidos_exatos = ["segredos.toml", "perfil.json", "hud.config.json", "paineis.json"]
    encontrados = [f for f in proibidos_exatos if (base / f).exists()]
    personas = list(base.glob("persona*.md"))
    envs = list(python_embutido.parent.rglob("*.env"))
    assert not encontrados, f"arquivos proibidos encontrados no bundle: {encontrados}"
    assert not personas, f"arquivos persona*.md encontrados no bundle: {personas}"
    assert not envs, f"arquivos .env encontrados no bundle: {envs}"

@pytest.fixture(autouse=True)
def montagem_temporaria(tmp_path, monkeypatch, powershell_isolado, request):
    """Mantém o contrato build/ do script, inteiramente dentro de tmp."""
    if request.node.get_closest_marker("pc_real"):
        return
    raiz = tmp_path / "repo"
    scripts = raiz / "scripts" / "windows"
    scripts.mkdir(parents=True)
    copia = scripts / SCRIPT_MONTAR.name
    shutil.copyfile(SCRIPT_MONTAR, copia)
    monkeypatch.setattr(sys.modules[__name__], "SCRIPT_MONTAR", copia)
    monkeypatch.setattr(sys.modules[__name__], "BUILD_NUCLEO", raiz / "build" / "nucleo")
    monkeypatch.setattr(sys.modules[__name__], "BUILD_CACHE", raiz / "build" / "cache")
