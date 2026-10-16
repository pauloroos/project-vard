import pytest
from fastapi.testclient import TestClient

from vard_voz.motor import para_wav
from vard_voz.servidor import criar_app


class MotorFalso:
    device = "cpu"

    def __init__(self, pronta=True):
        self.pronta = pronta
        self.aquecida = pronta
        self.chamadas = []

    VOZES = ["Suad Qasim", "Ana Florence"]

    def vozes(self):
        return list(self.VOZES)

    def tem_voz(self, nome):
        return nome in self.VOZES

    def falar(self, texto, velocidade=1.0, voz=None):
        if voz not in (None, "", *self.VOZES):
            raise KeyError(voz)
        self.chamadas.append((texto, velocidade, voz))
        return para_wav([0.0] * 2400)

    def falar_fluxo(self, texto, velocidade=1.0, voz=None):
        if voz not in (None, "", *self.VOZES):
            raise KeyError(voz)
        self.chamadas.append((texto, velocidade, voz))
        yield b"\x01\x00" * 10
        yield b"\x02\x00" * 5


class STTFalso:
    """MotorSTT falso para testes da rota /transcribe sem dependência de faster-whisper."""
    def __init__(self, pronta=True, texto="texto transcrito", confianca=0.95):
        self.pronta = pronta
        self._texto = texto
        self._confianca = confianca
        self.chamadas: list[bytes] = []

    def transcrever_bytes(self, audio: bytes, idioma: str | None = None) -> tuple[str, float]:
        self.chamadas.append(audio)
        if not self.pronta:
            raise RuntimeError("STT não carregado")
        return self._texto, self._confianca


def cliente(motor, motor_kokoro=None, motor_edge=None, motor_piper=None, stt=None):
    return TestClient(
        criar_app(
            motor,
            motor_kokoro=motor_kokoro,
            motor_edge=motor_edge,
            motor_piper=motor_piper,
            stt=stt,
            carregar_em_thread=False,
        ),
        base_url="http://127.0.0.1:4710",
    )


def test_saude_antes_do_aquecimento():
    r = cliente(MotorFalso(pronta=False)).get("/saude")
    assert r.status_code == 200
    d = r.json()
    assert d["pronta"] is False and d["voz"] == "Suad Qasim" and d["aquecida"] is False


def test_falar_aquecendo_503():
    r = cliente(MotorFalso(pronta=False)).post("/falar", json={"texto": "Oi."})
    assert r.status_code == 503 and r.json() == {"erro": "aquecendo"}


@pytest.mark.parametrize("texto", ["", "   ", "a" * 401])
def test_texto_invalido_400(texto):
    assert cliente(MotorFalso()).post("/falar", json={"texto": texto}).status_code == 400


def test_falar_devolve_wav():
    m = MotorFalso()
    r = cliente(m).post("/falar", json={"texto": "Oi, usuário.", "velocidade": 1.1})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
    assert m.chamadas == [("Oi, usuário", 1.1, None)]


def test_host_estranho_421():
    r = cliente(MotorFalso()).get("/saude", headers={"Host": "evil"})
    assert r.status_code == 421


def test_origin_estranha_403():
    r = cliente(MotorFalso()).get("/saude", headers={"Origin": "http://evil"})
    assert r.status_code == 403


