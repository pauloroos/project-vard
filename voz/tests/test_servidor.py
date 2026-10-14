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


def cliente(motor):
    return TestClient(criar_app(motor, carregar_em_thread=False), base_url="http://127.0.0.1:4710")


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
    r = cliente(MotorFalso()).get("/vozes")
    assert r.status_code == 200 and r.json() == {"vozes": ["Suad Qasim", "Ana Florence"], "atual": "Suad Qasim"}


def test_vozes_aquecendo_503():
    assert cliente(MotorFalso(pronta=False)).get("/vozes").status_code == 503


def test_falar_com_voz_passa_ao_motor():
    m = MotorFalso()
    r = cliente(m).post("/falar", json={"texto": "Oi.", "voz": "Ana Florence"}, headers={"Accept": "audio/pcm"})
    assert r.status_code == 200 and m.chamadas == [("Oi", 1.0, "Ana Florence")]


def test_falar_voz_desconhecida_400():
    m = MotorFalso()
    r = cliente(m).post("/falar", json={"texto": "Oi.", "voz": "Ninguém"})
    assert r.status_code == 400 and r.json() == {"erro": "voz_desconhecida"}
    assert m.chamadas == []


def test_falar_sem_voz_usa_a_padrao():
    m = MotorFalso()
    cliente(m).post("/falar", json={"texto": "Oi.", "voz": ""})
    assert m.chamadas[0][2] is None
