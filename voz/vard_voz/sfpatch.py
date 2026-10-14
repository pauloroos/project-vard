"""torchaudio.load via soundfile (o torchaudio novo exige torchcodec). Importar ANTES de TTS."""
import soundfile as _sf
import torch
import torchaudio


def _load(p, *a, **k):
    d, sr = _sf.read(p, dtype="float32", always_2d=True)
    return torch.from_numpy(d.T.copy()), sr


torchaudio.load = _load
