"""Áudio: conversão para o formato do whisper/silero (16 kHz mono int16) e captura WASAPI nas duas trilhas.

"eu" = microfone padrão; "outros" = loopback da saída padrão (PyAudioWPatch). Modo compartilhado sempre:
loopback não existe em modo exclusivo. O formato do stream é o do mixer (48 kHz, 2 canais, float32 em geral).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.signal import resample_poly

TAXA = 16000
log = logging.getLogger("vard_reuniao.audio")


def para_mono_16k(bloco: np.ndarray, taxa: int) -> np.ndarray:
    x = np.asarray(bloco, dtype=np.float32)
    if x.ndim == 2:
        if x.shape[1] > 2:          # surround: a media de todos os canais derruba o nivel; so frontal L/R
            x = x[:, :2]
        x = x.mean(axis=1)
    if int(taxa) != TAXA:
        g = np.gcd(int(taxa), TAXA)
        x = resample_poly(x, TAXA // g, int(taxa) // g).astype(np.float32)
    return np.clip(x * 32767.0, -32768, 32767).astype(np.int16)


@dataclass
class Dispositivos:
    eu_id: int
    eu_nome: str
    outros_id: int
    outros_nome: str
    taxa_eu: int
    taxa_outros: int
    canais_eu: int
    canais_outros: int

    def como_dict(self) -> dict:
        return {"eu": self.eu_nome, "outros": self.outros_nome}


def _normalizar(nome: str) -> str:
    """Normaliza FriendlyName para comparação: lowercase, trim, colapsa espaços."""
    return " ".join(str(nome).lower().split())


def _achar_por_nome(pa, kind: str, nome: str):
    """Busca dispositivo por FriendlyName normalizado; retorna info ou None se ambíguo/ausente."""
    if not nome:
        return None
    alvo = _normalizar(nome)
    try:
        n = pa.get_device_count()
    except Exception:  # noqa: BLE001
        return None
    achados = []
    for i in range(n):
        try:
            info = pa.get_device_info_by_index(i)
        except Exception:  # noqa: BLE001
            continue
        if kind == "input" and int(info.get("maxInputChannels", 0)) < 1:
            continue
        if kind == "loopback":
            # loopback é identificado pelo host API WASAPI e maxOutputChannels > 0
            try:
                import pyaudiowpatch
                if int(info.get("hostApi", -1)) != pa.get_host_api_info_by_type(pyaudiowpatch.paWASAPI)["index"]:
                    continue
            except (ImportError, OSError, KeyError, ValueError):
                continue
        if _normalizar(info.get("name", "")) == alvo:
            achados.append(info)
    if len(achados) == 1:
        return achados[0]
    return None  # ausente ou ambíguo → caller usa padrão


def dispositivos_com_preferencia(pa, microfone_nome: str = "", saida_nome: str = "") -> tuple[Dispositivos, dict]:
    """Resolve dispositivos pela preferência (FriendlyName); volta ao padrão com aviso se falhar."""
    avisos: dict[str, str] = {}
    lb = pa.get_default_wasapi_loopback()
    mic = None
    # Microfone preferido
    if microfone_nome:
        mic = _achar_por_nome(pa, "input", microfone_nome)
        if mic is None:
            avisos["microfone"] = f'"{microfone_nome}" não encontrado ou ambíguo; usando padrão.'
    if mic is None:
        try:
            import pyaudiowpatch
            wasapi = pa.get_host_api_info_by_type(pyaudiowpatch.paWASAPI)
            mic = pa.get_device_info_by_index(wasapi["defaultInputDevice"])
        except (ImportError, OSError, KeyError, ValueError):
            mic = None
    if mic is None:
        mic = pa.get_default_input_device_info()
    # Loopback da saída preferida
    if saida_nome:
        lb_pref = _achar_por_nome(pa, "loopback", saida_nome)
        if lb_pref is not None:
            lb = lb_pref
        else:
            avisos["saida"] = f'"{saida_nome}" não encontrada ou ambígua; usando loopback padrão.'
    return Dispositivos(
        eu_id=int(mic["index"]), eu_nome=str(mic["name"]), outros_id=int(lb["index"]), outros_nome=str(lb["name"]),
        taxa_eu=int(mic["defaultSampleRate"]), taxa_outros=int(lb["defaultSampleRate"]),
        canais_eu=max(1, int(mic["maxInputChannels"])), canais_outros=max(1, int(lb["maxInputChannels"])),
    ), avisos


def dispositivos_padrao(pa) -> Dispositivos:
    d, _ = dispositivos_com_preferencia(pa)
    return d


LOTE_BLOCOS = 5      # ~100 ms por trilha antes de reamostrar (o filtro sem estado erra na borda de blocos de 20 ms)


LACUNA_S = 0.2        # sem bloco por mais que 2 lotes: o que sobrou no lote parcial sai antes do audio novo


class Captura:
    """Dois streams WASAPI (callback). `ao_bloco(trilha, pcm16k_int16, t_monotonico)` roda na thread do PortAudio:
    deve ser rapido (enfileirar e voltar). Acumula LOTE_BLOCOS blocos por trilha; `t` e o do primeiro do lote."""

    def __init__(self, pa, dispositivos: Dispositivos, ao_bloco: Callable[[str, np.ndarray, float], None], bloco_ms: int = 20):
        self.pa, self.d, self.ao_bloco, self.bloco_ms = pa, dispositivos, ao_bloco, bloco_ms
        self.streams: dict[str, object] = {}
        self._lote: dict[str, list[np.ndarray]] = {}
        self._t_lote: dict[str, float] = {}
        self._t_ultimo: dict[str, float] = {}
        self._taxa: dict[str, int] = {}

    @property
    def ativa(self) -> bool:
        return bool(self.streams)

    def _despachar(self, trilha: str) -> None:
        blocos = self._lote.pop(trilha, [])
        t = self._t_lote.pop(trilha, 0.0)
        if blocos:
            self.ao_bloco(trilha, para_mono_16k(np.concatenate(blocos), self._taxa[trilha]), t)

    def _abrir(self, trilha: str, indice: int, taxa: int, canais: int):
        import pyaudiowpatch as pyaudio

        self._taxa[trilha] = taxa

        def cb(dados, quadros, info, status):
            try:
                x = np.frombuffer(dados, dtype=np.float32).reshape(-1, canais)
                agora = time.monotonic()
                if trilha in self._lote and agora - self._t_ultimo[trilha] > LACUNA_S:
                    self._despachar(trilha)      # lacuna (loopback mudo): o lote parcial sai com o proprio t
                if trilha not in self._lote:
                    self._lote[trilha] = []
                    self._t_lote[trilha] = agora
                self._t_ultimo[trilha] = agora
                self._lote[trilha].append(x.copy())
                if len(self._lote[trilha]) >= LOTE_BLOCOS:
                    self._despachar(trilha)
            except Exception:  # noqa: BLE001 - a thread do PortAudio nunca morre por erro nosso
                log.exception("bloco da trilha %s", trilha)
            return (None, pyaudio.paContinue)

        return self.pa.open(format=pyaudio.paFloat32, channels=canais, rate=taxa, input=True, input_device_index=indice,
                            frames_per_buffer=int(taxa * self.bloco_ms / 1000), stream_callback=cb)

    def abrir(self) -> None:
        self.streams["eu"] = self._abrir("eu", self.d.eu_id, self.d.taxa_eu, self.d.canais_eu)
        self.streams["outros"] = self._abrir("outros", self.d.outros_id, self.d.taxa_outros, self.d.canais_outros)
        for s in self.streams.values():
            s.start_stream()

    def fechar(self) -> None:
        for s in self.streams.values():
            try:
                s.stop_stream()
                s.close()
            except Exception:  # noqa: BLE001
                log.exception("fechar stream")
        self.streams.clear()
        for trilha in list(self._lote):          # sobra do ultimo lote
            try:
                self._despachar(trilha)
            except Exception:  # noqa: BLE001
                log.exception("sobra da trilha %s", trilha)
