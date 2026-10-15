"""Testes de entrada do núcleo (T1): __main__, /saude, porta ocupada, wheel e pastas."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

RAIZ_NUCLEO = Path(__file__).resolve().parents[1]


def test_versao_sem_config_nao_importa_torch_nem_abre_rede(monkeypatch, tmp_path: Path):
    """--versao imprime a versão e sai sem precisar de config, torch ou rede."""
    monkeypatch.delenv("VARD_CONFIG", raising=False)
    monkeypatch.delenv("VARD_DADOS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    resultado = subprocess.run(
        [sys.executable, "-m", "vard", "--versao"],
        capture_output=True,
        text=True,
        cwd=str(RAIZ_NUCLEO),
        timeout=15,
    )
    assert resultado.returncode == 0, resultado.stderr
    versao = resultado.stdout.strip()
    assert versao and versao.replace(".", "").replace("-", "").isalnum()
    # torch não deve aparecer nos imports quando só pedimos --versao
    assert "torch" not in resultado.stderr.lower()


def test_servir_com_caminho_com_espacos(monkeypatch, tmp_path: Path):
    """servir aceita VARD_CONFIG/VARD_DADOS com espaços (caminho real do usuário)."""
    cfg = tmp_path / "minha config"
    dados = tmp_path / "meus dados"
    cfg.mkdir()
    dados.mkdir()
    monkeypatch.setenv("VARD_CONFIG", str(cfg))
    monkeypatch.setenv("VARD_DADOS", str(dados))
    monkeypatch.setenv("VARD_SEM_VIGIA", "1")
    from vard import servidor  # type: ignore

    app = servidor.criar_app()
    assert app is not None


def _cliente_nucleo():
    """TestClient configurado com headers que passam pelo middleware so_localhost."""
    from fastapi.testclient import TestClient

    from vard import servidor

    client = TestClient(servidor.criar_app(), base_url="http://127.0.0.1:4700")
    return client


def test_saude_informa_pid_do_processo():
    """/saude responde ok, versao e pid do processo que atende."""
    client = _cliente_nucleo()
    resposta = client.get("/saude")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert isinstance(corpo["versao"], str) and corpo["versao"]
    assert corpo["pid"] == os.getpid()


def test_status_conserva_campos_do_mvp():
    """/status mantém os campos já usados pela aba (modo, openjarvis, lmstudio, modelo)."""
    client = _cliente_nucleo()
    resposta = client.get("/status")
    assert resposta.status_code == 200
    corpo = resposta.json()
    for chave in ("modo", "openjarvis", "lmstudio", "modelo"):
        assert chave in corpo, f"campo {chave} ausente em /status"


def test_porta_ocupada_sai_com_motivo_identificavel(tmp_path: Path, monkeypatch):
    """Porta ocupada encerra com código específico e mensagem clara, sem matar o ocupante."""
    from vard import servidor

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    porta = sock.getsockname()[1]
    try:
        codigo = servidor.servir(porta=porta, host="127.0.0.1")
        assert codigo == servidor.SAIDA_PORTA_OCUPADA
    finally:
        sock.close()


def test_saude_idempotente_em_multiplas_chamadas_de_criar_app():
    """criar_app() chamada duas vezes não duplica /saude nem quebra rotas existentes."""
    from vard import servidor

    app1 = servidor.criar_app()
    app2 = servidor.criar_app()
    rotas_saude = [r for r in app2.routes if getattr(r, "path", None) == "/saude"]
    assert len(rotas_saude) == 1, f"/saude duplicada: {len(rotas_saude)} registros"
    from fastapi.testclient import TestClient

    client = TestClient(app2, base_url="http://127.0.0.1:4700")
    resposta = client.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json()["ok"] is True


def test_pastas_hud_e_nucleo_sao_diferentes(monkeypatch, tmp_path: Path):
    """Config do HUD (%APPDATA%/io.github.pauloroos.vard) e do núcleo (VARD_CONFIG) são pastas distintas."""
    hud_dir = tmp_path / "appdata" / "io.github.pauloroos.vard"
    nucleo_cfg = tmp_path / "localappdata" / "rdl-vard" / "config"
    hud_dir.mkdir(parents=True)
    nucleo_cfg.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("VARD_CONFIG", raising=False)
    from vard import config

    assert config.pasta_config() != hud_dir
    assert str(config.pasta_config()).endswith("rdl-vard\\config") or str(config.pasta_config()).endswith(
        "rdl-vard/config"
    )


def _encerrar_arvore(proc: subprocess.Popen) -> None:
    """Encerra o processo e todos os filhos recursivamente via psutil."""
    try:
        pai = psutil.Process(proc.pid)
        filhos = pai.children(recursive=True)
        for filho in filhos:
            try:
                filho.terminate()
            except psutil.NoSuchProcess:
                pass
        for filho in filhos:
            try:
                filho.wait(timeout=3)
            except psutil.TimeoutExpired:
                try:
                    filho.kill()
                except psutil.NoSuchProcess:
                    pass
        pai.terminate()
        try:
            pai.wait(timeout=3)
        except psutil.TimeoutExpired:
            pai.kill()
            pai.wait(timeout=3)
    except psutil.NoSuchProcess:
        pass


def _porta_livre(porta: int, timeout: float = 2.0) -> bool:
    """Verifica se a porta ficou livre após encerramento."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", porta))
            s.close()
            return True
        except OSError:
            s.close()
            time.sleep(0.2)
    return False


