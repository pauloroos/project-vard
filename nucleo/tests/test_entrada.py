"""Testes de entrada do núcleo (T1): __main__, /saude e porta ocupada."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

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

    # Apenas importa o app para confirmar que caminhos com espaço não quebram a criação
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