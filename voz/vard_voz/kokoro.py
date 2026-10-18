"""Motor Kokoro do serviço de voz do Vard, sem OpenJarvis.

Usa o pacote `kokoro-onnx` (extra `kokoro` do voz/pyproject.toml; MIT, https://github.com/thewh1teagle/kokoro-onnx)
com o modelo Kokoro-82M v1.0 em ONNX (pesos Apache-2.0, https://huggingface.co/hexgrad/Kokoro-82M). Os dois
arquivos do modelo (`kokoro-v1.0.int8.onnx`, ~88 MB, e `voices-v1.0.bin`, ~27 MB) vêm do pacote opcional `kokoro`
do instalador de vozes (config/pacotes/vozes.json), que os grava em `<dados do Vard>/pacotes/ativo/kokoro`.
Nada é baixado aqui: sem a biblioteca ou sem os arquivos, o motor fica "não instalado" (pronta=False).

Importação leve: este módulo não importa onnxruntime/kokoro_onnx nem toca na GPU; só `carregar()` o faz.
Roda na CPU (onnxruntime) e, com `device="cuda"` e o onnxruntime-gpu instalado, na GPU com reserva na CPU.

Contrato (mesma interface pública do Motor XTTS):
- `VOZES_KOKORO`: dict {id: rótulo} com IDs estáveis (iguais a config/vozes.json).
- `MotorKokoro(device)`: `vozes`, `tem_voz`, `instalado`, `carregar`, `falar`, `falar_fluxo`, `pronta`/`aquecida`.
- Síntese devolve WAV PCM16 mono 24 kHz ou fluxo PCM16; voz desconhecida levanta KeyError; falha local
  levanta RuntimeError sem acionar API paga nem OpenJarvis.
"""
from __future__ import annotations

import importlib.util
import io
import logging
import os
import tempfile
import threading
import wave
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger("vard_voz")

# IDs estáveis compatíveis com config/vozes.json (lista "kokoro") e src/conectores/voz/kokoro.ts.
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
# Pacote do instalador de vozes (config/pacotes/vozes.json) que traz os arquivos do modelo.
PACOTE_ID = "kokoro"
ARQUIVO_VOZES = "voices-v1.0.bin"
# O instalador grava o arquivo principal do pacote como "download.dat"; um modelo posto à mão mantém o nome original.
ARQUIVOS_MODELO = ("kokoro-v1.0.int8.onnx", "kokoro-v1.0.onnx", "download.dat")
# Primeira letra do ID da voz -> idioma do espeak-ng usado pelo kokoro-onnx para os fonemas.
IDIOMA_POR_PREFIXO = {"p": "pt-br", "a": "en-us", "b": "en-gb"}
# Faixa de velocidade aceita pelo kokoro-onnx.
VELOCIDADE_MIN, VELOCIDADE_MAX = 0.5, 2.0

Fabrica = Callable[[Path, Path, list[str]], Any]


def pasta_modelo(env: Mapping[str, str] | None = None) -> Path:
    """Pasta dos arquivos do modelo: VARD_KOKORO_DIR, senão a pasta do pacote no instalador de vozes
    (`VARD_DADOS` ou `%LOCALAPPDATA%/rdl-vard`, a mesma raiz do instalador do núcleo)."""
    env = os.environ if env is None else env
    direta = env.get("VARD_KOKORO_DIR")
    if direta:
        return Path(direta)
    if env.get("VARD_DADOS"):
        raiz = Path(env["VARD_DADOS"])
    elif env.get("LOCALAPPDATA"):
        raiz = Path(env["LOCALAPPDATA"]) / "rdl-vard"
    else:
        raiz = Path(tempfile.gettempdir()) / "vard-dados-teste"
    return raiz / "pacotes" / "ativo" / PACOTE_ID


def arquivos_modelo(pasta: Path) -> tuple[Path, Path] | None:
    """(modelo, vozes) quando os dois estão na pasta; None se falta algum."""
    vozes = pasta / ARQUIVO_VOZES
    if not vozes.is_file():
        return None
    for nome in ARQUIVOS_MODELO:
        modelo = pasta / nome
        if modelo.is_file():
            return modelo, vozes
    return None


def biblioteca_instalada() -> bool:
    """kokoro-onnx presente no ambiente do serviço de voz (sem importar)."""
    return importlib.util.find_spec("kokoro_onnx") is not None


def idioma_da_voz(voz: str) -> str:
    return IDIOMA_POR_PREFIXO.get(voz[:1], "pt-br")


def _provedores_disponiveis() -> list[str]:
    import onnxruntime as rt  # import tardio: só na carga

    return list(rt.get_available_providers())


