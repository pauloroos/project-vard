"""Configuração do serviço: precedência VARD_REUNIAO_CONFIG, VARD_CONFIG/reuniao.toml, pasta do usuário, padrões.

Padrões iguais ao exemplo público config/examples/reuniao.example.toml: sem arquivo, o serviço funciona igual.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BLOQUEIO_PADRAO = ["legendas pela comunidade", "obrigado por assistir", "inscreva-se no canal", "tchau tchau", "amara.org"]
BLOQUEIO_EXATO_PADRAO = ["obrigado", "obrigada", "tchau", "amém", "legendas"]


def pasta_dados() -> Path:
    """Pasta de dados do usuário: VARD_DADOS sobrescreve; sem ela, %LOCALAPPDATA%/rdl-vard."""
    valor = os.environ.get("VARD_DADOS", "").strip()
    return Path(valor) if valor else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "rdl-vard"


def caminhos() -> list[Path]:
    """Cadeia de resolução de reuniao.toml, em ordem de precedência."""
    alvos = []
    direto = os.environ.get("VARD_REUNIAO_CONFIG", "").strip()
    if direto:
        alvos.append(Path(direto))
    base = os.environ.get("VARD_CONFIG", "").strip()
    if base:
        alvos.append(Path(base) / "reuniao.toml")
    alvos.append(pasta_dados() / "config" / "reuniao.toml")
    return alvos


def _achar(caminho: Path | None) -> Path | None:
    """Primeiro arquivo existente da cadeia; None quando não há nenhum (valem os padrões embutidos)."""
    alvos = [Path(caminho)] if caminho is not None else caminhos()
    return next((a for a in alvos if a.is_file()), None)


@dataclass
class Conf:
    guardar_audio: bool = False
    apagar_audio_horas: int = 24
    reter_dias: int = 90
    vad_limiar: float = 0.5
    min_silencio_ms: int = 700
    min_fala_ms: int = 250
    max_fala_s: float = 20.0
    confianca_minima: float = 0.3
    bloqueio: list[str] = field(default_factory=lambda: list(BLOQUEIO_PADRAO))
    bloqueio_exato: list[str] = field(default_factory=lambda: list(BLOQUEIO_EXATO_PADRAO))
    eco_limiar: float = 0.8
    bloco_chars: int = 9000
    diarizacao: bool = False


def carregar(caminho: Path | None = None) -> Conf:
    alvo = _achar(caminho)                                          # caminho explícito ou a cadeia de precedência
    if alvo is None:
        return Conf()
    try:
        with alvo.open("rb") as f:
            d = tomllib.load(f)
    except (OSError, ValueError):
        return Conf()
    try:
        a, v, t, ata, dia = (d.get(k, {}) for k in ("audio", "vad", "transcricao", "ata", "diarizacao"))
        c = Conf()
        return Conf(
            guardar_audio=bool(a.get("guardar_audio", c.guardar_audio)),
            apagar_audio_horas=int(a.get("apagar_audio_horas", c.apagar_audio_horas)),
            reter_dias=int(a.get("reter_dias", c.reter_dias)),
            vad_limiar=float(v.get("limiar", c.vad_limiar)),
            min_silencio_ms=int(v.get("min_silencio_ms", c.min_silencio_ms)),
            min_fala_ms=int(v.get("min_fala_ms", c.min_fala_ms)),
            max_fala_s=float(v.get("max_fala_s", c.max_fala_s)),
            confianca_minima=float(t.get("confianca_minima", c.confianca_minima)),
            bloqueio=[str(x) for x in t.get("bloqueio", c.bloqueio)],
            bloqueio_exato=[str(x) for x in t.get("bloqueio_exato", c.bloqueio_exato)],
            eco_limiar=float(t.get("eco_limiar", c.eco_limiar)),
            bloco_chars=int(ata.get("bloco_chars", c.bloco_chars)),
            diarizacao=bool(dia.get("ligada", c.diarizacao)),
        )
    except (ValueError, TypeError, AttributeError):
        return Conf()
