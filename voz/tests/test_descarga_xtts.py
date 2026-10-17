"""Descarga automática do XTTS após inatividade (0.9.4 leve).

- O motor descarrega sozinho depois de `ocioso_s` segundos sem uso.
- A próxima fala recarrega o modelo sob demanda (sem erro nem timeout curto).
- /saude informa se o XTTS está carregado ou descarregado.
- Timer falso controlável permite provar o ciclo sem esperar 10 minutos.

Nenhum teste aqui importa TTS/torch: tudo é dublê para não travar em ambiente
sem GPU ou sem o pacote XTTS instalado.
"""
from __future__ import annotations

import threading
import time

import pytest


class TimerControlavel:
    """Timer que NÃO dispara automaticamente; só quando .disparar() é chamado."""

    instancias: list["TimerControlavel"] = []

    def __init__(self, intervalo, funcao, *args, **kwargs):
        self.intervalo = intervalo
        self.funcao = funcao
        self.args = args
        self.kwargs = kwargs
        self.daemon = False
        self.name = ""
        self._cancelado = False
        self._disparado = False
        TimerControlavel.instancias.append(self)

    def start(self) -> None:
        # Não dispara automaticamente; o teste controla quando chamar.
        pass

    def cancel(self) -> None:
        self._cancelado = True

    def disparar(self) -> None:
        if self._cancelado or self._disparado:
            return
        self._disparado = True
        self.funcao(*self.args, **self.kwargs)


@pytest.fixture(autouse=True)
def limpar_timers():
    TimerControlavel.instancias.clear()
    yield
    TimerControlavel.instancias.clear()


@pytest.fixture
def motor_descarga(monkeypatch):
    """Motor XTTS falso com timer controlado e sem dependência de TTS/GPU."""
    monkeypatch.setattr(threading, "Timer", TimerControlavel)

    from vard_voz.motor import Motor

    class ModeloFalso:
        class SpeakerManager:
            speakers = {
                "Suad Qasim": {"gpt_cond_latent": b"gpt", "speaker_embedding": b"emb"}
            }

        speaker_manager = SpeakerManager()

        def inference(self, *_a, **_k):
            return {"wav": [0.0] * 240}

    cargas: list[float] = []
    descargas: list[float] = []
    original_descarregar = Motor.descarregar

    def carregar_falso(self):
        cargas.append(time.monotonic())
        self._modelo = ModeloFalso()
        self.pronta = True
        self.aquecida = True
        self._ultimo_uso = time.time()
        self._agendar_descarga()

    def descarregar_rastreado(self):
        descargas.append(time.monotonic())
        original_descarregar(self)

    monkeypatch.setattr(Motor, "carregar", carregar_falso)
    monkeypatch.setattr(Motor, "descarregar", descarregar_rastreado)

    m = Motor(device="cpu", ocioso_s=600)
    return m, cargas, descargas


def test_agenda_timer_apos_carregar(motor_descarga):
    motor, cargas, _ = motor_descarga
    motor.carregar()
    assert motor.pronta and motor.aquecida
    assert len(cargas) == 1
    # Timer foi agendado mas NÃO disparou ainda (controlável)
    timers = [t for t in TimerControlavel.instancias if not t._cancelado]
    assert len(timers) >= 1


def test_descarga_quando_timer_dispara(motor_descarga):
    motor, _, descargas = motor_descarga
    motor.carregar()
    assert motor.pronta
    # Simula passagem do tempo: dispara o timer agendado
    timers_ativos = [t for t in TimerControlavel.instancias if not t._cancelado]
    assert timers_ativos, "nenhum timer agendado"
    timers_ativos[-1].disparar()
    assert len(descargas) >= 1
    assert not motor.pronta and not motor.aquecida


def test_recarga_na_fala_apos_descarga(motor_descarga):
    motor, cargas, _ = motor_descarga
    motor.carregar()
    motor.descarregar()
    assert not motor.pronta
    wav = motor.falar("Oi.", 1.0)
    assert isinstance(wav, bytes) and len(wav) > 0
    # Recarregou sob demanda
    assert len(cargas) >= 2
    assert motor.pronta and motor.aquecida


def test_saude_separa_instalado_de_carregado(motor_descarga):
    """Rodada 2: /saude diz xtts=true (instalado) mesmo descarregado; xtts_carregado varia."""
    from fastapi.testclient import TestClient
    from vard_voz.servidor import criar_app

    motor, _, _ = motor_descarga
    motor.carregar()
    app = criar_app(
        motor=motor,
        motor_kokoro=None,
        motor_edge=None,
        motor_piper=None,
        carregar_em_thread=False,
    )
    with TestClient(app) as c:
        r = c.get("/saude", headers={"host": "127.0.0.1"})
        d = r.json()
        assert d["xtts"] is True
        assert d["xtts_carregado"] is True

        motor.descarregar()
        r2 = c.get("/saude", headers={"host": "127.0.0.1"})
        d2 = r2.json()
        # XTTS continua instalado (pode ser recarregado sob demanda)
        assert d2["xtts"] is True
        # Mas não está carregado agora
        assert d2["xtts_carregado"] is False


def test_recarga_nao_trava_com_rlock():
    """Rodada 2: _garantir_carregado chama carregar dentro do lock; RLock evita deadlock."""
    import threading
    from vard_voz.motor import Motor

    m = Motor(device="cpu", ocioso_s=0)
    assert isinstance(m._lock, type(threading.RLock())), "lock deve ser reentrante"

    # Simula estado descarregado
    m.pronta = False
    m._modelo = None

    class ModeloFalso:
        class SpeakerManager:
            speakers = {"Suad Qasim": {"gpt_cond_latent": b"g", "speaker_embedding": b"e"}}
        speaker_manager = SpeakerManager()
        def inference(self, *_a, **_k):
            return {"wav": [0.0] * 240}

    def carregar_sem_tts(self):
        self._modelo = ModeloFalso()
        self.pronta = True
        self.aquecida = True
        self._ultimo_uso = time.time()

    original = Motor.carregar
    Motor.carregar = carregar_sem_tts
    try:
        # Se fosse Lock simples, isso travaria aqui
        wav = m.falar("Teste.", 1.0)
        assert isinstance(wav, bytes) and len(wav) > 0
        assert m.pronta
    finally:
        Motor.carregar = original

def test_vozes_continuam_listadas_depois_da_descarga(motor_descarga):
    """A tela de Voz e /vozes não podem perder as vozes do XTTS só porque o modelo saiu da memória."""
    motor, _, _ = motor_descarga
    motor.carregar()
    antes = motor.vozes()
    motor.descarregar()
    assert motor._modelo is None
    assert motor.vozes() == antes
    assert motor.tem_voz("Suad Qasim")
