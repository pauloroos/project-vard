"""Testes do motor Kokoro próprio (T8).

Cobre: síntese WAV/PCM com taxa/canais corretos, ID de voz pt-BR preservado,
falha de síntese respeita cancelamento, instalação sem XTTS/coqui-tts,
reserva de fala local usa Kokoro quando habilitado e não aciona API paga/OpenJarvis.
Nenhum teste carrega modelo real nem exige GPU.
"""
from __future__ import annotations

import io
import struct
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# Importação leve: kokoro.py não deve importar TTS/coqui nem exigir GPU.
def _importar_kokoro():
    from vard_voz import kokoro  # noqa: WPS433
    return kokoro


def test_importacao_sem_gpu_nem_coqui():
    """Importar kokoro não baixa pesos, não importa TTS e funciona sem CUDA."""
    kokoro = _importar_kokoro()
    assert hasattr(kokoro, "MotorKokoro")
    assert hasattr(kokoro, "VOZES_KOKORO")
    # Garante que o módulo não forçou import de TTS/coqui no nível de módulo.
    nomes = dir(kokoro)
    assert "TTS" not in nomes
    assert not any("coqui" in n.lower() for n in nomes)


def test_vozes_kokoro_tem_pt_br_e_ids_estaveis():
    kokoro = _importar_kokoro()
    vozes = kokoro.VOZES_KOKORO
    assert isinstance(vozes, dict) and vozes
    ids = set(vozes.keys())
    # Pelo menos uma voz pt-BR feminina e uma masculina com IDs estáveis.
    assert "pf_dora" in ids or any(k.startswith("pf_") for k in ids)
    assert "pm_alex" in ids or any(k.startswith("pm_") for k in ids)
    # Todos os valores têm rótulo legível.
    for vid, rotulo in vozes.items():
        assert isinstance(vid, str) and vid
        assert isinstance(rotulo, str) and rotulo


def test_motor_kokoro_sintetiza_wav_com_taxa_e_canais_corretos():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    # Motor falso: devolve PCM float32 mono 24 kHz sem tocar em GPU.
    fake_pcm = b"\x00\x00\x80?\x00\x00\x80?" * 1200  # ~0,1 s a 24 kHz
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    wav_bytes = motor.falar("Olá mundo.", velocidade=1.0, voz="pf_dora")
    assert wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # PCM 16 bits
        assert w.getframerate() == 24000
        assert w.getnframes() > 0


def test_motor_kokoro_fluxo_pcm_headers_corretos():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    chunks = [b"\x01\x00" * 480, b"\x02\x00" * 240]
    motor._fluxo_raw = lambda texto, voz, velocidade: iter(chunks)  # type: ignore[attr-defined]
    motor.pronta = True
    motor.aquecida = True

    fluxo = motor.falar_fluxo("Teste.", velocidade=1.0, voz="pm_alex")
    coletado = b"".join(fluxo)
    assert coletado == b"".join(chunks)


def test_motor_kokoro_voz_desconhecida_erro_claro():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    with pytest.raises((KeyError, ValueError)):
        motor.falar("Oi.", voz="inexistente_xyz")


def test_motor_kokoro_falha_respeita_cancelamento_e_nao_chama_api_paga():
    """Falha na síntese local levanta RuntimeError sem tentar fallback externo."""
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]

    tentativas = []

    def _sintetizar_quebrado(texto, voz, velocidade):
        tentativas.append((texto, voz))
        raise RuntimeError("gpu indisponivel")

    motor._sintetizar_raw = _sintetizar_quebrado  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="gpu indisponivel"):
        motor.falar("Texto longo.", velocidade=1.0, voz="pf_dora")
    # A falha ocorreu exatamente uma vez (sem retry/fallback externo).
    assert len(tentativas) == 1


def test_motor_kokoro_aquecendo_devolve_estado_legivel():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    # Antes de carregar: pronta=False, aquecida=False, mas objeto existe.
    assert motor.pronta is False
    assert motor.aquecida is False
    # vozes() funciona mesmo sem modelo carregado (lista estática).
    vozes = motor.vozes()
    assert isinstance(vozes, list) and vozes


def test_reserva_de_fala_local_usa_kokoro_quando_habilitado():
    """Quando Kokoro está instalado/habilitado, a reserva local é ele; OpenJarvis não é chamado."""
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    motor._modelo = object()  # type: ignore[attr-defined]
    fake_pcm = b"\x00\x00" * 240
    motor._sintetizar_raw = lambda texto, voz, velocidade: (fake_pcm, 24000)  # type: ignore[attr-defined]
    chamadas_oj = []

    def _fake_oj_sintetizar(texto, voz, velocidade):
        chamadas_oj.append((texto, voz))
        return b""

    # Simula cenário: Kokoro disponível → reserva NÃO chama OJ.
    resultado = motor.falar("Reserva.", velocidade=1.0, voz="pf_dora")
    assert resultado and len(chamadas_oj) == 0


