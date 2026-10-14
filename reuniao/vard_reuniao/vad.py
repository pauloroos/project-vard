"""Segmentação por VAD (silero) por trilha: fala vira Segmento de min_fala a max_fala, cortado no silêncio.

O relógio é o t_bloco de cada bloco (monotônico), não a contagem de amostras: o loopback não entrega
quadros quando nada toca.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

TAXA = 16000


@dataclass
class Segmento:
    trilha: str
    t0: float
    t1: float
    pcm: np.ndarray


class Segmentador:
    def __init__(self, trilha: str, prob: Callable[[np.ndarray], float], *, limiar: float = 0.5, min_silencio_ms: int = 700,
                 min_fala_ms: int = 250, max_fala_s: float = 20.0, janela: int = 512):
        self.trilha, self.prob, self.limiar, self.janela = trilha, prob, limiar, janela
        self.min_silencio = min_silencio_ms / 1000
        self.min_fala = min_fala_ms / 1000
        self.max_fala = max_fala_s
        self._resto = np.zeros(0, dtype=np.int16)
        self._fala: list[np.ndarray] = []
        self._t0: float | None = None
        self._t_ultima_fala = 0.0
        self._n_ate_ultima = 0          # janelas até a última com fala (o silêncio final não entra no pcm)
        self._t_atual = 0.0

    def alimentar(self, pcm: np.ndarray, t_bloco: float) -> list[Segmento]:
        prontos: list[Segmento] = []
        # O relógio é sempre o do bloco: o resto de amostras pendente veio antes de t_bloco.
        t = t_bloco - len(self._resto) / TAXA
        if self._t0 is not None and t - self._t_ultima_fala >= self.min_silencio:
            # Lacuna sem quadros (loopback em silêncio) conta como silêncio: fecha a fala e descarta o resto velho.
            prontos += self._fechar_se_vale()
            self._resto = np.zeros(0, dtype=np.int16)
            t = t_bloco
        buf = np.concatenate([self._resto, np.asarray(pcm, dtype=np.int16)])
        i = 0
        while i + self.janela <= len(buf):
            jan = buf[i:i + self.janela]
            t_jan = t + i / TAXA
            self._t_atual = t_jan + self.janela / TAXA
            if self.prob(jan) >= self.limiar:
                if self._t0 is None:
                    self._t0 = t_jan
                self._fala.append(jan)
                self._t_ultima_fala = self._t_atual
                self._n_ate_ultima = len(self._fala)
                if self._t_atual - self._t0 >= self.max_fala:
                    prontos += self._fechar_se_vale()
            elif self._t0 is not None:
                self._fala.append(jan)        # silêncio curto dentro da fala fica no áudio
                if self._t_atual - self._t_ultima_fala >= self.min_silencio:
                    prontos += self._fechar_se_vale()
            i += self.janela
        self._resto = buf[i:]
        return prontos

    def _fechar_se_vale(self) -> list[Segmento]:
        seg = None
        if self._t0 is not None and self._t_ultima_fala - self._t0 >= self.min_fala:
            seg = Segmento(self.trilha, self._t0, self._t_ultima_fala, np.concatenate(self._fala[:self._n_ate_ultima]))
        self._fala, self._t0, self._n_ate_ultima = [], None, 0
        return [seg] if seg else []

    def fechar(self) -> Segmento | None:
        segs = self._fechar_se_vale()
        return segs[0] if segs else None


def carregar_silero() -> Callable[[np.ndarray], float]:
    """Devolve um `prob` NOVO a cada chamada (modelo próprio, com estado recorrente): use um por trilha.
    `prob.reset()` zera o estado do modelo; a sessão chama ao atravessar uma lacuna."""
    import torch
    from silero_vad import load_silero_vad

    torch.set_num_threads(1)
    modelo = load_silero_vad()

    def prob(janela: np.ndarray) -> float:
        with torch.no_grad():
            return float(modelo(torch.from_numpy(janela.astype(np.float32) / 32768.0), TAXA).item())

    if hasattr(modelo, "reset_states"):
        prob.reset = modelo.reset_states  # type: ignore[attr-defined]
    else:
        prob.reset = lambda: None  # type: ignore[attr-defined]
    return prob
