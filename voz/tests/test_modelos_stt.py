"""Catálogo, cache e escolha dos modelos de transcrição (aba Transcrição).

Download sempre simulado: o baixador falso grava arquivos pequenos no cache temporário,
no mesmo formato de pastas do Hugging Face. Nada de rede, modelo real nem GPU.
"""
from __future__ import annotations

import json
import sys
import threading
import types

import pytest

from vard_voz.modelos_stt import (
    CATALOGO,
    GerenciadorModelos,
    configuracao_stt,
    ler_escolha_hud,
)
from vard_voz.transcricao import MotorSTT


def baixador_falso(bytes_modelo: int = 1000):
    """Grava blobs + snapshots/<rev>/model.bin como o snapshot_download faria."""
    def baixar(repo: str, cache):
        pasta = cache / ("models--" + repo.replace("/", "--"))
        (pasta / "blobs").mkdir(parents=True, exist_ok=True)
        (pasta / "blobs" / "abc").write_bytes(b"\0" * bytes_modelo)
        snap = pasta / "snapshots" / "rev1"
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "model.bin").write_bytes(b"\0" * bytes_modelo)
        (snap / "config.json").write_text("{}")
    return baixar


def test_catalogo_tem_os_modelos_conhecidos_com_metadados():
    ids = [m.id for m in CATALOGO]
    for esperado in ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3"):
        assert esperado in ids
    for m in CATALOGO:
        assert m.repo and "/" in m.repo
        assert m.tamanho_mb > 0
        assert m.idioma in ("multilingue", "ingles")
        assert 1 <= m.velocidade <= 5 and 1 <= m.precisao <= 5
        assert m.descricao
    distil = next(m for m in CATALOGO if m.id == "distil-large-v3")
    assert distil.idioma == "ingles"


def test_cache_vazio_nada_baixado(tmp_path):
    g = GerenciadorModelos(cache=tmp_path, em_thread=False)
    assert g.baixado("small") is False
    lista = g.listar()
    assert {m["id"] for m in lista} == {m.id for m in CATALOGO}
    assert all(m["baixado"] is False for m in lista)
    assert g.progresso("small")["estado"] == "parado"


def test_baixar_grava_no_cache_e_marca_baixado(tmp_path):
    g = GerenciadorModelos(cache=tmp_path, baixador=baixador_falso(), em_thread=False)
    estado = g.baixar("small")
    assert estado["estado"] == "concluido"
    assert g.baixado("small") is True
    assert (tmp_path / "models--Systran--faster-whisper-small" / "snapshots" / "rev1" / "model.bin").is_file()
    item = next(m for m in g.listar() if m["id"] == "small")
    assert item["baixado"] is True and item["progresso"]["estado"] == "concluido"


def test_baixar_ja_baixado_nao_baixa_de_novo(tmp_path):
    chamadas = []
    falso = baixador_falso()

    def contar(repo, cache):
        chamadas.append(repo)
        falso(repo, cache)

    g = GerenciadorModelos(cache=tmp_path, baixador=contar, em_thread=False)
    g.baixar("tiny")
    g.baixar("tiny")
    assert len(chamadas) == 1


def test_progresso_durante_download_em_thread(tmp_path):
    liberar = threading.Event()
    gravou = threading.Event()

    def lento(repo, cache):
        pasta = cache / ("models--" + repo.replace("/", "--")) / "blobs"
        pasta.mkdir(parents=True)
        (pasta / "parcial.incomplete").write_bytes(b"\0" * 5_000_000)
        gravou.set()
        liberar.wait(5)
        baixador_falso()(repo, cache)

    g = GerenciadorModelos(cache=tmp_path, baixador=lento)
    assert g.baixar("tiny")["estado"] == "baixando"
    assert gravou.wait(5)
    p = g.progresso("tiny")
    assert p["estado"] == "baixando"
    assert p["bytes"] >= 5_000_000 and p["total"] > 0
    assert 0 < p["porcentagem"] < 100
    # Pedir de novo enquanto baixa não abre outro download.
    assert g.baixar("tiny")["estado"] == "baixando"
    with pytest.raises(RuntimeError):
        g.apagar("tiny")
    liberar.set()
    g.esperar("tiny", 5)
    assert g.progresso("tiny")["estado"] == "concluido"
    assert g.progresso("tiny")["porcentagem"] == 100


def test_falha_no_download_vira_estado_falhou(tmp_path):
    def quebra(repo, cache):
        raise OSError("sem rede")

    g = GerenciadorModelos(cache=tmp_path, baixador=quebra, em_thread=False)
    estado = g.baixar("base")
    assert estado["estado"] == "falhou"
    assert "sem rede" in estado["erro"]
    assert g.baixado("base") is False


def test_modelo_desconhecido(tmp_path):
    g = GerenciadorModelos(cache=tmp_path, em_thread=False)
    with pytest.raises(KeyError):
        g.baixar("gigante-v9")
    with pytest.raises(KeyError):
        g.apagar("gigante-v9")


def test_apagar_remove_do_cache(tmp_path):
    g = GerenciadorModelos(cache=tmp_path, baixador=baixador_falso(), em_thread=False)
    g.baixar("medium")
    assert g.baixado("medium")
    g.apagar("medium")
    assert g.baixado("medium") is False
    assert not (tmp_path / "models--Systran--faster-whisper-medium").exists()
    assert g.progresso("medium")["estado"] == "parado"
    g.apagar("medium")  # apagar o que não existe não é erro


