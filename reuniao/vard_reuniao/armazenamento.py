"""Pasta da reunião: reuniao.json, transcricao.jsonl/md e áudio FLAC temporário."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import pasta_dados

log = logging.getLogger("vard_reuniao.armazenamento")

RAIZ = pasta_dados() / "reunioes"


def nome_pasta(agora: dt.datetime) -> str:
    return agora.strftime("%Y-%m-%d_%H%M")


def mmss(t: float) -> str:
    s = int(t)
    return f"{s // 60:02d}:{s % 60:02d}"


@dataclass
class Fala:
    t0: float
    t1: float
    trilha: str              # "eu" | "outros" | "sistema"
    texto: str
    falante: int | None = None


@dataclass
class Reuniao:
    pasta: str
    inicio: str
    fim: str = ""
    duracao_s: int = 0
    dispositivos: dict = field(default_factory=dict)
    trilhas: list[str] = field(default_factory=lambda: ["eu", "outros"])
    diarizada: bool = False
    falantes: dict[str, str] = field(default_factory=dict)
    apagar_audio_em: str = ""
    guardar_audio: bool = False
    ata: bool = False
    relatorio: bool = False

    def salvar(self, pasta: Path) -> None:
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        alvo = pasta / "reuniao.json"
        tmp = pasta / "reuniao.json.tmp"
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, alvo)

    @classmethod
    def carregar(cls, pasta: Path) -> "Reuniao":
        d = json.loads((Path(pasta) / "reuniao.json").read_text(encoding="utf-8"))
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in nomes})


def linha_md(fala: Fala, falantes: dict[str, str]) -> str:
    t = mmss(fala.t0)
    if fala.trilha == "sistema":
        return f"[{t}] [{fala.texto}]"
    if fala.trilha == "eu":
        quem = "usuário"
    elif fala.falante is not None:
        nome = falantes.get(str(fala.falante))
        quem = f"falante {fala.falante} ({nome})" if nome else f"falante {fala.falante}"
    else:
        quem = "outros"
    return f"[{t}] {quem}: {fala.texto}"


class Transcricao:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.jsonl = self.pasta / "transcricao.jsonl"
        self.md = self.pasta / "transcricao.md"
        self._trava = threading.Lock()
        self._falantes: dict[str, str] = {}
        try:
            self._falantes = dict(Reuniao.carregar(self.pasta).falantes)
        except (OSError, ValueError, TypeError):
            pass
        self._falas: list[Fala] = self._ler_jsonl()      # lido uma vez; depois só em memória

    def acrescentar(self, fala: Fala) -> None:
        with self._trava:
            with self.jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(fala), ensure_ascii=False) + "\n")
            self._falas.append(fala)
            self._regravar_md()

    def marcador(self, t: float, texto: str) -> None:
        self.acrescentar(Fala(t, t, "sistema", texto))

    def falas(self) -> list[Fala]:
        return list(self._falas)

    def _ler_jsonl(self) -> list[Fala]:
        try:
            linhas = self.jsonl.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for ln in linhas:
            if not ln.strip():
                continue
            try:
                out.append(Fala(**json.loads(ln)))
            except (ValueError, TypeError):
                log.warning("linha ilegível em %s", self.jsonl.name)
        return out

    def substituir(self, falas: list[Fala]) -> None:
        """Troca todas as falas (a diarização reatribui falantes): jsonl por arquivo temporário e md."""
        with self._trava:
            tmp = self.jsonl.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(asdict(f), ensure_ascii=False) + "\n" for f in falas), encoding="utf-8")
            os.replace(tmp, self.jsonl)
            self._falas = list(falas)
            self._regravar_md()

    def reescrever(self, falantes: dict[str, str]) -> None:
        with self._trava:
            self._falantes = dict(falantes)
            try:
                r = Reuniao.carregar(self.pasta)
                r.falantes = dict(falantes)
                r.salvar(self.pasta)
            except (OSError, ValueError, TypeError):
                log.warning("reuniao.json ausente ou ilegivel: nomes so no md")
            self._regravar_md()

    def _regravar_md(self) -> None:
        linhas = [f"# Reunião {self.pasta.name}", ""]
        linhas += [linha_md(f, self._falantes) for f in self._falas]
        self.md.write_text("\n".join(linhas) + "\n", encoding="utf-8")


class Gravador:
    def __init__(self, pasta: Path, trilhas=("eu", "outros")):
        tmp = Path(pasta) / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._n: dict[str, int] = {t: 0 for t in trilhas}
        self._arqs = {
            t: sf.SoundFile(str(tmp / f"{t}.flac"), mode="w", samplerate=16000, channels=1, format="FLAC", subtype="PCM_16")
            for t in trilhas
        }

    def escrever(self, trilha: str, pcm16: np.ndarray) -> None:
        with self._trava:
            arq = self._arqs.get(trilha)
            if arq is not None:
                x = np.asarray(pcm16, dtype=np.int16)
                arq.write(x)
                self._n[trilha] = self._n.get(trilha, 0) + len(x)

    def amostras(self, trilha: str) -> int:
        """Quantas amostras (16 kHz) já foram gravadas na trilha."""
        with self._trava:
            return self._n.get(trilha, 0)

    def fechar(self) -> None:
        with self._trava:
            for arq in self._arqs.values():
                arq.close()
            self._arqs.clear()


MARCADOR_ORFA = "reunião encerrada por queda do serviço"


def fechar_orfas(raiz: Path, agora: dt.datetime, *, guardar_audio: bool = False, apagar_audio_horas: int = 24) -> list[str]:
    """Reunião sem `fim` (o serviço caiu com ela ativa) nunca fecharia sozinha. Chamada no arranque do 4720, quando
    nenhuma sessão existe: grava fim = agora, duração pela última fala, `apagar_audio_em` pela regra e um marcador."""
    raiz = Path(raiz)
    fechadas: list[str] = []
    if not raiz.is_dir():
        return fechadas
    for p in sorted(raiz.iterdir()):
        if not (p.is_dir() and (p / "reuniao.json").is_file()):
            continue
        try:
            reu = Reuniao.carregar(p)
            if reu.fim:
                continue
            transc = Transcricao(p)
            ultimo = max((f.t1 for f in transc.falas()), default=0.0)
            reu.fim = agora.isoformat(timespec="seconds")
            reu.duracao_s = int(ultimo)
            reu.guardar_audio = guardar_audio
            reu.apagar_audio_em = "" if guardar_audio else (agora + dt.timedelta(hours=apagar_audio_horas)).isoformat(timespec="seconds")
            transc.marcador(ultimo, MARCADOR_ORFA)
            reu.salvar(p)
            fechadas.append(p.name)
            log.warning("reunião órfã fechada: %s", p.name)
        except (OSError, ValueError, TypeError):
            log.exception("não consegui fechar a reunião órfã %s", p.name)
    return fechadas


def listar(raiz: Path, n: int = 10) -> list[Reuniao]:
    raiz = Path(raiz)
    if not raiz.is_dir():
        return []
    pastas = sorted((p for p in raiz.iterdir() if p.is_dir() and (p / "reuniao.json").is_file()), key=lambda p: p.name, reverse=True)
    out: list[Reuniao] = []
    for p in pastas:
        if len(out) >= n:
            break
        try:
            out.append(Reuniao.carregar(p))
        except (OSError, ValueError, TypeError):
            log.warning("reuniao.json ilegível em %s", p.name)
    return out


def ultima(raiz: Path) -> Reuniao | None:
    r = listar(raiz, 1)
    return r[0] if r else None
