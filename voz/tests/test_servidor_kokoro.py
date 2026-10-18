"""Kokoro no serviço de voz do Vard, sem OpenJarvis: /saude, /vozes e /falar com o motor instalado,
carregado sob demanda ou ausente. Motores falsos: nada de modelo real, GPU ou áudio."""
from __future__ import annotations

from fastapi.testclient import TestClient

from vard_voz.kokoro import VOZES_KOKORO, MotorKokoro
from vard_voz.motor import para_wav
from vard_voz.servidor import _MotorAusente, criar_app


class KokoroFalso:
    device = "cpu"

    def __init__(self, instalado=True, pronta=False):
        self._instalado = instalado
        self.pronta = pronta
        self.aquecida = pronta
        self.cargas = 0
        self.falas = []

    def instalado(self):
        return self._instalado

    def carregar(self):
        self.cargas += 1
        if self._instalado:
            self.pronta = self.aquecida = True

    def vozes(self):
        return list(VOZES_KOKORO)

    def tem_voz(self, nome):
        return nome in VOZES_KOKORO

    def falar(self, texto, velocidade=1.0, voz=None):
        self.falas.append(voz)
        return para_wav([0.0] * 240)

    def falar_fluxo(self, texto, velocidade=1.0, voz=None):
        self.falas.append(voz)
        yield b"\x01\x00" * 10


def cliente(kokoro):
    app = criar_app(_MotorAusente(), motor_kokoro=kokoro, motor_edge=None, motor_piper=None,
                    stt=object(), carregar_em_thread=False)
    return TestClient(app, base_url="http://127.0.0.1:4710")


def test_saude_mostra_kokoro_instalado_antes_de_carregar():
    d = cliente(KokoroFalso(instalado=True, pronta=False)).get("/saude").json()
    assert d["kokoro"] is True
    assert d["kokoro_carregado"] is False
    assert d["pronta"] is False  # nada carregado ainda: o HUD não manda frase sem voz


def test_saude_sem_kokoro_instalado():
    d = cliente(KokoroFalso(instalado=False)).get("/saude").json()
    assert d["kokoro"] is False and d["kokoro_carregado"] is False


def test_vozes_lista_kokoro_instalado_e_separa_por_motor():
    r = cliente(KokoroFalso(instalado=True, pronta=False)).get("/vozes")
    assert r.status_code == 200
    d = r.json()
    assert "pf_dora" in d["vozes"] and "pm_alex" in d["vozes"]
    assert d["por_motor"]["kokoro"] == list(VOZES_KOKORO)


def test_vozes_sem_nenhum_motor_continua_503():
    r = cliente(KokoroFalso(instalado=False)).get("/vozes")
    assert r.status_code == 503


def test_falar_com_voz_kokoro_carrega_sob_demanda_uma_vez():
    k = KokoroFalso(instalado=True, pronta=False)
    c = cliente(k)
    for _ in range(2):
        r = c.post("/falar", json={"texto": "Olá.", "voz": "pm_alex"}, headers={"Accept": "audio/pcm"})
        assert r.status_code == 200
    assert k.cargas == 1
    assert k.falas == ["pm_alex", "pm_alex"]
    assert c.get("/saude").json()["kokoro_carregado"] is True


def test_falar_com_voz_kokoro_sem_instalacao_e_503():
    k = KokoroFalso(instalado=False)
    r = cliente(k).post("/falar", json={"texto": "Olá.", "voz": "pf_dora"})
    assert r.status_code == 503
    assert k.falas == []


def test_motor_real_sem_arquivos_fica_fora_sem_erro(tmp_path):
    k = MotorKokoro(device="cpu", pasta=tmp_path)
    c = cliente(k)
    assert c.get("/saude").json()["kokoro"] is False
    assert c.post("/falar", json={"texto": "Olá.", "voz": "pf_dora"}).status_code == 503
