"""Testes de dispositivos_com_preferencia (T9c).
Valida resolução por FriendlyName normalizado, fallback para padrão e avisos.
"""
from __future__ import annotations
import sys
import types
import pytest

# Stub de pyaudiowpatch para que _achar_por_nome reconheça loopbacks sem instalar o pacote real.
_paw_stub = types.ModuleType("pyaudiowpatch")
_paw_stub.paWASAPI = 13  # valor arbitrário; só precisa ser consistente com o fake PaFalsoComLista
sys.modules.setdefault("pyaudiowpatch", _paw_stub)

from vard_reuniao.audio import dispositivos_com_preferencia, Dispositivos


class PaFalsoComLista:
    """PyAudio falso com lista controlada de dispositivos."""

    def __init__(self, dispositivos: list[dict]):
        self._dispositivos = dispositivos

    def get_device_count(self) -> int:
        return len(self._dispositivos)

    def get_device_info_by_index(self, i: int) -> dict:
        return self._dispositivos[i]

    def get_default_wasapi_loopback(self) -> dict:
        return {"index": 99, "name": "Loopback Padrão", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

    def get_default_input_device_info(self) -> dict:
        return {"index": 0, "name": "Mic Padrão", "defaultSampleRate": 48000.0, "maxInputChannels": 1}

    def get_host_api_info_by_type(self, tipo):
        # Para _achar_por_nome identificar loopbacks pelo hostApi WASAPI
        return {"index": 10}


def _mic(idx: int, nome: str, canais: int = 1) -> dict:
    return {
        "index": idx,
        "name": nome,
        "defaultSampleRate": 48000.0,
        "maxInputChannels": canais,
        "maxOutputChannels": 0,
        "hostApi": 10,
    }


def _loopback(idx: int, nome: str) -> dict:
    return {
        "index": idx,
        "name": nome,
        "defaultSampleRate": 48000.0,
        "maxInputChannels": 2,
        "maxOutputChannels": 2,
        "hostApi": 10,
    }


def test_sem_preferencia_usa_padrao():
    pa = PaFalsoComLista([_mic(0, "Mic A"), _mic(1, "Mic B")])
    d, avisos = dispositivos_com_preferencia(pa)
    assert isinstance(d, Dispositivos)
    assert not avisos
    # Sem preferência: usa o primeiro input ou default
    assert d.eu_id in (0, 1)


def test_resolve_microfone_por_nome_exato():
    pa = PaFalsoComLista([_mic(5, "Microfone USB Pro"), _mic(6, "Webcam Mic")])
    d, avisos = dispositivos_com_preferencia(pa, microfone_nome="Microfone USB Pro")
    assert d.eu_id == 5
    assert d.eu_nome == "Microfone USB Pro"
    assert "microfone" not in avisos


def test_resolve_loopback_por_saida_nome():
    pa = PaFalsoComLista([
        _mic(0, "Mic"),
        _loopback(20, "Caixas USB [Loopback]"),
        _loopback(21, "Fone BT [Loopback]"),
    ])
    d, avisos = dispositivos_com_preferencia(pa, saida_nome="Fone BT [Loopback]")
    assert d.outros_id == 21
    assert "saida" not in avisos


def test_microfone_ausente_usa_padrao_com_aviso():
    pa = PaFalsoComLista([_mic(0, "Mic Existente")])
    d, avisos = dispositivos_com_preferencia(pa, microfone_nome="Mic Sumiu")
    assert "microfone" in avisos
    assert "não encontrado" in avisos["microfone"]
    # Cai no padrão
    assert d.eu_id == 0


def test_saida_ausente_usa_loopback_padrao_com_aviso():
    pa = PaFalsoComLista([_mic(0, "Mic")])
    d, avisos = dispositivos_com_preferencia(pa, saida_nome="HDMI Sumiu")
    assert "saida" in avisos
    assert "não encontrada" in avisos["saida"]
    # Loopback padrão
    assert d.outros_id == 99


def test_nome_ambiguo_usa_padrao_com_aviso():
    pa = PaFalsoComLista([
        _mic(10, "Mic Genérico"),
        _mic(11, "Mic Genérico"),
    ])
    d, avisos = dispositivos_com_preferencia(pa, microfone_nome="Mic Genérico")
    assert "microfone" in avisos
    assert "ambíguo" in avisos["microfone"].lower() or "não encontrado" in avisos["microfone"]


def test_normalizacao_case_insensitive():
    pa = PaFalsoComLista([_mic(7, "  MICROFONE  usb  ")])
    d, avisos = dispositivos_com_preferencia(pa, microfone_nome="microfone usb")
    assert d.eu_id == 7
    assert "microfone" not in avisos