import threading
import wave
import io

import httpx
import numpy as np

from vard_reuniao import transcricao as tr
from vard_reuniao.vad import Segmento


def test_wav_bytes_e_riff_16k_mono():
    b = tr.wav_bytes(np.zeros(1600, dtype=np.int16))
    with wave.open(io.BytesIO(b)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (16000, 1, 2, 1600)


def test_transcritor_manda_language_pt_e_le_text():
    visto = {}

    def post(url, **kw):
        visto.update(url=url, kw=kw)
        return httpx.Response(200, json={"text": " Olá, mundo. ", "confidence": 0.97})

    t = tr.Transcritor(post=post)
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("Olá, mundo.", 0.97)
    assert visto["url"].endswith("/v1/speech/transcribe") and visto["kw"]["data"] == {"language": "pt"}
    assert visto["kw"]["files"]["file"][0].endswith(".wav") and visto["kw"]["trust_env"] is False


def test_transcritor_erro_vira_vazio():
    def post(url, **kw):
        raise httpx.ConnectError("fora")
    assert tr.Transcritor(post=post).transcrever(np.zeros(16, dtype=np.int16)) == ("", -1.0)
    assert tr.Transcritor(post=lambda u, **k: httpx.Response(500, text="x")).transcrever(np.zeros(16, dtype=np.int16)) == ("", -1.0)


def test_limpar_bloqueio_confianca_repeticao():
    bl = ["legendas pela comunidade"]
    assert tr.limpar("Legendas pela comunidade Amara.org", bl, 0.9) == ""
    assert tr.limpar("Tudo bem.", bl, 0.1) == ""
    assert tr.limpar("Tudo bem. Tudo bem. Tudo bem.", bl, 0.9) == ""
    assert tr.limpar("...", bl, 0.9) == ""
    assert tr.limpar("  Vamos decidir o prazo.  ", bl, 0.9) == "Vamos decidir o prazo."


def test_fila_e_serial_e_chama_ao_texto_na_ordem():
    ordem, pronto = [], threading.Event()
    trava = threading.Lock()

    def transcrever(seg):
        assert trava.acquire(blocking=False), "duas transcrições ao mesmo tempo"
        try:
            return (f"t{int(seg.t0)}", 0.9)
        finally:
            trava.release()

    def ao_texto(seg, texto, conf):
        ordem.append(texto)
        if len(ordem) == 3:
            pronto.set()

    f = tr.Fila(transcrever, ao_texto)
    f.iniciar()
    for t0 in (1, 2, 3):
        f.por(Segmento("eu", t0, t0 + 1, np.zeros(16, dtype=np.int16)))
    assert pronto.wait(5) and ordem == ["t1", "t2", "t3"]
    assert f.esvaziar(2) is True
    f.parar()


def test_fila_sobrevive_a_erro_no_callback():
    visto = []

    def ao_texto(seg, texto, conf):
        visto.append(texto)
        if len(visto) == 1:
            raise RuntimeError("boom")

    f = tr.Fila(lambda s: ("x", 1.0), ao_texto)
    f.iniciar()
    f.por(Segmento("eu", 0, 1, np.zeros(16, dtype=np.int16)))
    f.por(Segmento("eu", 1, 2, np.zeros(16, dtype=np.int16)))
    assert f.esvaziar(5) and len(visto) == 2
    f.parar()


def test_limpar_bloqueio_exato():
    exato = ["obrigado", "tchau"]
    assert tr.limpar("Obrigado.", [], 1.0, bloqueio_exato=exato) == ""
    assert tr.limpar("Obrigado pela ajuda, vamos seguir.", [], 1.0, bloqueio_exato=exato) == "Obrigado pela ajuda, vamos seguir."


def test_fila_e_de_uso_unico_depois_de_parar():
    import pytest
    f = tr.Fila(lambda s: ("x", 1.0), lambda s, t, c: None)
    f.iniciar()
    f.parar()
    with pytest.raises(RuntimeError):
        f.iniciar()


# ----------------------------------------------------------------------------- STT PRÓPRIO / FALLBACK
def test_transcritor_proprio_usa_voz_quando_disponivel():
    """Com proprio=True, tenta primeiro o vard-voz (4710)."""
    chamadas = []

    def post(url, **kw):
        chamadas.append(url)
        if "4710" in url:
            return httpx.Response(200, json={"text": "pela voz", "confidence": 0.9})
        raise AssertionError("não deveria chamar OpenJarvis")

    t = tr.Transcritor(post=post, proprio=True)
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("pela voz", 0.9)
    assert len(chamadas) == 1 and "4710" in chamadas[0]


def test_transcritor_proprio_fallback_para_openjarvis_em_503():
    """STT próprio 503 → cai no OpenJarvis silenciosamente."""
    chamadas = []

    def post(url, **kw):
        chamadas.append(url)
        if "4710" in url:
            return httpx.Response(503, json={"erro": "stt_indisponivel"})
        return httpx.Response(200, json={"text": "pelo OJ", "confidence": 0.8})

    t = tr.Transcritor(post=post, proprio=True)
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("pelo OJ", 0.8)
    assert len(chamadas) == 2 and "4710" in chamadas[0] and "8000" in chamadas[1]


def test_transcritor_proprio_fallback_para_openjarvis_em_connect_error():
    """vard-voz fora do ar → cai no OpenJarvis."""
    chamadas = []

    def post(url, **kw):
        chamadas.append(url)
        if "4710" in url:
            raise httpx.ConnectError("fora")
        return httpx.Response(200, json={"text": "fallback OJ", "confidence": 0.7})

    t = tr.Transcritor(post=post, proprio=True)
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("fallback OJ", 0.7)
    assert len(chamadas) == 2


def test_transcritor_sem_proprio_usa_so_openjarvis():
    """Com proprio=False, usa só o OpenJarvis (comportamento legado)."""
    chamadas = []

    def post(url, **kw):
        chamadas.append(url)
        return httpx.Response(200, json={"text": "OJ direto", "confidence": 0.85})

    t = tr.Transcritor(post=post, proprio=False)
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("OJ direto", 0.85)
    assert len(chamadas) == 1 and "8000" in chamadas[0]


def test_transcritor_proprio_via_env_var(monkeypatch):
    """VARD_STT_PROPRIO=1 ativa o modo próprio mesmo sem parâmetro."""
    monkeypatch.setenv("VARD_STT_PROPRIO", "1")
    chamadas = []

    def post(url, **kw):
        chamadas.append(url)
        if "4710" in url:
            return httpx.Response(200, json={"text": "via env", "confidence": 0.9})
        raise AssertionError("não deveria chamar OpenJarvis")

    t = tr.Transcritor(post=post)
    assert t.proprio is True
    assert t.transcrever(np.zeros(1600, dtype=np.int16)) == ("via env", 0.9)
    assert len(chamadas) == 1 and "4710" in chamadas[0]