def test_apelidos_do_faster_whisper_apontam_para_o_catalogo(tmp_path):
    g = GerenciadorModelos(cache=tmp_path, em_thread=False)
    assert g.normalizar("turbo") == "large-v3-turbo"
    assert g.normalizar("large") == "large-v3"
    assert g.normalizar("small") == "small"
    assert g.normalizar("pasta/qualquer") == "pasta/qualquer"


# --- escolha: hud.config.json com prioridade sobre as variáveis ---

def test_configuracao_sem_nada_usa_o_padrao_antigo():
    c = configuracao_stt({}, {})
    assert (c["modelo"], c["device"], c["compute"]) == ("base", "cpu", "int8")


def test_configuracao_so_com_variaveis_mantem_o_comportamento_atual():
    env = {"VARD_STT_MODEL": "large-v3-turbo", "VARD_STT_DEVICE": "cuda", "VARD_STT_COMPUTE": "float16"}
    c = configuracao_stt({}, env)
    assert (c["modelo"], c["device"], c["compute"]) == ("large-v3-turbo", "cuda", "float16")
    assert c["dispositivo"] == "cuda"


def test_configuracao_do_hud_ganha_das_variaveis():
    env = {"VARD_STT_MODEL": "large-v3-turbo", "VARD_STT_DEVICE": "cuda", "VARD_STT_COMPUTE": "float16"}
    c = configuracao_stt({"stt_modelo": "small", "stt_dispositivo": "cpu"}, env)
    assert (c["modelo"], c["device"], c["compute"], c["dispositivo"]) == ("small", "cpu", "int8", "cpu")


def test_configuracao_dispositivo_automatico_e_gpu():
    assert configuracao_stt({"stt_dispositivo": "auto"}, {})[("device")] == "auto"
    assert configuracao_stt({"stt_dispositivo": "auto"}, {})["compute"] == "auto"
    c = configuracao_stt({"stt_dispositivo": "cuda"}, {"VARD_STT_COMPUTE": "int8"})
    assert (c["device"], c["compute"]) == ("cuda", "float16")


def test_configuracao_ignora_valor_invalido_do_hud():
    env = {"VARD_STT_MODEL": "medium", "VARD_STT_DEVICE": "cuda"}
    c = configuracao_stt({"stt_modelo": "", "stt_dispositivo": "tpu"}, env)
    assert (c["modelo"], c["device"]) == ("medium", "cuda")
    c = configuracao_stt({"stt_modelo": 7}, env)
    assert c["modelo"] == "medium"


def test_ler_escolha_hud_pela_pasta_informada(tmp_path, monkeypatch):
    (tmp_path / "hud.config.json").write_text(json.dumps({"stt_modelo": "tiny", "stt_dispositivo": "cpu", "nome": "teste"}), encoding="utf-8")
    monkeypatch.setenv("VARD_HUD_CONFIG_DIR", str(tmp_path))
    assert ler_escolha_hud() == {"stt_modelo": "tiny", "stt_dispositivo": "cpu"}


def test_ler_escolha_hud_ausente_ou_invalido(tmp_path, monkeypatch):
    monkeypatch.setenv("VARD_HUD_CONFIG_DIR", str(tmp_path))
    assert ler_escolha_hud() == {}
    (tmp_path / "hud.config.json").write_text("{quebrado", encoding="utf-8")
    assert ler_escolha_hud() == {}
    (tmp_path / "hud.config.json").write_text("[1, 2]", encoding="utf-8")
    assert ler_escolha_hud() == {}


# --- troca do modelo carregado, sem derrubar o serviço ---

@pytest.fixture
def whisper_falso(monkeypatch):
    """faster_whisper falso: registra cada carga e pode falhar para um modelo."""
    cargas: list[tuple] = []
    falhar = set()

    class WhisperModel:
        def __init__(self, nome, device="cpu", compute_type="int8"):
            if nome in falhar:
                raise RuntimeError(f"falhou {nome}")
            cargas.append((nome, device, compute_type))
            self.nome = nome

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return cargas, falhar


def test_trocar_recarrega_com_o_novo_modelo(whisper_falso):
    cargas, _ = whisper_falso
    m = MotorSTT(modelo="base", device="cpu", compute_type="int8")
    m.carregar()
    m.trocar("small", "cuda", "float16")
    assert m.pronta
    assert (m.modelo_nome, m.device, m.compute_type) == ("small", "cuda", "float16")
    assert m._modelo.nome == "small"
    assert cargas == [("base", "cpu", "int8"), ("small", "cuda", "float16")]


def test_trocar_que_falha_volta_ao_modelo_anterior(whisper_falso):
    cargas, falhar = whisper_falso
    m = MotorSTT(modelo="base")
    m.carregar()
    falhar.add("large-v3")
    with pytest.raises(RuntimeError, match="falhou large-v3"):
        m.trocar("large-v3", "cuda", "float16")
    assert m.modelo_nome == "base" and m.pronta
    assert m._modelo.nome == "base"


def test_carregar_duas_vezes_carrega_uma(whisper_falso):
    cargas, _ = whisper_falso
    m = MotorSTT(modelo="tiny")
    m.carregar()
    m.carregar()
    assert len(cargas) == 1
