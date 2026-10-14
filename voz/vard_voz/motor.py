"""Motor XTTS v2: uma voz fixa (Suad Qasim), uma síntese por vez."""
from __future__ import annotations

import io
import logging
import os
import threading
import time

import numpy as np
import soundfile as sf

log = logging.getLogger("vard_voz")

VOZ = "Suad Qasim"
IDIOMA = "pt"
TEMPERATURA = 0.65
PENALIDADE = 5.0
TAXA = 24000
MODELO = "tts_models/multilingual/multi-dataset/xtts_v2"


def para_wav(onda, taxa: int = TAXA) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.asarray(onda, dtype="float32").squeeze(), taxa, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Motor:
    def __init__(self, device: str = "cuda") -> None:
        self.device = device
        self.pronta = False
        self.aquecida = False
        self._lock = threading.Lock()
        self._modelo = None
        self._cache: dict[str, tuple] = {}

    def vozes(self) -> list[str]:
        nomes = sorted(self._modelo.speaker_manager.speakers) if self._modelo is not None else [VOZ]
        return [VOZ, *[n for n in nomes if n != VOZ]]

    def tem_voz(self, nome: str) -> bool:
        return self._modelo is not None and nome in self._modelo.speaker_manager.speakers

    def _latentes(self, voz: str | None):
        nome = voz or VOZ
        if nome not in self._cache:
            v = self._modelo.speaker_manager.speakers[nome]  # KeyError se a voz não existe
            self._cache[nome] = (v["gpt_cond_latent"], v["speaker_embedding"])
        return self._cache[nome]

    def carregar(self) -> None:
        os.environ["COQUI_TOS_AGREED"] = "1"
        from . import sfpatch  # noqa: F401  (antes do TTS)
        from TTS.api import TTS

        t0 = time.time()
        tts = TTS(MODELO).to(self.device)
        self._modelo = tts.synthesizer.tts_model
        self._latentes(VOZ)
        self.pronta = True
        self.falar("Pronta.", 1.0)
        self.aquecida = True
        log.info("motor carregado em %.1fs (device=%s)", time.time() - t0, self.device)

    def falar(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> bytes:
        gpt, emb = self._latentes(voz)
        with self._lock:
            t0 = time.time()
            saida = self._modelo.inference(
                texto, IDIOMA, gpt, emb,
                temperature=TEMPERATURA, repetition_penalty=PENALIDADE, speed=velocidade,
            )
            wav = para_wav(saida["wav"])
            log.info("sintese chars=%d seg=%.2f device=%s voz=%s", len(texto), time.time() - t0, self.device, voz or VOZ)
            return wav

    def falar_fluxo(self, texto: str, velocidade: float = 1.0, voz: str | None = None):
        """Gera PCM16 mono 24 kHz em pedaços; segura o lock até o fim (ou até o gerador ser fechado).

        Os latentes são resolvidos já na chamada (voz inexistente = KeyError antes de qualquer fluxo)."""
        gpt, emb = self._latentes(voz)
        return self._fluxo(texto, velocidade, voz, gpt, emb)

    def _fluxo(self, texto, velocidade, voz, gpt, emb):
        with self._lock:
            t0 = time.time()
            primeiro = None
            try:
                for pedaco in self._modelo.inference_stream(
                    texto, IDIOMA, gpt, emb,
                    stream_chunk_size=20, enable_text_splitting=False,
                    temperature=TEMPERATURA, repetition_penalty=PENALIDADE, speed=velocidade,
                ):
                    onda = np.clip(pedaco.detach().cpu().numpy().astype("float32").squeeze(), -1.0, 1.0)
                    if primeiro is None:
                        primeiro = time.time() - t0
                    yield (onda * 32767.0).astype("<i2").tobytes()
            finally:
                log.info("fluxo chars=%d primeiro=%.2f seg=%.2f device=%s voz=%s",
                         len(texto), primeiro if primeiro is not None else -1.0, time.time() - t0, self.device, voz or VOZ)
