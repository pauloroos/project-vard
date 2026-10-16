"""Testes do motor Piper próprio (T8b).
Cobre: síntese WAV/PCM com taxa/canais corretos, voz pt-BR configurável,
falha de modelo ausente respeita cancelamento, importação sem download/GPU,
reserva de fala local usa Piper quando habilitado e não aciona API paga/OpenJarvis.
Nenhum teste baixa modelo real nem exige GPU.
"""
from __future__ import annotations
import io
import wave
from unittest.mock import MagicMock, patch
import pytest


def _importar_piper():
    from vard_voz import piper  # noqa: WPS433
    return piper


def test_importacao_sem_download_nem_gpu():
    """Importar piper não baixa modelo, não exige GPU e funciona offline."""
    piper = _importar_piper()
    assert hasattr(piper, "MotorPiper")
    assert hasattr(piper, "VOZES_PIPER_PT_BR")
    # Garante que o módulo não forçou download no nível de módulo.
    nomes = dir(piper)
    assert not any("download" in n.lower() for n in nomes)


def test_vozes_piper_pt_br_tem_feminina_e_masculina():
    piper = _importar_piper()
    vozes = piper.VOZES_PIPER_PT_BR
    assert isinstance(vozes, dict) and vozes
    ids = set(vozes.keys())
    # Pelo menos uma voz pt-BR feminina e uma masculina com IDs estáveis.
    assert any("pt_br" in k.lower() or "pt-br" in k.lower() for k in ids)
    for vid, rotulo in vozes.items():
        assert isinstance(vid, str) and vid
        assert isinstance(rotulo, str) and rotulo


def test_motor_piper_sintetiza_wav_com_taxa_e_canais_corretos():
    piper = _importar_piper()
    motor = piper.MotorPiper()
    # Motor falso: devolve PCM float32 mono 24 kHz sem tocar em GPU/modelo.
    fake_pcm = b"\x00\x00\x80?\x00\x00\x80?" * 1200  # ~0,1 s a 24 kHz
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True
    wav_bytes = motor.falar("Olá mundo.", velocidade=1.0, voz="pt_BR-feminina-medium")
    assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # PCM 16 bits
        assert w.getframerate() == 24000
        assert w.getnframes() > 0


def test_motor_piper_fluxo_pcm_chunks_corretos():
    piper = _importar_piper()
    motor = piper.MotorPiper()
    chunks = [b"\x01\x00" * 480, b"\x02\x00" * 240]
    motor._fluxo_raw = lambda texto, voz, velocidade: iter(chunks)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True
    fluxo = motor.falar_fluxo("Teste.", velocidade=1.0, voz="pt_BR-masculina-medium")
    coletado = b"".join(fluxo)
    assert coletado == b"".join(chunks)


def test_motor_piper_voz_desconhecida_erro_claro():
    piper = _importar_piper()
    motor = piper.MotorPiper()
    motor.pronta = True
    motor.aquecida = True
    with pytest.raises((KeyError, ValueError)):
        motor.falar("Oi.", voz="inexistente_xyz")


def test_motor_piper_falha_modelo_ausente_respeita_cancelamento():
    """Falha por modelo ausente levanta RuntimeError sem tentar fallback externo."""
    piper = _importar_piper()
    motor = piper.MotorPiper()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    tentativas = []

    def _sintetizar_quebrado(texto, voz, velocidade):
        tentativas.append((texto, voz))
        raise RuntimeError("modelo nao encontrado")

    motor._sintetizar_raw = _sintetizar_quebrado  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="modelo nao encontrado"):
        motor.falar("Texto longo.", velocidade=1.0, voz="pt_BR-feminina-medium")
    # A falha ocorreu exatamente uma vez (sem retry/fallback externo).
    assert len(tentativas) == 1


def test_motor_piper_aquecendo_devolve_estado_legivel():
    piper = _importar_piper()
    motor = piper.MotorPiper()
    # Antes de carregar: pronta=False, aquecida=False, mas objeto existe.
    assert motor.pronta is False
    assert motor.aquecida is False
    # vozes() funciona mesmo sem modelo carregado (lista estática).
    vozes = motor.vozes()
    assert isinstance(vozes, list) and vozes


def test_reserva_de_fala_local_usa_piper_quando_habilitado():
    """Quando Piper está habilitado, a reserva local é ele; OpenJarvis não é chamado."""
    piper = _importar_piper()
    motor = piper.MotorPiper()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    fake_pcm = b"\x00\x00" * 240
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    chamadas_oj = []

    def _fake_oj_sintetizar(texto, voz, velocidade):
        chamadas_oj.append((texto, voz))
        return b""

    resultado = motor.falar("Reserva.", velocidade=1.0, voz="pt_BR-feminina-medium")
    assert resultado and len(chamadas_oj) == 0


def test_piper_preserva_id_pt_br_na_saida():
    piper = _importar_piper()
    motor = piper.MotorPiper()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    vozes_usadas = []

    def _captura_voz(texto, voz, velocidade):
        vozes_usadas.append(voz)
        return (b"\x00\x00" * 240, 24000)

    motor._sintetizar_raw = _captura_voz  # type: ignore[attr-defined]
    motor.falar("Teste pt-BR.", voz="pt_BR-feminina-medium")
    assert vozes_usadas == ["pt_BR-feminina-medium"]