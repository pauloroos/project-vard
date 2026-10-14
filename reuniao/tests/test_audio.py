from types import SimpleNamespace

import numpy as np

from vard_reuniao import audio
from tests.conftest import tom


def test_para_mono_16k_de_48k_estereo():
    bloco = np.stack([tom(440, 0.1, 48000), tom(440, 0.1, 48000)], axis=1)   # (4800, 2) float32
    pcm = audio.para_mono_16k(bloco, 48000)
    assert pcm.dtype == np.int16 and pcm.shape == (1600,)
    assert 0.2 * 32767 < np.abs(pcm).max() <= 0.35 * 32767


def test_para_mono_16k_ja_mono_16k_so_converte():
    pcm = audio.para_mono_16k(tom(440, 0.05), 16000)
    assert pcm.shape == (800,) and pcm.dtype == np.int16


def test_para_mono_16k_satura_sem_estourar():
    pcm = audio.para_mono_16k(np.full(1600, 2.0, dtype=np.float32), 16000)
    assert pcm.max() == 32767


def test_para_mono_16k_44100():
    pcm = audio.para_mono_16k(tom(440, 1.0, 44100), 44100)
    assert abs(pcm.shape[0] - 16000) <= 2


class PaFalso:
    def get_host_api_info_by_type(self, tipo):
        raise OSError("sem host API WASAPI")      # o PyAudioWPatch levanta OSError; cai no microfone padrão

    def get_default_wasapi_loopback(self):
        return {"index": 7, "name": "Fone [Loopback]", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

    def get_default_input_device_info(self):
        return {"index": 2, "name": "Microfone", "defaultSampleRate": 48000.0, "maxInputChannels": 1}


def test_dispositivos_padrao():
    d = audio.dispositivos_padrao(PaFalso())
    assert (d.eu_id, d.outros_id) == (2, 7) and d.taxa_outros == 48000 and d.canais_outros == 2 and d.canais_eu == 1
    assert "Loopback" in d.outros_nome


def test_para_mono_16k_mais_de_dois_canais_usa_so_os_dois_primeiros():
    bloco = np.zeros((1600, 8), dtype=np.float32)
    bloco[:, 0] = 0.4
    bloco[:, 1] = 0.4
    pcm = audio.para_mono_16k(bloco, 16000)
    assert abs(int(pcm[100]) - int(0.4 * 32767)) <= 1      # média de todos os 8 daria 0.1


class PaWasapiFalso(PaFalso):
    def get_host_api_info_by_type(self, tipo):
        return {"defaultInputDevice": 5}

    def get_device_info_by_index(self, i):
        return {"index": i, "name": "Microfone WASAPI", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

    def get_default_input_device_info(self):
        raise AssertionError("deveria usar o dispositivo padrão do WASAPI")


def test_microfone_pelo_wasapi():
    d = audio.dispositivos_padrao(PaWasapiFalso())
    assert d.eu_id == 5 and d.eu_nome == "Microfone WASAPI" and d.canais_eu == 2


class StreamFalso:
    def start_stream(self): pass
    def stop_stream(self): pass
    def close(self): pass


class PaAbreFalso:
    def __init__(self):
        self.cbs = {}

    def open(self, **kw):
        self.cbs[kw["input_device_index"]] = kw["stream_callback"]
        return StreamFalso()


def test_captura_acumula_100ms_antes_de_converter(monkeypatch):
    pa = PaAbreFalso()
    d = audio.Dispositivos(1, "mic", 2, "lb", 48000, 48000, 2, 2)
    visto = []
    cap = audio.Captura(pa, d, lambda tr, pcm, t: visto.append((tr, pcm, t)))
    cap.abrir()
    bloco = np.stack([tom(440, 0.02, 48000)] * 2, axis=1).astype(np.float32).tobytes()
    relogio = {"t": 50.0}
    monkeypatch.setattr(audio, "time", SimpleNamespace(monotonic=lambda: relogio["t"]))
    for _ in range(4):
        pa.cbs[2](bloco, 960, {}, 0)
        relogio["t"] += 0.02
    assert visto == []
    pa.cbs[2](bloco, 960, {}, 0)
    assert len(visto) == 1 and visto[0][0] == "outros" and visto[0][2] == 50.0
    assert visto[0][1].dtype == np.int16 and abs(len(visto[0][1]) - 1600) <= 2
    cap.fechar()


def test_lote_parcial_antes_de_lacuna_e_despachado_com_o_proprio_t(monkeypatch):
    # Loopback em silencio nao entrega quadros: o lote parcial nao pode grudar no audio que volta depois.
    pa = PaAbreFalso()
    d = audio.Dispositivos(1, "mic", 2, "lb", 48000, 48000, 2, 2)
    visto = []
    cap = audio.Captura(pa, d, lambda tr, pcm, t: visto.append((tr, pcm, t)))
    cap.abrir()
    relogio = {"t": 10.0}
    monkeypatch.setattr(audio, "time", SimpleNamespace(monotonic=lambda: relogio["t"]))
    bloco = np.stack([tom(440, 0.02, 48000)] * 2, axis=1).astype(np.float32).tobytes()
    for _ in range(3):
        pa.cbs[2](bloco, 960, {}, 0)
        relogio["t"] += 0.02
    assert visto == []
    relogio["t"] = 20.0
    for _ in range(5):
        pa.cbs[2](bloco, 960, {}, 0)
        relogio["t"] += 0.02
    assert len(visto) == 2
    assert abs(visto[0][2] - 10.0) < 0.01 and abs(len(visto[0][1]) - 960) <= 2     # 3 blocos de 20 ms
    assert abs(visto[1][2] - 20.0) < 0.01 and abs(len(visto[1][1]) - 1600) <= 2
    cap.fechar()


def test_wasapi_sem_pa_com_metodos_propaga_erro_inesperado():
    class PaQuebrado(PaFalso):
        def get_host_api_info_by_type(self, tipo):
            raise RuntimeError("bug")
    import pytest
    with pytest.raises(RuntimeError):
        audio.dispositivos_padrao(PaQuebrado())