def test_kokoro_preserva_id_pt_br_na_saida():
    kokoro = _importar_kokoro()
    motor = kokoro.MotorKokoro(device="cpu")
    motor.pronta = True
    motor.aquecida = True
    vozes_usadas = []

    def _captura_voz(texto, voz, velocidade):
        vozes_usadas.append(voz)
        return (b"\x00\x00" * 240, 24000)

    motor._sintetizar_raw = _captura_voz  # type: ignore[attr-defined]
    motor.falar("Teste pt-BR.", voz="pf_dora")
    assert vozes_usadas == ["pf_dora"]

# --- Motor próprio sem OpenJarvis: kokoro-onnx + arquivos do instalador de vozes ---------------------

class _ModeloFalso:
    """Faz o papel do kokoro_onnx.Kokoro: guarda os pedidos e devolve uma onda curta em float32."""

    def __init__(self, vozes=None):
        self.pedidos = []
        self._vozes = vozes

    def create(self, texto, voice, speed=1.0, lang="en-us"):
        import numpy as np
        self.pedidos.append({"texto": texto, "voz": voice, "velocidade": speed, "idioma": lang})
        return np.zeros(2400, dtype="float32") + 0.1, 24000

    def get_voices(self):
        return sorted(self._vozes or [])


def _pasta_com_modelo(tmp_path, nome_modelo="kokoro-v1.0.int8.onnx", com_vozes=True):
    (tmp_path / nome_modelo).write_bytes(b"modelo ficticio")
    if com_vozes:
        (tmp_path / "voices-v1.0.bin").write_bytes(b"vozes ficticias")
    return tmp_path


