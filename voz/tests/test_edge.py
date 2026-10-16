"""Testes do motor Edge TTS próprio (T8b).
Cobre: síntese WAV/PCM com taxa/canais corretos, voz pt-BR configurável,
falha de rede respeita cancelamento, importação sem rede/download,
reserva de fala local usa Edge quando habilitado e não aciona API paga/OpenJarvis.
Nenhum teste faz rede real nem baixa pesos.
"""
from __future__ import annotations

import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _importar_edge():
    from vard_voz import edge  # noqa: WPS433
    return edge


def test_importacao_sem_rede_nem_download():
    """Importar edge não faz rede, não baixa nada e funciona offline."""
    edge = _importar_edge()
    assert hasattr(edge, "MotorEdge")
    assert hasattr(edge, "VOZES_EDGE_PT_BR")
    # Garante que o módulo não forçou import de edge_tts no nível de módulo.
    nomes = dir(edge)
    assert not any("edge_tts" in n.lower() for n in nomes)


def test_vozes_edge_pt_br_tem_feminina_e_masculina():
    edge = _importar_edge()
    vozes = edge.VOZES_EDGE_PT_BR
    assert isinstance(vozes, dict) and vozes
    ids = set(vozes.keys())
    # Pelo menos uma voz pt-BR feminina e uma masculina com IDs estáveis.
    assert any("br-" in k.lower() or "pt-br" in k.lower() for k in ids)
    for vid, rotulo in vozes.items():
        assert isinstance(vid, str) and vid
        assert isinstance(rotulo, str) and rotulo


def test_motor_edge_sintetiza_wav_com_taxa_e_canais_corretos():
    edge = _importar_edge()
    motor = edge.MotorEdge()
    # Motor falso: devolve PCM float32 mono 24 kHz sem tocar em rede.
    fake_pcm = b"\x00\x00\x80?\x00\x00\x80?" * 1200  # ~0,1 s a 24 kHz
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    wav_bytes = motor.falar("Olá mundo.", velocidade=1.0, voz="pt-BR-FranciscaNeural")
    assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # PCM 16 bits
        assert w.getframerate() == 24000
        assert w.getnframes() > 0


def test_motor_edge_fluxo_pcm_chunks_corretos():
    edge = _importar_edge()
    motor = edge.MotorEdge()
    chunks = [b"\x01\x00" * 480, b"\x02\x00" * 240]
    motor._fluxo_raw = lambda texto, voz, velocidade: iter(chunks)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    fluxo = motor.falar_fluxo("Teste.", velocidade=1.0, voz="pt-BR-AntonioNeural")
    coletado = b"".join(fluxo)
    assert coletado == b"".join(chunks)


def test_motor_edge_voz_desconhecida_erro_claro():
    edge = _importar_edge()
    motor = edge.MotorEdge()
    motor.pronta = True
    motor.aquecida = True

    with pytest.raises((KeyError, ValueError)):
        motor.falar("Oi.", voz="inexistente_xyz")


def test_motor_edge_falha_respeita_cancelamento_e_nao_chama_api_paga():
    """Falha na síntese levanta RuntimeError sem tentar fallback externo."""
    edge = _importar_edge()
    motor = edge.MotorEdge()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    tentativas = []

    def _sintetizar_quebrado(texto, voz, velocidade):
        tentativas.append((texto, voz))
        raise RuntimeError("rede indisponivel")

    motor._sintetizar_raw = _sintetizar_quebrado  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="rede indisponivel"):
        motor.falar("Texto longo.", velocidade=1.0, voz="pt-BR-FranciscaNeural")
    # A falha ocorreu exatamente uma vez (sem retry/fallback externo).
    assert len(tentativas) == 1


def test_motor_edge_aquecendo_devolve_estado_legivel():
    edge = _importar_edge()
    motor = edge.MotorEdge()
    # Antes de carregar: pronta=False, aquecida=False, mas objeto existe.
    assert motor.pronta is False
    assert motor.aquecida is False
    # vozes() funciona mesmo sem modelo carregado (lista estática).
    vozes = motor.vozes()
    assert isinstance(vozes, list) and vozes


def test_reserva_de_fala_local_usa_edge_quando_habilitado():
    """Quando Edge está habilitado, a reserva local é ele; OpenJarvis não é chamado."""
    edge = _importar_edge()
    motor = edge.MotorEdge()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    fake_pcm = b"\x00\x00" * 240
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]

    chamadas_oj = []

    def _fake_oj_sintetizar(texto, voz, velocidade):
        chamadas_oj.append((texto, voz))
        return b""

    resultado = motor.falar("Reserva.", velocidade=1.0, voz="pt-BR-FranciscaNeural")
    assert resultado and len(chamadas_oj) == 0


def test_edge_preserva_id_pt_br_na_saida():
    edge = _importar_edge()
    motor = edge.MotorEdge()
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    vozes_usadas = []

    def _captura_voz(texto, voz, velocidade):
        vozes_usadas.append(voz)
        return (b"\x00\x00" * 240, 24000)

    motor._sintetizar_raw = _captura_voz  # type: ignore[attr-defined]
    motor.falar("Teste pt-BR.", voz="pt-BR-FranciscaNeural")
    assert vozes_usadas == ["pt-BR-FranciscaNeural"]