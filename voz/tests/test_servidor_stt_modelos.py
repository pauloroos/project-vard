"""Rotas dos modelos de transcrição (/v1/stt/...): listar, baixar, progresso, apagar e trocar o ativo.

Download simulado no cache temporário; o STT é um dublê que só registra a troca.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from vard_voz.modelos_stt import GerenciadorModelos
from vard_voz.servidor import criar_app


class MotorAusente:
    pronta = False
    aquecida = False
    device = ""

    def carregar(self):
        return None

    def vozes(self):
        return []


class STTTroca:
    """STT falso com a interface usada pelas rotas novas (nome, device, compute e trocar)."""

    def __init__(self, modelo="base", device="cpu", compute_type="int8", falhar=False):
        self.modelo_nome = modelo
        self.device = device
        self.compute_type = compute_type
        self.pronta = True
        self.falhar = falhar
        self.trocas: list[tuple] = []

    def carregar(self):
        self.pronta = True

    def trocar(self, modelo, device, compute_type):
        self.trocas.append((modelo, device, compute_type))
        if self.falhar:
            raise RuntimeError("CUDA indisponível")
        self.modelo_nome, self.device, self.compute_type = modelo, device, compute_type

    def transcrever_bytes(self, audio, idioma=None):
        return "ok", 1.0


def baixador_falso(repo, cache):
    pasta = cache / ("models--" + repo.replace("/", "--"))
    (pasta / "blobs").mkdir(parents=True, exist_ok=True)
    (pasta / "blobs" / "x").write_bytes(b"\0" * 10)
    (pasta / "snapshots" / "r").mkdir(parents=True, exist_ok=True)
    (pasta / "snapshots" / "r" / "model.bin").write_bytes(b"\0" * 10)


@pytest.fixture
def ambiente(tmp_path):
    stt = STTTroca()
    modelos = GerenciadorModelos(cache=tmp_path, baixador=baixador_falso, em_thread=False)
    app = criar_app(MotorAusente(), motor_kokoro=None, motor_edge=None, motor_piper=None,
                    stt=stt, modelos_stt=modelos, carregar_em_thread=False)
    return TestClient(app, base_url="http://127.0.0.1:4710"), stt, modelos


def test_lista_modelos_com_estado_e_ativo(ambiente):
    c, stt, modelos = ambiente
    modelos.baixar("base")
    r = c.get("/v1/stt/modelos")
    assert r.status_code == 200
    d = r.json()
    assert d["ativo"] == "base" and d["device"] == "cpu" and d["pronta"] is True
    assert d["carregando"] is False and d["erro"] is None
    por_id = {m["id"]: m for m in d["modelos"]}
    assert por_id["base"]["baixado"] is True and por_id["base"]["ativo"] is True
    assert por_id["small"]["baixado"] is False and por_id["small"]["ativo"] is False
    assert por_id["distil-large-v3"]["idioma"] == "ingles"


def test_ativo_por_apelido_do_faster_whisper(tmp_path):
    stt = STTTroca(modelo="turbo")
    app = criar_app(MotorAusente(), motor_kokoro=None, motor_edge=None, motor_piper=None, stt=stt,
                    modelos_stt=GerenciadorModelos(cache=tmp_path, em_thread=False), carregar_em_thread=False)
    d = TestClient(app, base_url="http://127.0.0.1:4710").get("/v1/stt/modelos").json()
    assert d["ativo"] == "large-v3-turbo"


def test_baixar_e_consultar_progresso(ambiente):
    c, _, modelos = ambiente
    r = c.post("/v1/stt/modelos/small/baixar")
    assert r.status_code == 202
    assert r.json()["estado"] == "concluido"
    p = c.get("/v1/stt/modelos/small/progresso").json()
    assert p["estado"] == "concluido" and p["porcentagem"] == 100
    assert modelos.baixado("small")


def test_baixar_modelo_desconhecido_404(ambiente):
    c, _, _ = ambiente
    assert c.post("/v1/stt/modelos/gigante/baixar").status_code == 404
    assert c.get("/v1/stt/modelos/gigante/progresso").status_code == 404
    assert c.post("/v1/stt/modelos/gigante/apagar").status_code == 404


def test_ativar_modelo_baixado_troca_e_informa(ambiente):
    c, stt, modelos = ambiente
    modelos.baixar("small")
    r = c.post("/v1/stt/ativar", json={"modelo": "small", "dispositivo": "cuda"})
    assert r.status_code == 202
    assert stt.trocas == [("small", "cuda", "float16")]
    d = c.get("/v1/stt/modelos").json()
    assert d["ativo"] == "small" and d["dispositivo"] == "cuda" and d["carregando"] is False


def test_ativar_sem_dispositivo_mantem_o_atual(ambiente):
    c, stt, modelos = ambiente
    modelos.baixar("tiny")
    assert c.post("/v1/stt/ativar", json={"modelo": "tiny"}).status_code == 202
    assert stt.trocas == [("tiny", "cpu", "int8")]


def test_ativar_so_dispositivo_recarrega_o_mesmo_modelo(ambiente):
    c, stt, modelos = ambiente
    modelos.baixar("base")
    assert c.post("/v1/stt/ativar", json={"dispositivo": "auto"}).status_code == 202
    assert stt.trocas == [("base", "auto", "auto")]


def test_ativar_modelo_nao_baixado_409(ambiente):
    c, stt, _ = ambiente
    r = c.post("/v1/stt/ativar", json={"modelo": "medium"})
    assert r.status_code == 409 and r.json()["erro"] == "modelo_nao_baixado"
    assert stt.trocas == []


def test_ativar_valores_invalidos(ambiente):
    c, stt, modelos = ambiente
    modelos.baixar("small")
    assert c.post("/v1/stt/ativar", json={"modelo": "small", "dispositivo": "tpu"}).status_code == 400
    assert c.post("/v1/stt/ativar", json={"modelo": "inexistente"}).status_code == 404
    assert stt.trocas == []


def test_ativar_que_falha_fica_registrado_sem_derrubar(ambiente):
    c, stt, modelos = ambiente
    stt.falhar = True
    modelos.baixar("small")
    assert c.post("/v1/stt/ativar", json={"modelo": "small", "dispositivo": "cuda"}).status_code == 202
    d = c.get("/v1/stt/modelos").json()
    assert d["ativo"] == "base" and "CUDA" in d["erro"]
    # O serviço continua transcrevendo com o modelo anterior.
    assert c.post("/v1/speech/transcribe", content=b"RIFF").json()["text"] == "ok"


def test_sem_stt_ativar_503_e_lista_continua(tmp_path, monkeypatch):
    import vard_voz.servidor as servidor

    def sem_stt(**_):
        raise RuntimeError("extra stt ausente")

    monkeypatch.setattr(servidor, "MotorSTT", sem_stt)
    app = criar_app(MotorAusente(), motor_kokoro=None, motor_edge=None, motor_piper=None,
                    modelos_stt=GerenciadorModelos(cache=tmp_path, em_thread=False), carregar_em_thread=False)
    c = TestClient(app, base_url="http://127.0.0.1:4710")
    assert c.post("/v1/stt/ativar", json={"modelo": "base"}).status_code == 503
    d = c.get("/v1/stt/modelos").json()
    assert d["ativo"] == "" and d["pronta"] is False and len(d["modelos"]) >= 7


def test_apagar_baixado_e_recusar_o_ativo(ambiente):
    c, _, modelos = ambiente
    modelos.baixar("base")
    modelos.baixar("small")
    r = c.post("/v1/stt/modelos/base/apagar")
    assert r.status_code == 409 and r.json()["erro"] == "modelo_em_uso"
    assert modelos.baixado("base")
    assert c.post("/v1/stt/modelos/small/apagar").status_code == 200
    assert not modelos.baixado("small")


def test_rotas_novas_respeitam_a_guarda_de_origem(ambiente):
    c, _, _ = ambiente
    r = c.post("/v1/stt/modelos/small/baixar", headers={"Origin": "http://exemplo.invalid"})
    assert r.status_code == 403


def test_sem_stt_injetado_usa_a_escolha_do_hud(tmp_path, monkeypatch):
    (tmp_path / "hud.config.json").write_text(json.dumps({"stt_modelo": "small", "stt_dispositivo": "cpu"}), encoding="utf-8")
    monkeypatch.setenv("VARD_HUD_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("VARD_STT_MODEL", "large-v3")
    monkeypatch.setenv("VARD_STT_DEVICE", "cuda")
    app = criar_app(MotorAusente(), motor_kokoro=None, motor_edge=None, motor_piper=None,
                    modelos_stt=GerenciadorModelos(cache=tmp_path / "cache", em_thread=False), carregar_em_thread=False)
    d = TestClient(app, base_url="http://127.0.0.1:4710").get("/v1/stt/modelos").json()
    assert (d["ativo"], d["device"], d["dispositivo"]) == ("small", "cpu", "cpu")


def test_sem_hud_as_variaveis_continuam_valendo(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_HUD_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("VARD_STT_MODEL", "large-v3-turbo")
    monkeypatch.setenv("VARD_STT_DEVICE", "cuda")
    app = criar_app(MotorAusente(), motor_kokoro=None, motor_edge=None, motor_piper=None,
                    modelos_stt=GerenciadorModelos(cache=tmp_path / "cache", em_thread=False), carregar_em_thread=False)
    d = TestClient(app, base_url="http://127.0.0.1:4710").get("/v1/stt/modelos").json()
    assert (d["ativo"], d["device"]) == ("large-v3-turbo", "cuda")