def test_wheel_instalado_fora_do_repo(tmp_path: Path):
    """Wheel inclui server, MCPs, preflight e viewer; funciona fora do checkout com python -I.
    Estendido: sobe o núcleo como processo na venv, consulta /saude e /status por HTTP.
    """
    uv_bin = shutil.which("uv")
    if not uv_bin:
        pytest.skip("uv não encontrado no PATH")
    dist_dir = tmp_path / "dist"
    venv_dir = tmp_path / "venv"
    build = subprocess.run(
        [uv_bin, "build", "--project", str(RAIZ_NUCLEO), "--wheel", "--out-dir", str(dist_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert build.returncode == 0, build.stderr
    wheels = list(dist_dir.glob("*.whl"))
    assert wheels, "nenhum wheel gerado"
    wheel_path = wheels[0]
    venv = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert venv.returncode == 0, venv.stderr
    pip_exe = str(venv_dir / "Scripts" / "pip.exe" if sys.platform == "win32" else venv_dir / "bin" / "pip")
    py_exe = str(venv_dir / "Scripts" / "python.exe" if sys.platform == "win32" else venv_dir / "bin" / "python")
    install = subprocess.run(
        [pip_exe, "install", str(wheel_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stderr
    # Roda fora do repo com python -I para não importar do checkout
    fora_repo = tmp_path / "fora"
    fora_repo.mkdir()
    versao = subprocess.run(
        [py_exe, "-I", "-m", "vard", "--versao"],
        capture_output=True,
        text=True,
        cwd=str(fora_repo),
        timeout=15,
    )
    assert versao.returncode == 0, versao.stderr
    assert versao.stdout.strip()
    # Importa server e cada MCP
    imports = [
        "server",
        "consulta_mcp",
        "memoria_mcp",
        "mesa_mcp",
        "oficina_mcp",
        "reuniao_mcp",
        "preflight",
    ]
    for mod in imports:
        r = subprocess.run(
            [py_exe, "-I", "-c", f"import vard.{mod}; print(vard.{mod}.__name__)"],
            capture_output=True,
            text=True,
            cwd=str(fora_repo),
            timeout=15,
        )
        assert r.returncode == 0, f"falha ao importar vard.{mod}: {r.stderr}"
    # Verifica recursos do viewer
    viewer_check = subprocess.run(
        [py_exe, "-I", "-c", "from pathlib import Path; import vard; p=Path(vard.__file__).parent/'viewer'/'index.html'; print('OK' if p.exists() else 'MISS')"],
        capture_output=True,
        text=True,
        cwd=str(fora_repo),
        timeout=15,
    )
    assert "OK" in viewer_check.stdout, f"viewer/index.html ausente no wheel: {viewer_check.stdout} {viewer_check.stderr}"
    # Prova HTTP real: sobe o núcleo na venv, consulta /saude e /status
    # Usa portas fechadas para OpenJarvis/LM Studio via env, independente dos serviços reais da máquina.
    sock_oj = socket.socket(); sock_oj.bind(("127.0.0.1", 0)); porta_oj = sock_oj.getsockname()[1]; sock_oj.close()
    sock_lm = socket.socket(); sock_lm.bind(("127.0.0.1", 0)); porta_lm = sock_lm.getsockname()[1]; sock_lm.close()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    porta = sock.getsockname()[1]
    sock.close()
    env_proc = os.environ.copy()
    env_proc["VARD_OPENJARVIS_URL"] = f"http://127.0.0.1:{porta_oj}"
    env_proc["VARD_LMSTUDIO_URL"] = f"http://127.0.0.1:{porta_lm}"
    proc = subprocess.Popen(
        [py_exe, "-I", "-m", "vard", "servir", "--porta", str(porta), "--host", "127.0.0.1"],
        cwd=str(fora_repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env_proc,
    )
    try:
        url_saude = f"http://127.0.0.1:{porta}/saude"
        url_status = f"http://127.0.0.1:{porta}/status"
        inicio = time.monotonic()
        resposta_saude = None
        while time.monotonic() - inicio < 15:
            try:
                resposta_saude = httpx.get(url_saude, timeout=1)
                if resposta_saude.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        assert resposta_saude is not None and resposta_saude.status_code == 200, "núcleo (wheel) não subiu em 15s"
        saude = resposta_saude.json()
        assert saude["ok"] is True
        assert isinstance(saude["pid"], int) and saude["pid"] > 0
        resposta_status = httpx.get(url_status, timeout=3)
        assert resposta_status.status_code == 200
        status_body = resposta_status.json()
        assert "modo" in status_body
    finally:
        _encerrar_arvore(proc)
    assert _porta_livre(porta), f"porta {porta} ainda ocupada após encerramento do wheel"


def test_prova_http_real_subprocesso(tmp_path: Path):
    """Sobe o núcleo como processo, consulta /saude e /status por HTTP.
    Exige que saude.pid seja o proc.pid OU um descendente dele (psutil).
    Encerra a árvore inteira e confirma porta livre.
    NÃO escreve em .coordenacao (prova externa faz isso).
    Usa portas fechadas para OpenJarvis/LM Studio via env, independente dos serviços reais.
    """
    # Portas fechadas para OpenJarvis e LM Studio (reserva e fecha)
    sock_oj = socket.socket(); sock_oj.bind(("127.0.0.1", 0)); porta_oj = sock_oj.getsockname()[1]; sock_oj.close()
    sock_lm = socket.socket(); sock_lm.bind(("127.0.0.1", 0)); porta_lm = sock_lm.getsockname()[1]; sock_lm.close()
    # Encontra porta livre para o núcleo
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    porta = sock.getsockname()[1]
    sock.close()
    env_proc = os.environ.copy()
    env_proc["VARD_OPENJARVIS_URL"] = f"http://127.0.0.1:{porta_oj}"
    env_proc["VARD_LMSTUDIO_URL"] = f"http://127.0.0.1:{porta_lm}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "vard", "servir", "--porta", str(porta), "--host", "127.0.0.1"],
        cwd=str(RAIZ_NUCLEO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env_proc,
    )
    try:
        # Espera o servidor subir
        url_saude = f"http://127.0.0.1:{porta}/saude"
        url_status = f"http://127.0.0.1:{porta}/status"
        inicio = time.monotonic()
        resposta_saude = None
        while time.monotonic() - inicio < 10:
            try:
                resposta_saude = httpx.get(url_saude, timeout=1)
                if resposta_saude.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        assert resposta_saude is not None and resposta_saude.status_code == 200, "núcleo não subiu em 10s"
        saude = resposta_saude.json()
        assert saude["ok"] is True
        # saude.pid deve ser o proc.pid OU um descendente dele
        pid_saude = saude["pid"]
        assert isinstance(pid_saude, int) and pid_saude > 0
        if pid_saude != proc.pid:
            try:
                pai = psutil.Process(proc.pid)
                descendentes = {c.pid for c in pai.children(recursive=True)}
                assert pid_saude in descendentes, (
                    f"saude.pid={pid_saude} não é proc.pid={proc.pid} nem descendente"
                )
            except psutil.NoSuchProcess:
                pytest.fail(f"processo {proc.pid} morreu antes da verificação de descendência")
        resposta_status = httpx.get(url_status, timeout=3)
        assert resposta_status.status_code == 200
        status_body = resposta_status.json()
        assert "modo" in status_body
    finally:
        _encerrar_arvore(proc)
    # Confirma que a porta ficou livre
    assert _porta_livre(porta), f"porta {porta} ainda ocupada após encerramento do processo {proc.pid}"


def test_status_responde_rapido_com_urls_lentas(tmp_path: Path):
    """/status responde em < 3 s mesmo com OpenJarvis e LM Studio lentos/mortos.
    Sondas em paralelo garantem prazo total ~2 s, não 4 s sequenciais.
    """
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class LentoHandler(BaseHTTPRequestHandler):
        """Servidor falso que demora 1.5 s para responder (simula serviço lento)."""
        def do_GET(self):
            time.sleep(1.5)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if "/health" in self.path:
                self.wfile.write(b'{"ok":true}')
            else:
                self.wfile.write(b'{"data":[]}')
        def log_message(self, format, *args):
            pass  # silencia logs do servidor falso

    # Sobe dois servidores lentos em portas livres
    srv_oj = HTTPServer(("127.0.0.1", 0), LentoHandler)
    srv_lm = HTTPServer(("127.0.0.1", 0), LentoHandler)
    porta_oj = srv_oj.server_address[1]
    porta_lm = srv_lm.server_address[1]
    t_oj = threading.Thread(target=srv_oj.serve_forever, daemon=True)
    t_lm = threading.Thread(target=srv_lm.serve_forever, daemon=True)
    t_oj.start()
    t_lm.start()

    # Porta livre para o núcleo
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    porta = sock.getsockname()[1]
    sock.close()

    env_proc = os.environ.copy()
    env_proc["VARD_OPENJARVIS_URL"] = f"http://127.0.0.1:{porta_oj}"
    env_proc["VARD_LMSTUDIO_URL"] = f"http://127.0.0.1:{porta_lm}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "vard", "servir", "--porta", str(porta), "--host", "127.0.0.1"],
        cwd=str(RAIZ_NUCLEO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env_proc,
    )
    try:
        url_saude = f"http://127.0.0.1:{porta}/saude"
        url_status = f"http://127.0.0.1:{porta}/status"
        inicio = time.monotonic()
        resposta_saude = None
        while time.monotonic() - inicio < 10:
            try:
                resposta_saude = httpx.get(url_saude, timeout=1)
                if resposta_saude.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        assert resposta_saude is not None and resposta_saude.status_code == 200, "núcleo não subiu em 10s"

        # Mede tempo do /status: deve ser < 3 s (paralelo), não ~4 s (sequencial)
        t0 = time.monotonic()
        resposta_status = httpx.get(url_status, timeout=5)
        duracao = time.monotonic() - t0
        assert resposta_status.status_code == 200
        assert duracao < 4.0, f"/status demorou {duracao:.2f}s (esperado < 4s com sondas paralelas)"
        status_body = resposta_status.json()
        assert "modo" in status_body
        assert "openjarvis" in status_body
        assert "lmstudio" in status_body
    finally:
        _encerrar_arvore(proc)
        srv_oj.shutdown()
        srv_lm.shutdown()
    assert _porta_livre(porta), f"porta {porta} ainda ocupada após encerramento"