"""Provas negativas: nenhuma chamada proibida chega ao sistema operacional."""
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from guarda_pc import AcessoAoPcReal, PORTAS_REAIS


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
@pytest.mark.parametrize("porta", sorted(PORTAS_REAIS))
def test_socket_recusa_servicos_reais(host, porta):
    with socket.socket() as s, pytest.raises(AcessoAoPcReal, match="rede proibida"):
        s.connect_ex((host, porta))


@pytest.mark.parametrize("host", ["exemplo.com", "192.0.2.1", "0.0.0.0"])
def test_recusa_rede_externa_antes_do_dns(host):
    with pytest.raises(AcessoAoPcReal):
        socket.getaddrinfo(host, 443)


@pytest.mark.parametrize("metodo", [httpx.get, httpx.post])
def test_httpx_recusa_porta_real(metodo):
    with pytest.raises(AcessoAoPcReal, match="guarda do PC real"):
        metodo("http://127.0.0.1:1234/v1/models", trust_env=False)


@pytest.mark.parametrize("exe", ["claude", "codex", "agy", "gemini", "opencode", "ssh", "gh", "lms",
                                 "powershell", "pwsh", "taskkill.exe"])
@pytest.mark.parametrize("rodar", [subprocess.run, subprocess.Popen])
def test_recusa_subprocessos_reais(exe, rodar):
    with pytest.raises(AcessoAoPcReal, match="subprocesso .* proibido"):
        rodar([exe, "--version"])


@pytest.mark.parametrize("comando", ["codex --version", '"powershell.exe" -NoProfile'])
def test_recusa_subprocesso_em_string(comando):
    with pytest.raises(AcessoAoPcReal):
        subprocess.run(comando)


def test_recusa_executavel_sobreposto():
    with pytest.raises(AcessoAoPcReal):
        subprocess.Popen(["inofensivo"], executable="ssh.exe")


def test_recusa_powershell_fora_do_harness(powershell_isolado):
    with pytest.raises(AcessoAoPcReal):
        subprocess.run(["powershell", "-File", "scripts/windows/vard-modo.ps1", "jogo"])


def test_servidor_falso_em_porta_livre_continua_funcionando():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"duble")

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as servidor:
        thread = threading.Thread(target=servidor.serve_forever)
        thread.start()
        try:
            resposta = httpx.get(f"http://127.0.0.1:{servidor.server_port}", trust_env=False)
            assert resposta.status_code == 200 and resposta.text == "duble"
        finally:
            servidor.shutdown()
            thread.join(timeout=5)
        assert not thread.is_alive()
