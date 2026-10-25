"""Testes do MotorSTT próprio (faster-whisper opcional).

Sem GPU/download na importação; motor fake para provar contrato sem dependência pesada.
Cobre: limites, decodificação WAV, rejeição de excesso, confiança e palavras de chamada.
"""
from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from vard_voz.transcricao import (
    LIMITE_BYTES,
    LIMITE_SEGUNDOS,
    MotorSTT,
    _decodificar_para_pcm,
    _logprob_para_confianca,
    _ressamplear,
)


def _wav_bytes(pcm16: np.ndarray, taxa: int = 16000, canais: int = 1) -> bytes:
    """Gera WAV PCM16 mono/stereo sintético para testes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(np.asarray(pcm16, dtype=np.int16).tobytes())
    return buf.getvalue()


class FakeSegmento:
    """Segmento falso do faster-whisper para testes sem modelo real."""

    def __init__(self, text: str, avg_logprob: float = -0.2):
        self.text = text
        self.avg_logprob = avg_logprob


class FakeModelo:
    """WhisperModel falso que devolve segmentos controlados."""

    def __init__(self, segmentos: list[FakeSegmento] | None = None):
        self._segmentos = segmentos or []
        self.chamadas: list[dict] = []

    def transcribe(self, audio, language="pt", condition_on_previous_text=True, initial_prompt=None):
        self.chamadas.append({
            "language": language,
            "condition_on_previous_text": condition_on_previous_text,
            "initial_prompt": initial_prompt,
            "audio_shape": getattr(audio, "shape", None),
        })
        info = type("Info", (), {"language": language})()
        return self._segmentos, info


@pytest.fixture
def motor_com_fake():
    """MotorSTT com modelo fake injetado (sem carregar faster-whisper real)."""
    m = MotorSTT(modelo="base", device="cpu", compute_type="int8")
    m._modelo = FakeModelo([FakeSegmento("Olá mundo.", -0.1)])
    return m


def test_importacao_sem_gpu_nem_download():
    """Importar o módulo não deve carregar faster-whisper nem baixar nada."""
    import importlib
    import sys

    # Remove do cache se já foi importado
    # (o faster-whisper também: com o extra instalado, outro teste pode tê-lo importado antes)
    mods_remover = [k for k in sys.modules if k.startswith(("vard_voz.transcricao", "faster_whisper"))]
    for k in mods_remover:
        del sys.modules[k]

    mod = importlib.import_module("vard_voz.transcricao")
    assert hasattr(mod, "MotorSTT")
    # faster-whisper NÃO deve estar em sys.modules após import do módulo
    assert "faster_whisper" not in sys.modules


def test_motor_nao_carregado_levanta_runtime_error():
    m = MotorSTT()
    assert m.pronta is False
    with pytest.raises(RuntimeError, match="não carregado"):
        m.transcrever_bytes(b"\x00" * 100)


def test_carregar_sem_pacote_levanta_runtime_error(monkeypatch):
    """Se faster-whisper não estiver instalado, carregar() deve falhar com mensagem clara."""
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("No module named 'faster_whisper'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    m = MotorSTT()
    with pytest.raises(RuntimeError, match="faster-whisper não instalado"):
        m.carregar()


def test_limite_bytes_excedido(motor_com_fake):
    audio_grande = b"\x00" * (LIMITE_BYTES + 1)
    with pytest.raises(ValueError, match="excede"):
        motor_com_fake.transcrever_bytes(audio_grande)


def test_limite_segundos_excedido(motor_com_fake):
    """Áudio WAV longo demais (>120s) deve ser rejeitado antes da inferência."""
    # 121 segundos a 16kHz mono 16-bit = 121 * 16000 * 2 bytes
    pcm = np.zeros(int((LIMITE_SEGUNDOS + 1) * 16000), dtype=np.int16)
    wav = _wav_bytes(pcm)
    with pytest.raises(ValueError, match="excede.*s"):
        motor_com_fake.transcrever_bytes(wav)


def test_wav_mono_16k_decodifica_corretamente():
    pcm = np.array([100, -200, 300, -400], dtype=np.int16)
    wav = _wav_bytes(pcm, taxa=16000, canais=1)
    resultado = _decodificar_para_pcm(wav)
    np.testing.assert_array_equal(resultado, pcm)


def test_wav_stereo_convertido_para_mono():
    stereo = np.array([[100, 200], [-300, -100]], dtype=np.int16)
    wav = _wav_bytes(stereo.flatten(), taxa=16000, canais=2)
    resultado = _decodificar_para_pcm(wav)
    esperado = np.array([150, -200], dtype=np.int16)  # média dos canais
    np.testing.assert_array_equal(resultado, esperado)


def test_wav_taxa_diferente_ressampleado():
    # 0.5s de áudio a 8kHz = 4000 amostras; a 16kHz deve virar ~8000
    pcm_8k = np.zeros(4000, dtype=np.int16)
    wav = _wav_bytes(pcm_8k, taxa=8000, canais=1)
    resultado = _decodificar_para_pcm(wav)
    assert len(resultado) == pytest.approx(8000, abs=10)


def test_audio_invalido_sem_pyav_levanta_runtime_error():
    """Bytes que não são WAV e sem PyAV devem levantar RuntimeError."""
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "av":
            raise ImportError("No module named 'av'")
        return original_import(name, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "__import__", fake_import)
        with pytest.raises(RuntimeError, match="PyAV não instalado"):
            _decodificar_para_pcm(b"\x00\x01\x02\x03")


def test_transcrever_devolve_texto_e_confianca(motor_com_fake):
    wav = _wav_bytes(np.zeros(1600, dtype=np.int16))
    texto, conf = motor_com_fake.transcrever_bytes(wav)
    assert texto == "Olá mundo."
    assert 0.0 <= conf <= 1.0


def test_transcrever_passa_language_pt_e_condition_false(motor_com_fake):
    wav = _wav_bytes(np.zeros(1600, dtype=np.int16))
    motor_com_fake.transcrever_bytes(wav)
    chamada = motor_com_fake._modelo.chamadas[0]
    assert chamada["language"] == "pt"
    assert chamada["condition_on_previous_text"] is False


def test_palavras_chamada_viraram_initial_prompt():
    m = MotorSTT(palavras_chamada=["Vard", "assistente"])
    m._modelo = FakeModelo([FakeSegmento("Sim.")])
    wav = _wav_bytes(np.zeros(1600, dtype=np.int16))
    m.transcrever_bytes(wav)
    assert m._modelo.chamadas[0]["initial_prompt"] == "Vard assistente"


def test_silencio_legitimo_devolve_vazio_com_conf_zero():
    m = MotorSTT()
    m._modelo = FakeModelo([])  # sem segmentos = silêncio
    wav = _wav_bytes(np.zeros(1600, dtype=np.int16))
    texto, conf = m.transcrever_bytes(wav)
    assert texto == ""
    assert conf == 0.0


def test_logprob_para_confianca_mapeamento():
    assert _logprob_para_confianca([0.0]) == 1.0
    assert _logprob_para_confianca([-3.0]) == 0.0
    assert 0.0 < _logprob_para_confianca([-1.5]) < 1.0
    assert _logprob_para_confianca([]) == 0.0


def test_ressamplear_mesma_taxa_retorna_igual():
    arr = np.array([1, 2, 3, 4], dtype=np.int16)
    resultado = _ressamplear(arr, 16000, 16000)
    np.testing.assert_array_equal(resultado, arr)


def test_ressamplear_dobra_taxa():
    arr = np.array([0, 100], dtype=np.int16)
    resultado = _ressamplear(arr, 8000, 16000)
    assert len(resultado) == 4


def test_falha_nao_vira_silencio_com_sucesso():
    """Erro na transcrição deve propagar exceção, não devolver texto vazio com sucesso."""
    m = MotorSTT()

    class ModeloQueFalha:
        def transcribe(self, *a, **kw):
            raise RuntimeError("GPU OOM")

    m._modelo = ModeloQueFalha()
    wav = _wav_bytes(np.zeros(1600, dtype=np.int16))
    with pytest.raises(RuntimeError, match="GPU OOM"):
        m.transcrever_bytes(wav)