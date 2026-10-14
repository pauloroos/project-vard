import os

import numpy as np
import pytest

os.environ["PYANNOTE_METRICS_ENABLED"] = "0"      # nenhum teste manda telemetria do pyannote


@pytest.fixture(autouse=True)
def _ambiente_isolado(tmp_path, monkeypatch):
    """Nenhum teste lê configuração ou dados reais do usuário: a cadeia de resolução cai em pasta vazia."""
    monkeypatch.setenv("VARD_REUNIAO_CONFIG", str(tmp_path / "ausente" / "reuniao.toml"))
    monkeypatch.setenv("VARD_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("VARD_DADOS", str(tmp_path / "dados"))


def tom(freq_hz: float, dur_s: float, taxa: int = 16000, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur_s * taxa)) / taxa
    return (np.sin(2 * np.pi * freq_hz * t) * amp).astype(np.float32)


def silencio(dur_s: float, taxa: int = 16000) -> np.ndarray:
    return np.zeros(int(dur_s * taxa), dtype=np.float32)


@pytest.fixture
def pasta_reuniao(tmp_path):
    p = tmp_path / "2026-10-13_1500"
    p.mkdir()
    return p
