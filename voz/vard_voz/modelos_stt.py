"""Modelos de transcrição (faster-whisper) da aba Transcrição: catálogo, cache e escolha.

Os arquivos ficam no cache do Hugging Face, onde o próprio faster-whisper procura ao carregar pelo nome.
Nada é baixado na importação; o download roda numa thread e o progresso é o tamanho já gravado no cache.
A escolha do usuário vem do hud.config.json (stt_modelo, stt_dispositivo) e ganha das variáveis VARD_STT_*.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("vard_voz.modelos_stt")

# Os mesmos arquivos que o faster_whisper.utils.download_model baixa.
ARQUIVOS = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
DISPOSITIVOS = ("auto", "cuda", "cpu")
# Tipo de cálculo por dispositivo quando a escolha vem da tela (auto deixa o CTranslate2 decidir).
COMPUTE_POR_DISPOSITIVO = {"auto": "auto", "cuda": "float16", "cpu": "int8"}


@dataclass(frozen=True)
class ModeloSTT:
    id: str
    repo: str
    nome: str
    tamanho_mb: int
    idioma: str  # "multilingue" | "ingles"
    velocidade: int  # 1 (lento) a 5 (rápido)
    precisao: int  # 1 (erra mais) a 5 (mais preciso)
    descricao: str


# Tamanhos aproximados do download (model.bin em float16), em MB.
CATALOGO: tuple[ModeloSTT, ...] = (
    ModeloSTT("tiny", "Systran/faster-whisper-tiny", "Tiny", 75, "multilingue", 5, 1,
              "O mais leve; serve para testar, mas erra bastante."),
    ModeloSTT("base", "Systran/faster-whisper-base", "Base", 145, "multilingue", 5, 2,
              "Leve e rápido; razoável em frases curtas."),
    ModeloSTT("small", "Systran/faster-whisper-small", "Small", 485, "multilingue", 4, 3,
              "Bom equilíbrio para quem usa só a CPU."),
    ModeloSTT("medium", "Systran/faster-whisper-medium", "Medium", 1530, "multilingue", 2, 4,
              "Mais preciso; pede GPU para ficar ágil."),
    ModeloSTT("large-v3", "Systran/faster-whisper-large-v3", "Large v3", 3090, "multilingue", 1, 5,
              "O mais preciso e o mais pesado; melhor na GPU."),
    ModeloSTT("large-v3-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "Large v3 Turbo", 1620, "multilingue", 3, 5,
              "Quase a precisão do Large v3, bem mais rápido. Recomendado com GPU."),
    ModeloSTT("distil-large-v3", "Systran/faster-distil-whisper-large-v3", "Distil Large v3", 1510, "ingles", 4, 4,
              "Versão destilada e rápida, mas só entende inglês."),
)
POR_ID = {m.id: m for m in CATALOGO}
# Apelidos aceitos pelo faster-whisper que caem num modelo do catálogo.
APELIDOS = {"turbo": "large-v3-turbo", "large": "large-v3"}


def _cache_padrao() -> Path:
    """Mesmo cache do huggingface_hub (HF_HUB_CACHE, HF_HOME/hub ou ~/.cache/huggingface/hub)."""
    try:
        from huggingface_hub import constants  # type: ignore[import-untyped]
        return Path(constants.HF_HUB_CACHE)
    except Exception:
        if os.environ.get("HF_HUB_CACHE"):
            return Path(os.environ["HF_HUB_CACHE"])
        home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
        return Path(home) / "hub"


def _baixar_hf(repo: str, cache: Path) -> None:
    from huggingface_hub import snapshot_download  # type: ignore[import-untyped]
    snapshot_download(repo, cache_dir=str(cache), allow_patterns=ARQUIVOS)


class GerenciadorModelos:
    """Estado de download de cada modelo do catálogo no cache local."""

    def __init__(
        self,
        cache: Path | None = None,
        baixador: Callable[[str, Path], None] | None = None,
        em_thread: bool = True,
    ) -> None:
        self._cache = Path(cache) if cache is not None else None
        self._baixador = baixador or _baixar_hf
        self._em_thread = em_thread
        self._trava = threading.Lock()
        self._estados: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}

    @property
    def cache(self) -> Path:
        if self._cache is None:
            self._cache = _cache_padrao()
        return self._cache

    @staticmethod
    def normalizar(nome: str) -> str:
        return APELIDOS.get(nome, nome)

    def _modelo(self, id_: str) -> ModeloSTT:
        m = POR_ID.get(self.normalizar(id_))
        if m is None:
            raise KeyError(id_)
        return m

    def pasta(self, id_: str) -> Path:
        return self.cache / ("models--" + self._modelo(id_).repo.replace("/", "--"))

    def baixado(self, id_: str) -> bool:
        snaps = self.pasta(id_) / "snapshots"
        return snaps.is_dir() and any((s / "model.bin").is_file() for s in snaps.iterdir())

    def _bytes_gravados(self, id_: str) -> int:
        blobs = self.pasta(id_) / "blobs"
        if not blobs.is_dir():
            return 0
        total = 0
        for arq in blobs.iterdir():
            try:
                total += arq.stat().st_size
            except OSError:
                pass
        return total

    def progresso(self, id_: str) -> dict:
        m = self._modelo(id_)
        with self._trava:
            atual = dict(self._estados.get(m.id) or {})
        total = m.tamanho_mb * 1_000_000
        if not atual:
            atual = {"estado": "concluido" if self.baixado(m.id) else "parado", "erro": None}
        bytes_ = self._bytes_gravados(m.id) if atual["estado"] != "parado" else 0
        if atual["estado"] == "concluido":
            pct = 100
        elif atual["estado"] == "baixando":
            pct = max(0, min(99, int(bytes_ * 100 / total)))  # o tamanho é aproximado: 100 só ao terminar
        else:
            pct = 0
        return {"estado": atual["estado"], "bytes": bytes_, "total": total, "porcentagem": pct, "erro": atual.get("erro")}

    def listar(self) -> list[dict]:
        return [
            {
                "id": m.id, "nome": m.nome, "repo": m.repo, "tamanho_mb": m.tamanho_mb, "idioma": m.idioma,
                "velocidade": m.velocidade, "precisao": m.precisao, "descricao": m.descricao,
                "baixado": self.baixado(m.id), "progresso": self.progresso(m.id),
            }
            for m in CATALOGO
        ]

    def baixar(self, id_: str) -> dict:
        """Começa o download (uma vez só por modelo) e devolve o progresso."""
        m = self._modelo(id_)
        iniciar = False
        with self._trava:
            if (self._estados.get(m.id) or {}).get("estado") != "baixando":
                iniciar = not self.baixado(m.id)
                self._estados[m.id] = {"estado": "baixando" if iniciar else "concluido", "erro": None}
        if iniciar and self._em_thread:
            t = threading.Thread(target=self._executar, args=(m,), daemon=True, name=f"baixar-stt-{m.id}")
            self._threads[m.id] = t
            t.start()
        elif iniciar:
            self._executar(m)
        return self.progresso(m.id)

    def _executar(self, m: ModeloSTT) -> None:
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            self._baixador(m.repo, self.cache)
            estado = {"estado": "concluido" if self.baixado(m.id) else "falhou",
                      "erro": None if self.baixado(m.id) else "download terminou sem model.bin"}
        except Exception as exc:
            log.warning("download do modelo %s falhou: %s", m.id, exc)
            estado = {"estado": "falhou", "erro": str(exc) or type(exc).__name__}
        with self._trava:
            self._estados[m.id] = estado

    def esperar(self, id_: str, prazo: float | None = None) -> None:
        """Só para testes e encerramento: espera o download em andamento terminar."""
        t = self._threads.get(self._modelo(id_).id)
        if t is not None:
            t.join(prazo)

    def apagar(self, id_: str) -> None:
        m = self._modelo(id_)
        with self._trava:
            if (self._estados.get(m.id) or {}).get("estado") == "baixando":
                raise RuntimeError("modelo ainda baixando")
            self._estados.pop(m.id, None)
        pasta = self.pasta(m.id)
        if pasta.exists():
            shutil.rmtree(pasta)


def caminho_hud() -> Path:
    """Mesmo endereço do núcleo (nucleo/vard/ajustes.py): pasta informada pelo app ou a da instalação."""
    pasta = os.environ.get("VARD_HUD_CONFIG_DIR", "").strip()
    if pasta:
        return Path(pasta) / "hud.config.json"
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "io.github.pauloroos.vard" / "hud.config.json"


def ler_escolha_hud(caminho: Path | None = None) -> dict:
    """Só os campos stt_* do hud.config.json; ausente ou inválido devolve {}."""
    try:
        dados = json.loads((caminho or caminho_hud()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {k: dados[k] for k in ("stt_modelo", "stt_dispositivo") if k in dados}


def configuracao_stt(hud: Mapping, env: Mapping) -> dict:
    """Modelo, dispositivo e tipo de cálculo: hud.config.json primeiro, VARD_STT_* como reserva."""
    modelo = hud.get("stt_modelo")
    if not isinstance(modelo, str) or not modelo.strip():
        modelo = env.get("VARD_STT_MODEL") or "base"
    disp = hud.get("stt_dispositivo")
    if isinstance(disp, str) and disp in DISPOSITIVOS:
        return {"modelo": modelo.strip(), "dispositivo": disp, "device": disp, "compute": COMPUTE_POR_DISPOSITIVO[disp]}
    device = env.get("VARD_STT_DEVICE") or "cpu"
    compute = env.get("VARD_STT_COMPUTE") or "int8"
    return {"modelo": modelo.strip(), "dispositivo": device, "device": device, "compute": compute}
