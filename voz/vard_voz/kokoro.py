"""Motor Kokoro próprio para o Vard (T8).

Importação leve: não importa TTS/coqui nem exige GPU no nível de módulo.
A biblioteca Kokoro é carregada apenas em `carregar()`, e falhas de import
são tratadas como estado "não instalado" (pronta=False) sem quebrar o serviço.

Contrato:
- `VOZES_KOKORO`: dict {id: rótulo} com vozes pt-BR e en-US estáveis.
- `MotorKokoro(device)`: mesma interface pública do Motor XTTS (`vozes`,
  `tem_voz`, `falar`, `falar_fluxo`, `carregar`, atributos `pronta`/`aquecida`).
- Síntese devolve WAV PCM16 mono 24 kHz ou fluxo PCM16; voz desconhecida
  levanta KeyError/ValueError; falha local não aciona API paga/OpenJarvis.
"""
from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Iterator

log = logging.getLogger("vard_voz")

# IDs estáveis compatíveis com src/conectores/voz/kokoro.ts.
VOZES_KOKORO: dict[str, str] = {
    "pf_dora": "Dora (pt-BR, feminina)",
    "pm_alex": "Alex (pt-BR, masculina)",
    "pm_santa": "Santa (pt-BR, masculina)",
    "af_heart": "Heart (en-US, feminina)",
    "af_bella": "Bella (en-US, feminina)",
    "am_adam": "Adam (en-US, masculina)",
    "am_michael": "Michael (en-US, masculina)",
    "bf_emma": "Emma (en-GB, feminina)",
    "bm_george": "George (en-GB, masculina)",
}

TAXA = 24000


def _pcm_para_wav(pcm: bytes, taxa: int = TAXA) -> bytes:
    """Converte PCM16 mono em WAV PCM16 mono."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buf.getvalue()


class MotorKokoro:
    """Motor TTS Kokoro com a mesma interface pública do Motor XTTS.

    A importação da biblioteca Kokoro ocorre apenas em `carregar()`; se a
    dependência não estiver instalada, o motor permanece em pronta=False e
    `falar`/`falar_fluxo` levantam RuntimeError sem tocar em rede/GPU.
    """

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.pronta = False
        self.aquecida = False
        self._lock = threading.Lock()
        self._modelo = None

    # --- Interface pública (espelha Motor XTTS) -------------------------

    def vozes(self) -> list[str]:
        return list(VOZES_KOKORO.keys())

    def tem_voz(self, nome: str) -> bool:
        return nome in VOZES_KOKORO

    def carregar(self) -> None:
        """Carrega o modelo Kokoro no dispositivo escolhido.

        Falha de import (biblioteca não instalada) deixa pronta=False e
        registra aviso; não baixa pesos nem exige GPU na chamada.
        """
        try:
            # Import tardio: só aqui a biblioteca Kokoro é tocada.
            from kokoro import KPipeline  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - ambiente sem kokoro
            log.warning("kokoro nao instalado: %s", exc)
            return

        with self._lock:
            try:
                self._modelo = KPipeline(lang="p", device=self.device)
                self.pronta = True
                self.aquecida = True
                log.info("motor kokoro carregado (device=%s)", self.device)
            except Exception:
                log.exception("falha ao carregar kokoro")

    def falar(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> bytes:
        """Sintetiza texto em WAV PCM16 mono 24 kHz."""
        pcm, taxa = self._sintetizar_raw(texto, voz, velocidade)
        return _pcm_para_wav(pcm, taxa)

    def falar_fluxo(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> Iterator[bytes]:
        """Gera PCM16 mono 24 kHz em pedaços."""
        yield from self._fluxo_raw(texto, voz, velocidade)

    # --- Internos (substituíveis em teste) ------------------------------

    def _validar_voz(self, voz: str | None) -> str:
        v = voz or next(iter(VOZES_KOKORO))
        if v not in VOZES_KOKORO:
            raise KeyError(v)
        return v

    def _sintetizar_raw(self, texto: str, voz: str | None, velocidade: float) -> tuple[bytes, int]:
        """Devolve (PCM16 bytes, taxa). Override em teste para evitar GPU."""
        v = self._validar_voz(voz)
        if not self.pronta or self._modelo is None:
            raise RuntimeError("kokoro nao carregado")
        with self._lock:
            try:
                # KPipeline.__call__ devolve (audio_np, tokens); audio é float32 [-1,1].
                audio, _ = self._modelo(texto, voice=v, speed=velocidade)
            except Exception as exc:
                raise RuntimeError(f"falha na sintese kokoro: {exc}") from exc
        import numpy as np  # import tardio para permitir mock sem numpy

        pcm = (np.asarray(audio, dtype="float32").squeeze() * 32767.0).astype("<i2").tobytes()
        return pcm, TAXA

    def _fluxo_raw(self, texto: str, voz: str | None, velocidade: float) -> Iterator[bytes]:
        """Gera chunks de PCM16. Override em teste para evitar GPU."""
        pcm, _taxa = self._sintetizar_raw(texto, voz, velocidade)
        # Chunk de ~0,1 s (4800 bytes a 24 kHz mono 16 bits).
        tamanho = 4800
        for i in range(0, len(pcm), tamanho):
            yield pcm[i : i + tamanho]