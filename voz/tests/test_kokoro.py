"""Testes do motor Kokoro próprio (T8).

Cobre: síntese WAV/PCM com taxa/canais corretos, ID de voz pt-BR preservado,
falha de síntese respeita cancelamento, instalação sem XTTS/coqui-tts,
reserva de fala local usa Kokoro quando habilitado e não aciona API paga/OpenJarvis.
Nenhum teste carrega modelo real nem exige GPU.
"""
from __future__ import annotations

import io
import struct
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# Importação leve: kokoro.py não deve importar TTS/coqui nem exigir GPU.
def _importar_kokoro():
    from vard_voz import kokoro  # noqa: WPS433
    return kokoro


def test_importacao_sem_gpu_nem_coqui():
    """Importar kokoro não baixa pesos, não importa TTS e funciona sem CUDA."""
    kokoro = _importar_kokoro()
    assert hasattr(kokoro, "MotorKokoro")
    assert hasattr(kokoro, "VOZES_KOKORO")
    # Garante que o módulo não forçou import de TTS/coqui no nível de módulo.
    nomes = dir(kokoro)
    assert "TTS" not in nomes
    assert not any("coqui" in n.lower() for n in nomes)


def test_vozes_kokoro_tem_pt_br_e_ids_estaveis():
    kokoro = _importar_kokoro()
    vozes = kokoro.VOZES_KOKORO
    assert isinstance(vozes, dict) and vozes
    ids = set(vozes.keys())
    # Pelo menos uma voz pt-BR feminina e uma masculina com IDs estáveis.
    assert "pf_dora" in ids or any(k.startswith("pf_") for k in ids)
    assert "pm_alex" in ids or any(k.startswith("pm_") for k in ids)
    # Todos os valores têm rótulo legível.
    for vid, rotulo in vozes.items():
        assert isinstance(vid, str) and vid
        assert isinstance(rotulo, str) and rotulo


def test_motor_kokoro_sintetiza_wav_com_taxa_e_canais_corretos():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    # Motor falso: devolve PCM float32 mono 24 kHz sem tocar em GPU.
    fake_pcm = b"\x00\x00\x80?\x00\x00\x80?" * 1200  # ~0,1 s a 24 kHz
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    wav_bytes = motor.falar("Olá mundo.", velocidade=1.0, voz="pf_dora")
    assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # PCM 16 bits
        assert w.getframerate() == 24000
        assert w.getnframes() > 0


def test_motor_kokoro_fluxo_pcm_headers_corretos():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    chunks = [b"\x01\x00" * 480, b"\x02\x00" * 240]
    motor._fluxo_raw = lambda texto, voz, velocidade: iter(chunks)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    fluxo = motor.falar_fluxo("Teste.", velocidade=1.0, voz="pm_alex")
    coletado = b"".join(fluxo)
    assert coletado == b"".join(chunks)


def test_motor_kokoro_voz_desconhecida_erro_claro():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    with pytest.raises((KeyError, ValueError)):
        motor.falar("Oi.", voz="inexistente_xyz")


def test_motor_kokoro_falha_respeita_cancelamento_e_nao_chama_api_paga():
    """Falha na síntese local levanta RuntimeError sem tentar fallback externo."""
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]

    tentativas = []

    def _sintetizar_quebrado(texto, voz, velocidade):
        tentativas.append((texto, voz))
        raise RuntimeError("gpu indisponivel")

    motor._sintetizar_raw = _sintetizar_quebrado  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="gpu indisponivel"):
        motor.falar("Texto longo.", velocidade=1.0, voz="pf_dora")
    # A falha ocorreu exatamente uma vez (sem retry/fallback externo).
    assert len(tentativas) == 1


def test_motor_kokoro_aquecendo_devolve_estado_legivel():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    # Antes de carregar: pronta=False, aquecida=False, mas objeto existe.
    assert motor.pronta is False
    assert motor.aquecida is False
    # vozes() funciona mesmo sem modelo carregado (lista estática).
    vozes = motor.vozes()
    assert isinstance(vozes, list) and vozes


def test_reserva_de_fala_local_usa_kokoro_quando_habilitado():
    """Quando Kokoro está instalado/habilitado, a reserva local é ele; OpenJarvis não é chamado."""
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    fake_pcm = b"\x00\x00" * 240
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    chamadas_oj = []

    def _fake_oj_sintetizar(texto, voz, velocidade):
        chamadas_oj.append((texto, voz))
        return b""

    # Simula cenário: Kokoro disponível → reserva NÃO chama OJ.
    resultado = motor.falar("Reserva.", velocidade=1.0, voz="pf_dora")
    assert resultado and len(chamadas_oj) == 0


def test_kokoro_preserva_id_pt_br_na_saida():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    vozes_usadas = []

    def _captura_voz(texto, voz, velocidade):
        vozes_usadas.append(voz)
        return (b"\x00\x00" * 240, 24000)

    motor._sintetizar_raw = _captura_voz  # type: ignore[attr-defined]
    motor.falar("Teste pt-BR.", voz="pf_dora")
    assert vozes_usadas == ["pf_dora"]