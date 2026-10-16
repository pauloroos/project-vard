"""Motor Piper TTS próprio para o Vard (T8b).
Portado/adaptado do projeto Open-LLM-VTuber (MIT, copyright Yi-Ting Chiu).
Referência: src/open_llm_vtuber/tts/piper_tts.py
Importação leve: não importa piper nem baixa modelo no nível de módulo.
A biblioteca piper-tts é carregada apenas em `carregar()`; o modelo ONNX
é baixado sob demanda na primeira síntese (nunca no import). Falhas de
import/modelo são tratadas como estado "não disponível" (pronta=False)
sem quebrar o serviço.
Contrato:
- `VOZES_PIPER_PT_BR`: dict {id: rótulo} com vozes pt-BR locais.
- `MotorPiper()`: mesma interface pública do Motor XTTS/Kokoro/Edge (`vozes`,
  `tem_voz`, `falar`, `falar_fluxo`, `carregar`, atributos `pronta`/`aquecida`).
- Síntese devolve WAV PCM16 mono 24 kHz ou fluxo PCM16; voz desconhecida
  levanta KeyError/ValueError; falha local não aciona API paga/OpenJarvis.
- Modelo ONNX baixado sob demanda; testes usam fakes sem download/GPU.
"""
from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Iterator

log = logging.getLogger("vard_voz")

# Vozes Piper pt-BR disponíveis (modelos ONNX em models/piper/).
# IDs seguem convenção do HuggingFace csukuangfj/vits-piper-pt_BR-*.
VOZES_PIPER_PT_BR: dict[str, str] = {
    "pt_BR-feminina-medium": "Feminina (pt-BR, medium)",
    "pt_BR-masculina-medium": "Masculina (pt-BR, medium)",
    "pt_BR-feminina-low": "Feminina (pt-BR, low)",
    "pt_BR-masculina-low": "Masculina (pt-BR, low)",
}

TAXA = 24000


def _pcm_para_wav(pcm: bytes, taxa: int = TAXA) -> bytes:
    """Converte PCM16 mono em WAV PCM16 mono."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buf.getvalue()


class MotorPiper:
    """Motor TTS Piper (local, CPU) com a mesma interface pública do Motor XTTS/Kokoro/Edge.

    A importação da biblioteca piper-tts ocorre apenas em `carregar()`; o
    modelo ONNX é baixado sob demanda na primeira síntese. Se a dependência
    não estiver instalada ou o modelo não existir, o motor permanece em
    pronta=False e `falar`/`falar_fluxo` levantam RuntimeError sem tocar
    em API paga/OpenJarvis.
    """

    def __init__(self) -> None:
        self.pronta = False
        self.aquecida = False
        self._lock = threading.Lock()
        self._modelo = None  # PiperVoice instance quando carregado

    # --- Interface pública (espelha Motor XTTS/Kokoro/Edge) -------------------------

    def vozes(self) -> list[str]:
        return list(VOZES_PIPER_PT_BR.keys())

    def tem_voz(self, nome: str) -> bool:
        return nome in VOZES_PIPER_PT_BR

    def carregar(self) -> None:
        """Verifica se piper-tts está instalado e marca pronta=True.

        Não baixa modelo nem exige GPU; apenas valida o import.
        O modelo ONNX será carregado sob demanda na primeira síntese.
        """
        try:
            from piper import PiperVoice  # type: ignore[import-not-found]  # noqa: F401

            self._modelo = True  # marcador de disponibilidade
            self.pronta = True
            self.aquecida = True
            log.info("motor piper-tts disponível")
        except Exception as exc:
            log.warning("piper-tts nao instalado: %s", exc)

    def falar(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> bytes:
        """Sintetiza texto em WAV PCM16 mono 24 kHz."""
        pcm, taxa = self._sintetizar_raw(texto, voz, velocidade)
        return _pcm_para_wav(pcm, taxa)

    def falar_fluxo(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> Iterator[bytes]:
        """Gera PCM16 mono 24 kHz em pedaços."""
        yield from self._fluxo_raw(texto, voz, velocidade)

    # --- Internos (substituíveis em teste) ------------------------------

    def _validar_voz(self, voz: str | None) -> str:
        v = voz or next(iter(VOZES_PIPER_PT_BR))
        if v not in VOZES_PIPER_PT_BR:
            raise KeyError(v)
        return v

    def _sintetizar_raw(self, texto: str, voz: str | None, velocidade: float) -> tuple[bytes, int]:
        """Devolve (PCM16 bytes, taxa). Override em teste para evitar download/GPU."""
        v = self._validar_voz(voz)
        if not self.pronta or self._modelo is None:
            raise RuntimeError("piper-tts nao carregado")
        with self._lock:
            try:
                from piper import PiperVoice  # type: ignore[import-not-found]
                from piper.voice import SynthesisConfig  # type: ignore[import-not-found]

                # Carrega modelo sob demanda (download se não existir localmente).
                model_path = f"models/piper/{v}.onnx"
                voice_model = PiperVoice.load(model_path)
                config = SynthesisConfig(length_scale=1.0 / max(velocidade, 0.1))
                # Piper gera PCM16 nativamente; coletamos os samples.
                audio_iter = voice_model.synthesize_stream_raw(texto, config=config)
                pcm_parts: list[bytes] = []
                for chunk in audio_iter:
                    pcm_parts.append(chunk)
                pcm = b"".join(pcm_parts)
                return pcm, TAXA
            except Exception as exc:
                raise RuntimeError(f"falha na sintese piper: {exc}") from exc

    def _fluxo_raw(self, texto: str, voz: str | None, velocidade: float) -> Iterator[bytes]:
        """Gera chunks de PCM16. Override em teste para evitar download/GPU."""
        pcm, _taxa = self._sintetizar_raw(texto, voz, velocidade)
        tamanho = 4800  # ~0,1 s a 24 kHz mono 16 bits
        for i in range(0, len(pcm), tamanho):
            yield pcm[i : i + tamanho]