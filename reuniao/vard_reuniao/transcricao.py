"""Transcrição pelo OpenJarvis (whisper), limpeza de alucinação e fila serial."""
from __future__ import annotations

import io
import logging
import queue
import re
import threading
import time
import wave
from collections import Counter
from typing import Callable

import httpx
import numpy as np

from .texto import simples
from .vad import Segmento

log = logging.getLogger("vard_reuniao.transcricao")


ERRO_CONF = -1.0        # confiança negativa = falhou (HTTP/rede); vazio com conf >= 0 é silêncio legítimo


def wav_bytes(pcm16: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.asarray(pcm16, dtype=np.int16).tobytes())
    return buf.getvalue()


class Transcritor:
    def __init__(self, base: str = "http://127.0.0.1:8000", post=httpx.post, timeout: float = 60):
        self.base, self.post, self.timeout = base.rstrip("/"), post, timeout

    def transcrever(self, pcm16: np.ndarray) -> tuple[str, float]:
        try:
            r = self.post(
                f"{self.base}/v1/speech/transcribe",
                files={"file": ("segmento.wav", wav_bytes(pcm16), "audio/wav")},
                data={"language": "pt"}, timeout=self.timeout, trust_env=False,
            )
            if r.status_code != 200:
                log.warning("transcrever: HTTP %s %s", r.status_code, r.text[:80])
                return "", ERRO_CONF
            d = r.json()
            return str(d.get("text", "")).strip(), float(d.get("confidence") or 0.0)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as e:
            log.warning("transcrever: %s", str(e)[:80])
            return "", ERRO_CONF


def limpar(texto: str, bloqueio: list[str], confianca: float, minimo: float = 0.3, bloqueio_exato=()) -> str:
    t = str(texto).strip()
    s = simples(t)
    if not s or confianca < minimo:
        return ""
    if s in {simples(x) for x in bloqueio_exato}:
        return ""
    if any(simples(b) and simples(b) in s for b in bloqueio):
        return ""
    frases = [simples(f) for f in re.split(r"[.!?]+", t)]
    if any(n >= 3 for f, n in Counter(frases).items() if f):
        return ""
    return t


class Fila:
    def __init__(self, transcrever: Callable[[Segmento], tuple[str, float]], ao_texto: Callable[[Segmento, str, float], None]):
        self.transcrever, self.ao_texto = transcrever, ao_texto
        self._q: queue.Queue = queue.Queue()
        self._th: threading.Thread | None = None
        self._parada = False           # a Fila e de uso unico: depois de parar nao reinicia

    @property
    def tamanho(self) -> int:
        return self._q.unfinished_tasks

    def por(self, seg: Segmento) -> None:
        self._q.put(seg)

    def iniciar(self) -> None:
        if self._parada:
            raise RuntimeError("Fila ja parada: crie outra")
        if self._th and self._th.is_alive():
            return
        self._th = threading.Thread(target=self._laco, daemon=True, name="vard-fila")
        self._th.start()

    def _laco(self) -> None:
        while True:
            seg = self._q.get()
            try:
                if seg is None:
                    return
                texto, conf = self.transcrever(seg)
                self.ao_texto(seg, texto, conf)
            except Exception:  # noqa: BLE001 — um segmento ruim não derruba a fila
                log.exception("fila: segmento")
            finally:
                self._q.task_done()

    def esvaziar(self, timeout_s: float = 30.0) -> bool:
        fim = time.monotonic() + timeout_s
        while self._q.unfinished_tasks:
            if time.monotonic() >= fim:
                return False
            time.sleep(0.05)
        return True

    def parar(self) -> None:
        self._parada = True
        if self._th and self._th.is_alive():
            self._q.put(None)
            self._th.join(timeout=5)