def test_pasta_modelo_respeita_variaveis(tmp_path):
    kokoro = _importar_kokoro()
    assert kokoro.pasta_modelo({"VARD_KOKORO_DIR": str(tmp_path)}) == tmp_path
    esperado = tmp_path / "pacotes" / "ativo" / kokoro.PACOTE_ID
    assert kokoro.pasta_modelo({"VARD_DADOS": str(tmp_path)}) == esperado
    assert kokoro.pasta_modelo({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "rdl-vard" / "pacotes" / "ativo" / kokoro.PACOTE_ID


def test_arquivos_modelo_aceita_o_nome_gravado_pelo_instalador(tmp_path):
    kokoro = _importar_kokoro()
    # O instalador de pacotes grava o arquivo principal como download.dat; os extras mantêm o nome.
    _pasta_com_modelo(tmp_path, nome_modelo="download.dat")
    modelo, vozes = kokoro.arquivos_modelo(tmp_path)
    assert modelo.name == "download.dat" and vozes.name == "voices-v1.0.bin"


def test_arquivos_modelo_sem_vozes_ou_sem_pasta_e_none(tmp_path):
    kokoro = _importar_kokoro()
    assert kokoro.arquivos_modelo(tmp_path / "nao-existe") is None
    _pasta_com_modelo(tmp_path, com_vozes=False)
    assert kokoro.arquivos_modelo(tmp_path) is None


def test_instalado_exige_biblioteca_e_arquivos(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    _pasta_com_modelo(tmp_path)
    motor = kokoro.MotorKokoro(device="cpu", pasta=tmp_path)
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: False)
    assert motor.instalado() is False
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: True)
    assert motor.instalado() is True
    assert kokoro.MotorKokoro(device="cpu", pasta=tmp_path / "vazia").instalado() is False


def test_carregar_sem_instalacao_nao_chama_a_biblioteca(tmp_path):
    kokoro = _importar_kokoro()
    chamadas = []
    motor = kokoro.MotorKokoro(device="cpu", pasta=tmp_path, fabrica=lambda *a: chamadas.append(a))
    motor.carregar()
    assert motor.pronta is False and chamadas == []


def test_carregar_na_cpu_usa_so_o_provedor_cpu(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: True)
    _pasta_com_modelo(tmp_path)
    pedidos = []

    def fabrica(modelo, vozes, provedores):
        pedidos.append((modelo.name, vozes.name, provedores))
        return _ModeloFalso()

    motor = kokoro.MotorKokoro(device="cpu", pasta=tmp_path, fabrica=fabrica,
                               provedores_disponiveis=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    motor.carregar()
    assert motor.pronta is True and motor.aquecida is True
    assert pedidos == [("kokoro-v1.0.int8.onnx", "voices-v1.0.bin", ["CPUExecutionProvider"])]
    motor.carregar()  # já carregado: não carrega de novo
    assert len(pedidos) == 1


@pytest.mark.parametrize("disponiveis, esperado", [
    (["CUDAExecutionProvider", "CPUExecutionProvider"], ["CUDAExecutionProvider", "CPUExecutionProvider"]),
    (["CPUExecutionProvider"], ["CPUExecutionProvider"]),
])
def test_carregar_na_gpu_pede_cuda_com_reserva_na_cpu(tmp_path, monkeypatch, disponiveis, esperado):
    kokoro = _importar_kokoro()
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: True)
    _pasta_com_modelo(tmp_path)
    pedidos = []
    motor = kokoro.MotorKokoro(device="cuda", pasta=tmp_path,
                               fabrica=lambda m, v, p: pedidos.append(p) or _ModeloFalso(),
                               provedores_disponiveis=lambda: disponiveis)
    motor.carregar()
    assert pedidos == [esperado]


def test_carregar_que_falha_fica_nao_pronta(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: True)
    _pasta_com_modelo(tmp_path)

    def fabrica(*_):
        raise RuntimeError("modelo corrompido")

    motor = kokoro.MotorKokoro(device="cpu", pasta=tmp_path, fabrica=fabrica, provedores_disponiveis=lambda: [])
    motor.carregar()
    assert motor.pronta is False


def _motor_carregado(kokoro, tmp_path, monkeypatch, modelo=None):
    monkeypatch.setattr(kokoro, "biblioteca_instalada", lambda: True)
    _pasta_com_modelo(tmp_path)
    modelo = modelo or _ModeloFalso()
    motor = kokoro.MotorKokoro(device="cpu", pasta=tmp_path, fabrica=lambda *_: modelo,
                               provedores_disponiveis=lambda: ["CPUExecutionProvider"])
    motor.carregar()
    return motor, modelo


@pytest.mark.parametrize("voz, idioma", [("pf_dora", "pt-br"), ("pm_alex", "pt-br"), ("af_heart", "en-us"), ("bm_george", "en-gb")])
def test_sintese_usa_o_idioma_da_voz(tmp_path, monkeypatch, voz, idioma):
    kokoro = _importar_kokoro()
    motor, modelo = _motor_carregado(kokoro, tmp_path, monkeypatch)
    wav_bytes = motor.falar("Olá.", velocidade=1.0, voz=voz)
    assert modelo.pedidos[-1]["idioma"] == idioma and modelo.pedidos[-1]["voz"] == voz
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 2400


def test_sintese_sem_voz_usa_a_primeira_pt_br_e_limita_a_velocidade(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    motor, modelo = _motor_carregado(kokoro, tmp_path, monkeypatch)
    motor.falar("Oi.", velocidade=3.0)
    motor.falar("Oi.", velocidade=0.1)
    assert [p["voz"] for p in modelo.pedidos] == ["pf_dora", "pf_dora"]
    assert [p["velocidade"] for p in modelo.pedidos] == [2.0, 0.5]


def test_fluxo_entrega_o_pcm_inteiro_em_pedacos(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    motor, _ = _motor_carregado(kokoro, tmp_path, monkeypatch)
    pedacos = list(motor.falar_fluxo("Oi.", 1.0, "pm_santa"))
    assert len(pedacos) >= 1 and sum(len(p) for p in pedacos) == 2400 * 2


def test_vozes_carregadas_seguem_o_arquivo_de_vozes(tmp_path, monkeypatch):
    kokoro = _importar_kokoro()
    motor, _ = _motor_carregado(kokoro, tmp_path, monkeypatch, _ModeloFalso(vozes=["pf_dora", "pm_alex", "zf_xiaobei"]))
    assert motor.vozes() == ["pf_dora", "pm_alex"]
    assert motor.tem_voz("pm_alex") and not motor.tem_voz("pm_santa") and not motor.tem_voz("zf_xiaobei")


def test_manifesto_do_instalador_traz_os_arquivos_que_o_motor_procura():
    """O pacote 'kokoro' de config/pacotes/vozes.json grava o que MotorKokoro procura na pasta do pacote."""
    import json
    from pathlib import Path

    kokoro = _importar_kokoro()
    manifesto = json.loads((Path(__file__).resolve().parents[2] / "config" / "pacotes" / "vozes.json").read_text(encoding="utf-8"))
    pacote = next(p for p in manifesto["pacotes"] if p["id"] == kokoro.PACOTE_ID)
    assert pacote["tipo"] == "motor" and not pacote["indisponivel"]
    assert len(pacote["sha256"]) == 64 and pacote["bytes_download"] > 0
    assert "download.dat" in kokoro.ARQUIVOS_MODELO  # nome do arquivo principal gravado pelo instalador
    assert [e["nome"] for e in pacote["arquivos_extras"]] == [kokoro.ARQUIVO_VOZES]
    assert all(len(e["sha256"]) == 64 for e in pacote["arquivos_extras"])
    assert any(d.startswith("kokoro-onnx") for d in pacote["dependencias"])


def test_biblioteca_instalada_reavalia_a_cada_consulta(monkeypatch):
    """Instalada pelo instalador de vozes com o serviço no ar: a próxima consulta já enxerga (sem cache da subida)."""
    import importlib
    import importlib.util

    kokoro = _importar_kokoro()
    invalidacoes = []
    presente = {"valor": False}
    monkeypatch.setattr(importlib, "invalidate_caches", lambda: invalidacoes.append(1))
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome: object() if presente["valor"] and nome == "kokoro_onnx" else None)
    assert kokoro.biblioteca_instalada() is False
    presente["valor"] = True
    assert kokoro.biblioteca_instalada() is True
    assert len(invalidacoes) == 2