def test_origin_tauri_200_com_cors():
    r = cliente(MotorFalso()).get("/saude", headers={"Origin": "http://tauri.localhost"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_falar_fluxo_pcm():
    m = MotorFalso()
    r = cliente(m).post("/falar", json={"texto": "Oi.", "velocidade": 1.2}, headers={"Accept": "audio/pcm"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/pcm"
    assert (r.headers["x-taxa"], r.headers["x-canais"], r.headers["x-formato"]) == ("24000", "1", "s16le")
    assert r.content == b"\x01\x00" * 10 + b"\x02\x00" * 5
    assert m.chamadas == [("Oi", 1.2, None)]


def test_falar_fluxo_query():
    r = cliente(MotorFalso()).post("/falar?fluxo=1", json={"texto": "Oi."})
    assert r.headers["content-type"] == "audio/pcm"


def test_falar_padrao_continua_wav():
    r = cliente(MotorFalso()).post("/falar", json={"texto": "Oi."}, headers={"Accept": "*/*"})
    assert r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"


def test_falar_fluxo_texto_vazio_400():
    r = cliente(MotorFalso()).post("/falar", json={"texto": " "}, headers={"Accept": "audio/pcm"})
    assert r.status_code == 400


def test_motor_recebe_texto_normalizado_wav_e_pcm():
    m = MotorFalso()
    c = cliente(m)
    assert c.post("/falar", json={"texto": "São 18h05."}).status_code == 200
    r = c.post("/falar", json={"texto": "Custa R$ 12,50!"}, headers={"Accept": "audio/pcm"})
    assert r.status_code == 200
    assert [c[0] for c in m.chamadas] == ["São dezoito e cinco", "Custa doze reais e cinquenta centavos"]


def test_vozes_lista_e_atual():
    # motor_kokoro=None isola o comportamento XTTS-only; com Kokoro ativo a lista inclui vozes Kokoro.
    r = cliente(MotorFalso(), motor_kokoro=None, motor_edge=None, motor_piper=None).get("/vozes")
    assert r.status_code == 200 and r.json() == {"vozes": ["Suad Qasim", "Ana Florence"], "atual": "Suad Qasim"}


def test_vozes_aquecendo_503():
    # Sem nenhum motor opcional e XTTS não pronto → 503; com qualquer motor ativo retorna 200.
    assert cliente(MotorFalso(pronta=False), motor_kokoro=None, motor_edge=None, motor_piper=None).get("/vozes").status_code == 503


def test_falar_com_voz_passa_ao_motor():
    m = MotorFalso()
    r = cliente(m, motor_kokoro=None, motor_edge=None, motor_piper=None).post("/falar", json={"texto": "Oi.", "voz": "Ana Florence"}, headers={"Accept": "audio/pcm"})
    assert r.status_code == 200 and m.chamadas == [("Oi", 1.0, "Ana Florence")]


def test_falar_voz_desconhecida_400():
    # MotorFalso padrão tem pronta=True; com opcionais desativados, valida voz no XTTS.
    m = MotorFalso()
    r = cliente(m, motor_kokoro=None, motor_edge=None, motor_piper=None).post(
        "/falar", json={"texto": "Oi.", "voz": "Ninguém"}
    )
    assert r.status_code == 400 and r.json() == {"erro": "voz_desconhecida"}
    assert m.chamadas == []


def test_falar_sem_voz_usa_a_padrao():
    m = MotorFalso()
    cliente(m).post("/falar", json={"texto": "Oi.", "voz": ""})
    assert m.chamadas[0][2] is None


# ----------------------------------------------------------------------------- STT
def test_transcribe_stt_indisponivel_503():
    """Sem MotorSTT (extra não instalado), /transcribe devolve 503."""
    r = cliente(MotorFalso(), stt=None).post("/v1/speech/transcribe", content=b"\x00" * 10)
    assert r.status_code == 503 and r.json()["erro"] == "stt_indisponivel"


def test_transcribe_stt_nao_carregado_503():
    """MotorSTT existe mas não está pronto → 503."""
    stt = STTFalso(pronta=False)
    r = cliente(MotorFalso(), stt=stt).post("/v1/speech/transcribe", content=b"\x00" * 10)
    assert r.status_code == 503 and r.json()["erro"] == "stt_indisponivel"


def test_transcribe_audio_vazio_400():
    stt = STTFalso()
    r = cliente(MotorFalso(), stt=stt).post("/v1/speech/transcribe", content=b"")
    assert r.status_code == 400 and r.json()["erro"] == "audio_vazio"


def test_transcribe_audio_grande_demais_413():
    stt = STTFalso()
    grande = b"\x00" * (10 * 1024 * 1024 + 1)
    r = cliente(MotorFalso(), stt=stt).post("/v1/speech/transcribe", content=grande)
    assert r.status_code == 413 and r.json()["erro"] == "audio_grande_demais"


def test_transcribe_devolve_texto_e_confianca():
    stt = STTFalso(texto="Olá mundo.", confianca=0.92)
    r = cliente(MotorFalso(), stt=stt).post("/v1/speech/transcribe", content=b"\x00" * 100)
    assert r.status_code == 200
    j = r.json()
    assert j["text"] == "Olá mundo." and j["confidence"] == 0.92
    assert len(stt.chamadas) == 1 and stt.chamadas[0] == b"\x00" * 100


def test_transcribe_falha_do_motor_503():
    """RuntimeError no motor → 503 stt_falhou, não exceção vazada."""
    class STTQueFalha:
        pronta = True
        def transcrever_bytes(self, audio, idioma=None):
            raise RuntimeError("GPU OOM")
    r = cliente(MotorFalso(), stt=STTQueFalha()).post("/v1/speech/transcribe", content=b"\x00" * 10)
    assert r.status_code == 503 and r.json()["erro"] == "stt_falhou"


def test_transcribe_valor_invalido_400():
    """ValueError (ex: áudio longo demais) → 400 com mensagem."""
    class STTValorInvalido:
        pronta = True
        def transcrever_bytes(self, audio, idioma=None):
            raise ValueError("áudio excede 120s")
    r = cliente(MotorFalso(), stt=STTValorInvalido()).post("/v1/speech/transcribe", content=b"\x00" * 10)
    assert r.status_code == 400 and "excede" in r.json()["erro"]