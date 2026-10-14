"""Diarização pós-reunião da trilha "outros": pyannote community-1 (CPU hoje) e reserva por embeddings.

Nada roda durante a reunião e nada força a GPU: `escolher_device` só devolve "cuda" com folga real.
O modelo vem do cache local (HF_HOME) em modo offline; o download único é feito por deploy\\instalar-reuniao.ps1.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Callable

from . import armazenamento as arm
from .armazenamento import Fala
from .config import pasta_dados

# Antes de qualquer import de huggingface_hub/pyannote (o __main__ também define; aqui cobre testes e uso avulso).
_LOCAL = pasta_dados()
os.environ["PYANNOTE_METRICS_ENABLED"] = "0"      # forçado: telemetria do pyannote desligada
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HOME", str(_LOCAL / "modelos" / "hf"))

log = logging.getLogger("vard_reuniao.diarizacao")

MODELOS = ("pyannote/speaker-diarization-community-1", "pyannote/segmentation-3.0", "pyannote/speaker-diarization-3.1")
MODELO_RESERVA = "pyannote/wespeaker-voxceleb-resnet34-LM"
ESTADO = _LOCAL / "reuniao-modelos.json"
MOTIVO_AUSENTE = "modelo não baixado (deploy\\instalar-reuniao.ps1)"
GPU_MINIMA_MB = 1500
LIMIAR_COSSENO = 0.7

Trecho = tuple[float, float, int]       # t0, t1, falante (>= 1, em ordem de primeira aparição)


def estado(arquivo: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arquivo or ESTADO).read_text(encoding="utf-8"))
        pronta = bool(d.get("pronto"))
        modo = str(d.get("modo", "")) if pronta else "nenhum"
        return {"pronta": pronta, "motivo": str(d.get("motivo", "")), "modo": modo or "nenhum",
                "baixado_em": str(d.get("baixado_em", ""))}
    except (OSError, ValueError, AttributeError):
        return {"pronta": False, "motivo": MOTIVO_AUSENTE, "modo": "nenhum", "baixado_em": ""}


def gpu_livre_mb(run=subprocess.run) -> int:
    try:
        r = run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return 0
        return int(str(r.stdout).strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 0


def escolher_device(livre_mb: int) -> str:
    return "cuda" if livre_mb >= GPU_MINIMA_MB else "cpu"


def renumerar(brutos: list[tuple[float, float, object]]) -> list[Trecho]:
    """Rótulos quaisquer -> 1, 2, ... por ordem de primeira aparição no tempo."""
    mapa: dict[object, int] = {}
    out: list[Trecho] = []
    for t0, t1, rotulo in sorted(brutos, key=lambda x: (x[0], x[1])):
        n = mapa.setdefault(rotulo, len(mapa) + 1)
        out.append((float(t0), float(t1), n))
    return out


def _audio(flac: Path) -> dict:
    """FLAC -> {"waveform": tensor float32 (1, n), "sample_rate": 16000}; sem torchcodec."""
    import numpy as np
    import soundfile as sf
    import torch

    dados, taxa = sf.read(str(flac), dtype="float32", always_2d=True)
    mono = dados.mean(axis=1)
    if taxa != 16000:
        from scipy.signal import resample_poly
        mono = resample_poly(mono, 16000, taxa).astype(np.float32)
    return {"waveform": torch.tensor(np.ascontiguousarray(mono), dtype=torch.float32).unsqueeze(0), "sample_rate": 16000}


def _descarregar() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def diarizar_community(flac: Path, device: str, repo: str = MODELOS[0]) -> list[Trecho]:
    os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
    import torch
    from pyannote.audio import Pipeline

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    audio = _audio(Path(flac))
    pipeline = Pipeline.from_pretrained(repo)
    try:
        if pipeline is None:
            raise RuntimeError(f"não consegui carregar {repo} do cache local")
        pipeline.to(torch.device(device))
        saida = pipeline(audio)
        diar = getattr(saida, "exclusive_speaker_diarization", None) or getattr(saida, "speaker_diarization", None) or saida
        brutos = [(turno.start, turno.end, rotulo) for turno, _, rotulo in diar.itertracks(yield_label=True)]
    finally:
        del pipeline
        _descarregar()
    return renumerar(brutos)


def agrupar(embeddings) -> list[int]:
    """Agrupamento hierárquico (média, cosseno, corte 0,7) -> rótulos na ordem recebida."""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage

    m = np.asarray(embeddings, dtype=float)
    if len(m) == 0:
        return []
    if len(m) == 1:
        return [1]
    z = linkage(m, "average", metric="cosine")
    return [int(x) for x in fcluster(z, t=LIMIAR_COSSENO, criterion="distance")]


def _embedder_wespeaker(flac: Path, device: str):
    os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
    import numpy as np
    import torch
    from pyannote.audio import Inference, Model
    from pyannote.core import Segment

    audio = _audio(Path(flac))
    modelo = Model.from_pretrained(MODELO_RESERVA)
    inf = Inference(modelo, window="whole", device=torch.device(device))

    def embeddar(t0: float, t1: float):
        return np.asarray(inf.crop(audio, Segment(t0, t1))).reshape(-1)

    return embeddar


def diarizar_reserva(flac: Path, falas: list[Fala], device: str, embeddar: Callable | None = None) -> list[Trecho]:
    """Sem pipeline: um embedding por fala de "outros", agrupado. Cada fala vira um trecho."""
    outros = [f for f in falas if f.trilha == "outros" and f.t1 - f.t0 >= 0.3]
    if not outros:
        return []
    try:
        if embeddar is None:
            embeddar = _embedder_wespeaker(Path(flac), device)
        rotulos = agrupar([embeddar(f.t0, f.t1) for f in outros])
    finally:
        embeddar = None
        _descarregar()
    return renumerar([(f.t0, f.t1, r) for f, r in zip(outros, rotulos)])


def _sobreposicao(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _distancia(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, max(a0, b0) - min(a1, b1))


def atribuir(falas: list[Fala], trechos: list[Trecho]) -> list[Fala]:
    """Para cada fala de "outros": o falante com mais tempo sobreposto; sem sobreposição, o do trecho mais próximo."""
    out: list[Fala] = []
    for f in falas:
        if f.trilha != "outros" or not trechos:
            out.append(f)
            continue
        tempo: dict[int, float] = {}
        for t0, t1, n in trechos:
            s = _sobreposicao(f.t0, f.t1, t0, t1)
            if s > 0:
                tempo[n] = tempo.get(n, 0.0) + s
        if tempo:
            n = max(sorted(tempo), key=lambda k: tempo[k])
        else:
            n = min(trechos, key=lambda t: (_distancia(f.t0, f.t1, t[0], t[1]), t[2]))[2]
        out.append(replace(f, falante=n))
    return out


def _runner_padrao(falas: list[Fala], modo: str) -> Callable[[Path, str], list[Trecho]]:
    def run(flac: Path, device: str) -> list[Trecho]:
        if modo == "reserva":
            return diarizar_reserva(flac, falas, device)
        try:
            return diarizar_community(flac, device)
        except Exception:  # noqa: BLE001
            log.exception("community-1 falhou; tentando o speaker-diarization-3.1")
            return diarizar_community(flac, device, MODELOS[2])
    return run


def diarizar_pasta(pasta: Path, *, run_diarizar=None, gpu_livre=gpu_livre_mb, modo: str | None = None) -> dict:
    pasta = Path(pasta)
    flac = pasta / "tmp" / "outros.flac"
    if not flac.is_file():
        return {"ok": False, "erro": "sem_audio"}
    modo = modo or ("reserva" if estado().get("modo") == "reserva" else "community-1")
    device = escolher_device(gpu_livre())
    transcricao = arm.Transcricao(pasta)
    falas = transcricao.falas()
    run = run_diarizar or _runner_padrao(falas, modo)
    try:
        trechos = run(flac, device)
    except Exception as e:  # noqa: BLE001
        log.exception("diarização falhou")
        return {"ok": False, "erro": "falha", "detalhe": str(e)[:200]}
    if not trechos:
        log.info("diarização de %s: nenhum trecho de fala", pasta.name)
        return {"ok": False, "erro": "sem_fala"}
    novas = atribuir(falas, trechos)
    transcricao.substituir(novas)
    try:
        r = arm.Reuniao.carregar(pasta)
        r.diarizada = True
        r.salvar(pasta)
    except (OSError, ValueError, TypeError):
        log.warning("reuniao.json ilegível: diarizada não marcada")
    n = len({f.falante for f in novas if f.trilha == "outros" and f.falante is not None})
    log.info("diarização de %s: %d falantes (%s, %s)", pasta.name, n, modo, device)
    return {"ok": True, "falantes": n, "device": device, "modo": modo}
