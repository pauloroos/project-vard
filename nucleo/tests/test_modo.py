import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from vard import modo

RAIZ = Path(__file__).resolve().parent.parent


def test_ler_estado_sem_arquivo_e_desconhecido(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(modo, "ARQUIVO_ESTADO", tmp_path / "estado.json")
    assert modo.ler_estado()["modo"] == "desconhecido"


def test_ler_estado_le_json(tmp_path: Path, monkeypatch):
    arq = tmp_path / "estado.json"
    arq.write_text(json.dumps({"modo": "jogo", "desde": "2026-10-12T20:00:00", "detalhe": "GPU livre"}), encoding="utf-8")
    monkeypatch.setattr(modo, "ARQUIVO_ESTADO", arq)
    e = modo.ler_estado()
    assert e["modo"] == "jogo" and e["detalhe"] == "GPU livre"


def test_ler_estado_json_quebrado_vira_desconhecido(tmp_path: Path, monkeypatch):
    arq = tmp_path / "estado.json"
    arq.write_text("{quebrado", encoding="utf-8")
    monkeypatch.setattr(modo, "ARQUIVO_ESTADO", arq)
    assert modo.ler_estado()["modo"] == "desconhecido"


def test_disparar_recusa_verbo_desconhecido():
    with pytest.raises(ValueError):
        modo.disparar("explodir")


def _decodificar(args: list[str]) -> str:
    return base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16-le")


def test_disparar_lanca_intermediario_sem_janela(monkeypatch, tmp_path: Path):
    chamadas = []

    class _P:
        pid = 4242

    def _popen(args, **kw):
        chamadas.append((args, kw))
        return _P()

    monkeypatch.setattr(modo.subprocess, "Popen", _popen)
    script = tmp_path / "vard-modo.ps1"
    script.write_text("", encoding="utf-8")
    pid = modo.disparar("jogo", script=script)
    assert pid == 4242
    args, kw = chamadas[0]
    assert args[0] == "powershell" and "-NonInteractive" in args
    texto = _decodificar(args)
    assert texto.startswith("Start-Process -FilePath powershell")
    assert f"'\"{script}\"'" in texto and "'jogo'" in texto and "'-File'" in texto
    # DETACHED_PROCESS faz o powershell 5.1 sair com 0 sem rodar nada: proibido.
    assert not kw["creationflags"] & subprocess.DETACHED_PROCESS
    assert kw["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert kw["stdout"] is subprocess.DEVNULL and kw["stdin"] is subprocess.DEVNULL


def test_comando_intermediario_escapa_apostrofo_e_espaco():
    texto = modo.comando_intermediario(Path("X:/Programas DEV/d'Ávila/vard-modo.ps1"), "voltar")
    assert "d''Ávila" in texto and "Programas DEV" in texto and texto.endswith("-WindowStyle Hidden")


def test_sonda_e_aba_sao_verbos():
    assert "sonda" in modo.VERBOS and "aba" in modo.VERBOS


# ---------------------------------------------------------------- integração (só Windows)
STUB = """param([string]$Verbo)
Set-Content -Path (Join-Path $PSScriptRoot 'comecou.txt') -Value $Verbo -Encoding ascii
Start-Sleep -Seconds {espera}
Set-Content -Path (Join-Path $PSScriptRoot 'marcador.txt') -Value $Verbo -Encoding ascii
"""


def _stub(pasta: Path, espera: int = 0) -> Path:
    s = pasta / "stub.ps1"
    s.write_text(STUB.replace("{espera}", str(espera)), encoding="utf-8")
    return s


def _esperar_arquivo(arq: Path, segundos: float = 10) -> str | None:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if arq.exists():
            try:
                return arq.read_text(encoding="ascii").strip()
            except OSError:
                pass
        time.sleep(0.2)
    return None


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
@pytest.mark.pc_real
def test_disparar_roda_o_script(tmp_path: Path):
    modo.disparar("jogo", script=_stub(tmp_path))
    assert _esperar_arquivo(tmp_path / "marcador.txt") == "jogo"


@pytest.mark.skipif(sys.platform != "win32", reason="só Windows")
@pytest.mark.pc_real
def test_disparar_sobrevive_ao_taskkill_do_pai(tmp_path: Path):
    # Simula a ponte/bandeja: um python que dispara e depois leva taskkill /T /F na árvore
    # (é o que o vard-modo.ps1 faz com a ponte no jogo e com a bandeja no parar).
    stub = _stub(tmp_path, espera=5)
    codigo = (
        "import sys, time; from pathlib import Path; from vard import modo; "
        f"print(modo.disparar('jogo', script=Path(r'{stub}')), flush=True); time.sleep(60)"
    )
    pai = subprocess.Popen([sys.executable, "-c", codigo], cwd=str(RAIZ), stdout=subprocess.PIPE, text=True)
    try:
        intermediario = int(pai.stdout.readline().strip())
        assert _esperar_arquivo(tmp_path / "comecou.txt") == "jogo", "o script não começou"
        fim = time.monotonic() + 10   # o intermediário sai logo depois do Start-Process
        while psutil.pid_exists(intermediario) and time.monotonic() < fim:
            time.sleep(0.2)
        subprocess.run(["taskkill", "/PID", str(pai.pid), "/T", "/F"], capture_output=True, check=False)
        pai.wait(timeout=10)
    finally:
        if pai.poll() is None:
            pai.kill()
        pai.stdout.close()
    assert not (tmp_path / "marcador.txt").exists(), "o stub deveria ainda estar no Start-Sleep"
    assert _esperar_arquivo(tmp_path / "marcador.txt") == "jogo", "o taskkill do pai matou o script"


# ---------------------------------------------------------------- endpoint /modo (HTTP)
from fastapi.testclient import TestClient

import server


@pytest.fixture
def cliente_modo(monkeypatch, tmp_path):
    server.HISTORICO.clear()
    monkeypatch.setattr(server, "_reuniao_ativa", lambda: False)
    from vard import central
    monkeypatch.setattr(central, "ARQUIVO", tmp_path / "avisos.jsonl")
    return TestClient(server.app, base_url="http://127.0.0.1:4700")


def test_modo_jogo_retorna_erro_claro(cliente_modo, monkeypatch):
    from vard import modo
    chamados = []
    monkeypatch.setattr(modo, "disparar", lambda verbo: chamados.append(verbo) or 1)
    r = cliente_modo.post("/modo", json={"modo": "jogo"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code in (503, 400)
    assert "indispon" in r.text


def test_modo_voltar_retorna_sucesso_imediato(cliente_modo, monkeypatch):
    from vard import modo
    chamados = []
    monkeypatch.setattr(modo, "disparar", lambda verbo: chamados.append(verbo) or 1)
    r = cliente_modo.post("/modo", json={"modo": "voltar"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_modo_desconhecido_retorna_erro(cliente_modo):
    r = cliente_modo.post("/modo", json={"modo": "xyz"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code == 400


# ---------------------------------------------------------------- endpoint /modo (HTTP)
from fastapi.testclient import TestClient

import server


@pytest.fixture
def cliente_modo(monkeypatch, tmp_path):
    server.HISTORICO.clear()
    monkeypatch.setattr(server, "_reuniao_ativa", lambda: False)
    from vard import central
    monkeypatch.setattr(central, "ARQUIVO", tmp_path / "avisos.jsonl")
    return TestClient(server.app, base_url="http://127.0.0.1:4700")


def test_modo_jogo_retorna_erro_claro(cliente_modo, monkeypatch):
    from vard import modo
    chamados = []
    monkeypatch.setattr(modo, "disparar", lambda verbo: chamados.append(verbo) or 1)
    r = cliente_modo.post("/modo", json={"modo": "jogo"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code in (503, 400)
    assert "indispon" in r.text


def test_modo_voltar_retorna_sucesso_imediato(cliente_modo, monkeypatch):
    from vard import modo
    chamados = []
    monkeypatch.setattr(modo, "disparar", lambda verbo: chamados.append(verbo) or 1)
    r = cliente_modo.post("/modo", json={"modo": "voltar"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_modo_desconhecido_retorna_erro(cliente_modo):
    r = cliente_modo.post("/modo", json={"modo": "xyz"}, headers={"Origin": "http://127.0.0.1:4700"})
    assert r.status_code == 400
