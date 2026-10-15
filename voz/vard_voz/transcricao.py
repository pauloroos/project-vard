"""Transcrição STT própria via faster-whisper (opcional).

Importação leve: o motor só carrega quando explicitamente instanciado.
Sem GPU/download na importação; dispositivo e modelo são parâmetros.
Aceita WAV e OGG/Opus (Telegram), decodifica via PyAV para PCM mono 16 kHz.
"""
from __future__ import annotations

import io
import logging
import wave

import numpy as np

log = logging.getLogger("vard_voz.transcricao")

TAXA = 16000
CANAL = 1
LIMITE_BYTES = 10 * 1024 * 1024  # 10 MiB
LIMITE_SEGUNDOS = 120


class MotorSTT:
    """Wrapper sobre faster-whisper com carregamento explícito."""

    def __init__(
        self,
        modelo: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        idioma: str = "pt",
        palavras_chamada: list[str] | None = None,
    ) -> None:
        self.modelo_nome = modelo
        self.device = device
        self.compute_type = compute_type
        self.idioma = idioma
        self.palavras_chamada = list(palavras_chamada or [])
        self._modelo = None

    @property
    def pronta(self) -> bool:
        return self._modelo is not None

    def carregar(self) -> None:
        """Carrega o modelo faster-whisper. Falha se o pacote não estiver instalado."""
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper não instalado; instale o extra 'stt': uv pip install vard-voz[stt]"
            ) from exc
        log.info("carregando STT modelo=%s device=%s compute=%s", self.modelo_nome, self.device, self.compute_type)
        self._modelo = WhisperModel(
            self.modelo_nome, device=self.device, compute_type=self.compute_type
        )

    def transcrever_bytes(self, audio: bytes, idioma: str | None = None) -> tuple[str, float]:
        """Transcreve áudio em bytes (WAV ou OGG/Opus). Devolve (texto, confiança).

        Confiança negativa (-1.0) indica falha; texto vazio com conf >= 0 é silêncio legítimo.
        """
        if not self.pronta:
            raise RuntimeError("MotorSTT não carregado; chame carregar() primeiro")
        if len(audio) > LIMITE_BYTES:
            raise ValueError(f"áudio excede {LIMITE_BYTES} bytes")
        pcm = _decodificar_para_pcm(audio)
        duracao_s = len(pcm) / TAXA
        if duracao_s > LIMITE_SEGUNDOS:
            raise ValueError(f"áudio excede {LIMITE_SEGUNDOS}s ({duracao_s:.1f}s)")
        lang = idioma or self.idioma
        segmentos, info = self._modelo.transcribe(
            pcm.astype(np.float32) / 32768.0,
            language=lang,
            condition_on_previous_text=False,
            initial_prompt=" ".join(self.palavras_chamada) if self.palavras_chamada else None,
        )
        partes: list[str] = []
        confs: list[float] = []
        for seg in segmentos:
            texto = (seg.text or "").strip()
            if texto:
                partes.append(texto)
                confs.append(float(seg.avg_logprob) if seg.avg_logprob is not None else 0.0)
        texto_final = " ".join(partes).strip()
        # avg_logprob não é confiança direta; normalizamos para escala 0-1 aproximada
        confianca = _logprob_para_confianca(confs) if confs else 0.0
        return texto_final, confianca


def _logprob_para_confianca(logprobs: list[float]) -> float:
    """Converte média de log-probs para uma pseudo-confiança 0-1.

    logprob ~ 0 → alta confiança; logprob < -1 → baixa. Mapeia [-3, 0] → [0, 1].
    Lista vazia devolve 0.0 (sem segmentos = sem confiança).
    """
    if not logprobs:
        return 0.0
    media = sum(logprobs) / len(logprobs)
    # Clamp entre -3 e 0
    clamp = max(-3.0, min(0.0, media))
    return round((clamp + 3.0) / 3.0, 4)


def _decodificar_para_pcm(audio: bytes) -> np.ndarray:
    """Decodifica WAV ou OGG/Opus para PCM mono 16 kHz int16.

    Tenta WAV primeiro (wave); se falhar, usa PyAV (av) para OGG/Opus.
    """
    # Tentar WAV nativo
    try:
        buf = io.BytesIO(audio)
        with wave.open(buf, "rb") as w:
            n_canais = w.getnchannels()
            taxa = w.getframerate()
            amostras = w.getsampwidth()
            frames = w.readframes(w.getnframes())
        arr = np.frombuffer(frames, dtype=np.int16 if amostras == 2 else np.uint8)
        if amostras == 1:
            arr = ((arr.astype(np.int16) - 128) * 256).astype(np.int16)
        if n_canais > 1:
            arr = arr.reshape(-1, n_canais).mean(axis=1).astype(np.int16)
        if taxa != TAXA:
            arr = _ressamplear(arr, taxa, TAXA)
        return arr
    except (wave.Error, EOFError, ValueError):
        pass

    # Fallback: PyAV para OGG/Opus e outros formatos
    try:
        import av  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyAV não instalado e áudio não é WAV; instale o extra 'stt': uv pip install vard-voz[stt]"
        ) from exc

    container = av.open(io.BytesIO(audio))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="s16", layout="mono", rate=TAXA)
    chunks: list[np.ndarray] = []
    for frame in container.decode(stream):
        for rframe in resampler.resample(frame):
            arr = rframe.to_ndarray().flatten()
            chunks.append(arr.astype(np.int16))
    container.close()
    if not chunks:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(chunks)


def _ressamplear(arr: np.ndarray, taxa_origem: int, taxa_destino: int) -> np.ndarray:
    """Ressampleagem linear simples para conversão de taxa."""
    if taxa_origem == taxa_destino:
        return arr
    fator = taxa_destino / taxa_origem
    novo_len = int(len(arr) * fator)
    indices = np.linspace(0, len(arr) - 1, novo_len)
    return np.interp(indices, np.arange(len(arr)), arr.astype(np.float64)).astype(np.int16)