def _fabrica_padrao(modelo: Path, vozes: Path, provedores: list[str]) -> Any:
    """Sessão ONNX nos provedores pedidos + Kokoro do kokoro-onnx sobre ela."""
    import onnxruntime as rt
    from kokoro_onnx import Kokoro  # type: ignore[import-not-found]

    sessao = rt.InferenceSession(str(modelo), providers=provedores)
    return Kokoro.from_session(sessao, str(vozes))


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
    """Motor TTS Kokoro (kokoro-onnx) com a mesma interface pública do Motor XTTS.

    `fabrica` e `provedores_disponiveis` existem para os testes trocarem a biblioteca por um falso.
    """

    def __init__(
        self,
        device: str = "cpu",
        pasta: Path | None = None,
        fabrica: Fabrica | None = None,
        provedores_disponiveis: Callable[[], list[str]] | None = None,
    ) -> None:
        self.device = device
        self.pronta = False
        self.aquecida = False
        self._pasta = pasta
        self._fabrica = fabrica or _fabrica_padrao
        self._provedores_disponiveis = provedores_disponiveis or _provedores_disponiveis
        self._lock = threading.Lock()
        self._modelo: Any = None

    # --- Interface pública (espelha Motor XTTS) -------------------------

    @property
    def pasta(self) -> Path:
        return self._pasta if self._pasta is not None else pasta_modelo()

    def vozes(self) -> list[str]:
        ids = list(VOZES_KOKORO)
        listar = getattr(self._modelo, "get_voices", None)
        if callable(listar):
            try:
                no_arquivo = set(listar())
            except Exception:  # noqa: BLE001 - lista estática é a reserva
                return ids
            if no_arquivo:  # arquivo sem lista legível: fica a lista estável
                return [v for v in ids if v in no_arquivo]
        return ids

    def tem_voz(self, nome: str) -> bool:
        return nome in self.vozes()

    def instalado(self) -> bool:
        """Biblioteca no ambiente e arquivos do modelo na pasta: dá para carregar sem baixar nada."""
        return biblioteca_instalada() and arquivos_modelo(self.pasta) is not None

    def provedores(self) -> list[str]:
        """Provedores ONNX na ordem de preferência: GPU (se pedida e disponível) e sempre a CPU de reserva."""
        if self.device.startswith("cuda"):
            try:
                if "CUDAExecutionProvider" in self._provedores_disponiveis():
                    return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            except Exception:  # noqa: BLE001
                log.warning("nao consegui listar os provedores do onnxruntime; uso a CPU")
        return ["CPUExecutionProvider"]

    def carregar(self) -> None:
        """Carrega o modelo dos arquivos já instalados. Sem biblioteca ou arquivos fica pronta=False (não baixa nada)."""
        with self._lock:
            if self.pronta:
                return
            if not biblioteca_instalada():
                log.info("kokoro: biblioteca kokoro-onnx ausente (extra 'kokoro' do serviço de voz)")
                return
            arquivos = arquivos_modelo(self.pasta)
            if arquivos is None:
                log.info("kokoro: modelo nao instalado (pacote '%s' do instalador de vozes)", PACOTE_ID)
                return
            provedores = self.provedores()
            try:
                self._modelo = self._fabrica(arquivos[0], arquivos[1], provedores)
            except Exception:
                log.exception("falha ao carregar kokoro")
                self._modelo = None
                return
            self.pronta = True
            self.aquecida = True
            log.info("motor kokoro carregado (provedores=%s)", ",".join(provedores))

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
        """Devolve (PCM16 bytes, taxa)."""
        v = self._validar_voz(voz)
        if not self.pronta or self._modelo is None:
            raise RuntimeError("kokoro nao carregado")
        vel = min(VELOCIDADE_MAX, max(VELOCIDADE_MIN, float(velocidade)))
        with self._lock:
            try:
                # kokoro_onnx.Kokoro.create devolve (onda float32 em [-1, 1], taxa).
                audio, taxa = self._modelo.create(texto, voice=v, speed=vel, lang=idioma_da_voz(v))
            except Exception as exc:
                raise RuntimeError(f"falha na sintese kokoro: {exc}") from exc
        import numpy as np  # import tardio para permitir mock sem numpy

        onda = np.clip(np.asarray(audio, dtype="float32").reshape(-1), -1.0, 1.0)
        pcm = (onda * 32767.0).astype("<i2").tobytes()
        return pcm, int(taxa or TAXA)

    def _fluxo_raw(self, texto: str, voz: str | None, velocidade: float) -> Iterator[bytes]:
        """Gera chunks de PCM16."""
        pcm, _taxa = self._sintetizar_raw(texto, voz, velocidade)
        # Chunk de ~0,1 s (4800 bytes a 24 kHz mono 16 bits).
        tamanho = 4800
        for i in range(0, len(pcm), tamanho):
            yield pcm[i : i + tamanho]
