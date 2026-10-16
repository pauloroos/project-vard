"""Guarda compartilhada pelas suítes Python; instalada antes da coleta.

Não é uma sandbox do sistema: filhos permitidos devem usar somente dublês e tmp.
PowerShell exige a fixture powershell_isolado e um harness temporário revisado.
"""
import atexit
import shutil
import ipaddress
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile

import pytest

PORTAS_REAIS = {1234, 8000, 4700, 4710, 4720}
EXECUTAVEIS = {"claude", "codex", "agy", "gemini", "opencode", "ssh", "gh", "lms",
               "taskkill", "powershell", "pwsh", "reg", "wmic", "tasklist", "netstat", "nvidia-smi"}
_popen = subprocess.Popen
_run = subprocess.run
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_sendto = socket.socket.sendto
_getaddrinfo = socket.getaddrinfo
_real = False
_pasta_powershell = None


class AcessoAoPcReal(AssertionError):
    """Uma operação do teste escapou dos dublês."""


def verificar_destino(host, porta):
    if _real:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii")
    try:
        local = ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        local = str(host).lower().rstrip(".") == "localhost"
    if not local or int(porta or 0) in PORTAS_REAIS:
        raise AcessoAoPcReal("guarda do PC real: rede proibida; use transporte falso ou porta livre")


def _conectar(self, endereco):
    if isinstance(endereco, tuple):
        verificar_destino(*endereco[:2])
    return _connect(self, endereco)


def _conectar_ex(self, endereco):
    if isinstance(endereco, tuple):
        verificar_destino(*endereco[:2])
    return _connect_ex(self, endereco)


def _resolver(host, port, *args, **kwargs):
    if host is not None:
        verificar_destino(host, port)
    return _getaddrinfo(host, port, *args, **kwargs)


def _enviar(self, dados, *args):
    endereco = args[-1]
    if isinstance(endereco, tuple):
        verificar_destino(*endereco[:2])
    return _sendto(self, dados, *args)


def verificar_comando(args, kwargs):
    if _real:
        return
    partes = ([os.fspath(a) for a in args] if isinstance(args, (list, tuple))
              else shlex.split(str(args), posix=False))
    exe = Path(str(kwargs.get("executable") or partes[0]).strip('"')).name.lower()
    exe = exe.removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")
    if kwargs.get("shell"):
        raise AcessoAoPcReal("guarda do PC real: shell proibido; use argumentos explícitos")
    if exe not in EXECUTAVEIS:
        return
    if exe in {"powershell", "pwsh"} and _pasta_powershell:
        # Só executa o harness dentro do tmp deste teste; scripts do produto são dados.
        baixos = [p.lower() for p in partes]
        if "-file" in baixos:
            alvo = Path(partes[baixos.index("-file") + 1]).resolve()
            if alvo.is_relative_to(_pasta_powershell):
                return
    raise AcessoAoPcReal(f"guarda do PC real: subprocesso {exe} proibido; injete um dublê")


class PopenProtegido(_popen):
    def __init__(self, args, *a, **kw):
        verificar_comando(args, kw)
        super().__init__(args, *a, **kw)


def run_protegido(*a, **kw):
    verificar_comando(a[0] if a else kw["args"], kw)
    return _run(*a, **kw)


def instalar():
    socket.socket.connect = _conectar
    socket.socket.connect_ex = _conectar_ex
    socket.socket.sendto = _enviar
    socket.getaddrinfo = _resolver
    subprocess.Popen = PopenProtegido
    subprocess.run = run_protegido
    if "--pc-real" in sys.argv:
        return
    # Antes dos imports: nenhum módulo captura os diretórios reais do usuário.
    raiz = Path(tempfile.mkdtemp(prefix="vard-guarda-"))
    atexit.register(shutil.rmtree, raiz, ignore_errors=True)
    for nome in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE", "HOME", "VARD_CONFIG", "VARD_DADOS", "HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME"):
        os.environ[nome] = str(raiz / nome.lower())
    for nome in ("OPENJARVIS_HOME", "VARD_INSTALACAO", "VARD_REUNIAO_CONFIG"):
        os.environ.pop(nome, None)


def pytest_addoption(parser):
    parser.addoption("--pc-real", action="store_true", help="habilita somente provas marcadas pc_real")


def pytest_configure(config):
    config.addinivalue_line("markers", "pc_real: prova manual que acessa o PC; desabilitada por padrão")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--pc-real"):
        for item in items:
            if item.get_closest_marker("pc_real"):
                item.add_marker(pytest.mark.skip(reason="PC real: exige --pc-real explícito"))


@pytest.fixture(autouse=True)
def guarda_pc(request, tmp_path, monkeypatch):
    global _real
    _real = bool(request.node.get_closest_marker("pc_real") and request.config.getoption("--pc-real"))
    if not _real:
        for nome in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE", "HOME"):
            monkeypatch.setenv(nome, str(tmp_path / nome.lower()))
    yield
    _real = False


@pytest.fixture
def powershell_isolado(tmp_path):
    """Libera apenas harnesses do tmp; não libera scripts/windows nem -Command."""
    global _pasta_powershell
    _pasta_powershell = tmp_path.resolve()
    yield
    _pasta_powershell = None
