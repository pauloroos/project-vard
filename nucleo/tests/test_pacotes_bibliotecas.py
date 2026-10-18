"""Bibliotecas Python dos pacotes opcionais no ambiente do serviço de voz.

O instalador baixa e confere os arquivos e, antes de promover, instala as dependências que são requisitos
Python (não ids de pacote). Subprocesso simulado: nada é instalado de verdade.
"""
from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from vard.pacotes import InstaladorPacotes
from vard.pacotes import bibliotecas as bib
from vard.pacotes.manifesto import PacoteInfo

CONTEUDO = b"MODELO_FICTICIO_" * 64


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(CONTEUDO)))
        self.end_headers()
        self.wfile.write(CONTEUDO)


@pytest.fixture()
def porta():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _pacote(porta: int, deps: list[str]) -> PacoteInfo:
    return PacoteInfo(
        id="motor-ficticio", nome="Motor Fictício", versao="1.0.0", tipo="motor", descricao="",
        url=f"http://127.0.0.1:{porta}/modelo.onnx", sha256=hashlib.sha256(CONTEUDO).hexdigest(),
        bytes_download=len(CONTEUDO), bytes_instalado=len(CONTEUDO), python=">=3.10", backend="cpu",
        licenca_url="https://example.com/licenca", licenca_nome="Licença Fictícia", dependencias=deps,
    )


def _python_falso(tmp_path: Path) -> Path:
    py = tmp_path / "voz" / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    return py


# --- funções puras -------------------------------------------------------------------------------

def test_dependencias_python_ignoram_ids_de_pacote():
    assert bib.dependencias_python(["xtts-v2", "kokoro-onnx==0.6.1", " ", "torch>=2.11"], {"xtts-v2", "kokoro"}) == [
        "kokoro-onnx==0.6.1", "torch>=2.11"]


def test_python_da_voz_usa_voz_python_configurado(tmp_path):
    py = _python_falso(tmp_path)
    assert bib.python_da_voz({"raiz_codigo": "", "servicos": {"voz_python": str(py)}}) == py


def test_python_da_voz_cai_no_venv_da_raiz_do_codigo(tmp_path):
    py = _python_falso(tmp_path)
    assert bib.python_da_voz({"raiz_codigo": str(tmp_path), "servicos": {}}) == py


def test_python_da_voz_ausente_e_none(tmp_path):
    assert bib.python_da_voz({"raiz_codigo": str(tmp_path), "servicos": {}}) is None
    assert bib.python_da_voz({"raiz_codigo": "", "servicos": {}}) is None
    assert bib.python_da_voz({"raiz_codigo": "", "servicos": {"voz_python": str(tmp_path / "nao.exe")}}) is None


def test_comando_prefere_uv_e_cai_no_pip(tmp_path):
    py = tmp_path / "python.exe"
    assert bib.comando_instalacao(py, ["kokoro-onnx==0.6.1"], which=lambda n: "uv-ficticio" if n == "uv" else None) == [
        "uv-ficticio", "pip", "install", "--python", str(py), "kokoro-onnx==0.6.1"]
    assert bib.comando_instalacao(py, ["kokoro-onnx==0.6.1"], which=lambda n: None) == [
        str(py), "-m", "pip", "install", "kokoro-onnx==0.6.1"]


def test_erro_sem_caminho_da_maquina(tmp_path):
    py = _python_falso(tmp_path)
    erro = bib.instalar_bibliotecas(["kokoro-onnx==0.6.1"], py, executar=lambda c: (2, f"aviso\nfalhou em {py}\n"),
                                    which=lambda n: None)
    assert erro is not None and "kokoro-onnx==0.6.1" in erro and str(tmp_path) not in erro


def test_sem_python_da_voz_erro_claro_sem_executar():
    chamadas = []
    erro = bib.instalar_bibliotecas(["x==1"], None, executar=lambda c: chamadas.append(c) or (0, ""))
    assert erro and "servico de voz" in erro and chamadas == []


# --- instalador ----------------------------------------------------------------------------------

def _instalador(tmp_path, py, executar):
    return InstaladorPacotes(raiz_pacotes=tmp_path / "pacotes", python_voz=lambda: py,
                             executar_bibliotecas=executar, ids_pacotes=lambda: {"xtts-v2", "motor-ficticio"})


@pytest.mark.asyncio
async def test_instala_bibliotecas_no_python_da_voz_antes_de_concluir(tmp_path, porta, monkeypatch):
    monkeypatch.setattr(bib.shutil, "which", lambda n: None)
    py = _python_falso(tmp_path)
    comandos = []
    inst = _instalador(tmp_path, py, lambda c: comandos.append(c) or (0, ""))
    estados = []
    r = await inst.instalar(_pacote(porta, ["xtts-v2", "kokoro-onnx==0.6.1"]), on_progress=lambda p: estados.append(p.estado))
    await inst.fechar()
    assert r.estado == "concluido", r.erro
    assert comandos == [[str(py), "-m", "pip", "install", "kokoro-onnx==0.6.1"]]
    assert estados.index("bibliotecas") < estados.index("concluido")
    assert inst.esta_instalado("motor-ficticio")


@pytest.mark.asyncio
async def test_falha_das_bibliotecas_nao_instala_o_pacote(tmp_path, porta):
    py = _python_falso(tmp_path)
    inst = _instalador(tmp_path, py, lambda c: (1, "ERROR: No matching distribution found"))
    r = await inst.instalar(_pacote(porta, ["kokoro-onnx==0.6.1"]))
    await inst.fechar()
    assert r.estado == "falhou"
    assert "No matching distribution" in r.erro and "kokoro-onnx" in r.erro
    assert not inst.esta_instalado("motor-ficticio")
    assert not (tmp_path / "pacotes" / "ativo" / "motor-ficticio").exists()
    assert not (tmp_path / "pacotes" / "staging" / "motor-ficticio").exists()


@pytest.mark.asyncio
async def test_sem_dependencia_python_nao_chama_instalador(tmp_path, porta):
    comandos = []
    inst = _instalador(tmp_path, None, lambda c: comandos.append(c) or (0, ""))
    r = await inst.instalar(_pacote(porta, ["xtts-v2"]))
    await inst.fechar()
    assert r.estado == "concluido" and comandos == []


@pytest.mark.asyncio
async def test_sem_ambiente_da_voz_falha_com_erro_claro(tmp_path, porta):
    inst = _instalador(tmp_path, None, lambda c: (0, ""))
    r = await inst.instalar(_pacote(porta, ["kokoro-onnx==0.6.1"]))
    await inst.fechar()
    assert r.estado == "falhou" and "servico de voz" in r.erro


def test_manifesto_real_separa_kokoro_onnx_como_biblioteca():
    from vard.pacotes import carregar_todos_manifestos

    m = carregar_todos_manifestos()
    assert bib.dependencias_python(m["kokoro"].dependencias, set(m)) == ["kokoro-onnx==0.6.1"]
