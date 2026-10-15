"""Testes do módulo de preferência de dispositivos (T9)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from vard_reuniao.preferencia import (
    PreferenciaDispositivos,
    gravar_preferencia,
    ler_preferencia,
)


@pytest.fixture
def tmp_dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola VARD_DADOS em um diretório temporário."""
    dados = tmp_path / "dados"
    dados.mkdir()
    monkeypatch.setenv("VARD_DADOS", str(dados))
    return dados


def test_ler_sem_arquivo_retorna_padrao(tmp_dados: Path) -> None:
    pref = ler_preferencia()
    assert pref.microfone_id == ""
    assert pref.saida_id == ""


def test_gravar_e_ler_roundtrip(tmp_dados: Path) -> None:
    original = PreferenciaDispositivos(
        microfone_id="mic-1",
        microfone_rotulo="Microfone USB",
        saida_id="out-2",
        saida_rotulo="Fone Bluetooth",
    )
    gravar_preferencia(original)
    lida = ler_preferencia()
    assert lida == original


def test_gravar_cria_pai(tmp_dados: Path) -> None:
    """gravar_preferencia cria o diretório pai se não existir."""
    # Remove o subdir reuniao para forçar a criação
    subdir = tmp_dados / "reuniao"
    if subdir.exists():
        subdir.rmdir()
    gravar_preferencia(PreferenciaDispositivos(microfone_id="x"))
    assert (subdir / "preferencia.json").exists()


def test_ler_corrompido_retorna_padrao(tmp_dados: Path) -> None:
    caminho = tmp_dados / "reuniao" / "preferencia.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("{invalid json", encoding="utf-8")
    pref = ler_preferencia()
    assert pref.microfone_id == ""


def test_como_dict_contem_todos_os_campos() -> None:
    d = PreferenciaDispositivos(saida_id="s").como_dict()
    assert set(d.keys()) == {
        "microfone_id",
        "microfone_rotulo",
        "saida_id",
        "saida_rotulo",
    }