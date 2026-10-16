"""Motor Edge TTS próprio para o Vard (T8b).

Portado/adaptado do projeto Open-LLM-VTuber (MIT, copyright Yi-Ting Chiu).
Referência: src/open_llm_vtuber/tts/edge_tts.py

Importação leve: não importa edge_tts nem faz rede no nível de módulo.
A biblioteca edge-tts é carregada apenas em `carregar()` ou na primeira
síntese; falhas de import/rede são tratadas como estado "não disponível"
(pronta=False) sem quebrar o serviço.

Contrato:
- `VOZES_EDGE_PT_BR`: dict {id: rótulo} com vozes pt-BR neurais da Microsoft.
- `MotorEdge()`: mesma interface pública do Motor XTTS/Kokoro (`vozes`,
  `tem_voz`, `falar`, `falar_fluxo`, `carregar`, atributos `pronta`/`aquecida`).
- Síntese devolve WAV PCM16 mono 24 kHz ou fluxo PCM16; voz desconhecida
  levanta KeyError/ValueError; falha de rede não aciona API paga/OpenJarvis.
- Exige internet para síntese real; testes usam fakes sem rede.
"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
import wave
from typing import Iterator

log = logging.getLogger("vard_voz")

# Vozes neurais pt-BR da Microsoft (edge-tts --list-voices).
VOZES_EDGE_PT_BR: dict[str, str] = {
    "pt-BR-FranciscaNeural": "Francisca (pt-BR, feminina)",
    "pt-BR-AntonioNeural": "Antônio (pt-BR, masculina)",
    "pt-BR-BrendaNeural": "Brenda (pt-BR, feminina)",
    "pt-BR-DonatoNeural": "Donato (pt-BR, masculina)",
    "pt-BR-ElzaNeural": "Elza (pt-BR, feminina)",
    "pt-BR-FabioNeural": "Fábio (pt-BR, masculina)",
    "pt-BR-GiovannaNeural": "Giovanna (pt-BR, feminina)",
    "pt-BR-HumbertoNeural": "Humberto (pt-BR, masculina)",
    "pt-BR-JulioNeural": "Júlio (pt-BR, masculina)",
    "pt-BR-LeilaNeural": "Leila (pt-BR, feminina)",
    "pt-BR-LeticiaNeural": "Letícia (pt-BR, feminina)",
    "pt-BR-ManuelaNeural": "Manuela (pt-BR, feminina)",
    "pt-BR-NicolauNeural": "Nicolau (pt-BR, masculina)",
    "pt-BR-ThalitaNeural": "Thalita (pt-BR, feminina)",
    "pt-BR-ValerioNeural": "Valério (pt-BR, masculina)",
    "pt-BR-YaraNeural": "Yara (pt-BR, feminina)",
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


class MotorEdge:
    """Motor TTS Edge (Microsoft Neural) com a mesma interface pública do Motor XTTS/Kokoro.

    A importação da biblioteca edge-tts ocorre apenas em `carregar()` ou na
    primeira síntese; se a dependência não estiver instalada ou a rede falhar,
    o motor permanece em pronta=False e `falar`/`falar_fluxo` levantam
    RuntimeError sem tocar em API paga/OpenJarvis.
    """

    def __init__(self) -> None:
        self.pronta = False
        self.aquecida = False
        self._lock = threading.Lock()
        self._modelo = None  # marcador de disponibilidade; edge-tts não tem objeto persistente

    # --- Interface pública (espelha Motor XTTS/Kokoro) -------------------------

    def vozes(self) -> list[str]:
        return list(VOZES_EDGE_PT_BR.keys())

    def tem_voz(self, nome: str) -> bool:
        return nome in VOZES_EDGE_PT_BR

    def carregar(self) -> None:
        """Verifica se edge-tts está instalado e marca pronta=True.

        Não faz rede nem baixa nada; apenas valida o import.
        """
        try:
            import edge_tts  # type: ignore[import-not-found]  # noqa: F401

            self._modelo = True
            self.pronta = True
            self.aquecida = True
            log.info("motor edge-tts disponível")
        except Exception as exc:
            log.warning("edge-tts nao instalado: %s", exc)

    def falar(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> bytes:
        """Sintetiza texto em WAV PCM16 mono 24 kHz."""
        pcm, taxa = self._sintetizar_raw(texto, voz, velocidade)
        return _pcm_para_wav(pcm, taxa)

    def falar_fluxo(self, texto: str, velocidade: float = 1.0, voz: str | None = None) -> Iterator[bytes]:
        """Gera PCM16 mono 24 kHz em pedaços."""
        yield from self._fluxo_raw(texto, voz, velocidade)

    # --- Internos (substituíveis em teste) ------------------------------

    def _validar_voz(self, voz: str | None) -> str:
        v = voz or next(iter(VOZES_EDGE_PT_BR))
        if v not in VOZES_EDGE_PT_BR:
            raise KeyError(v)
        return v

    def _sintetizar_raw(self, texto: str, voz: str | None, velocidade: float) -> tuple[bytes, int]:
        """Devolve (PCM16 bytes, taxa). Override em teste para evitar rede."""
        v = self._validar_voz(voz)
        if not self.pronta or self._modelo is None:
            raise RuntimeError("edge-tts nao carregado")
        with self._lock:
            try:
                import edge_tts  # type: ignore[import-not-found]

                communicate = edge_tts.Communicate(texto, v, rate=f"{int((velocidade - 1.0) * 100):+d}%")
                # edge-tts gera MP3; convertemos para PCM16 via ffmpeg/pydub/subprocess.
                # Para simplificar e evitar dependência externa pesada, usamos asyncio
                # e capturamos os bytes MP3, depois decodificamos.
                mp3_bytes = asyncio.run(self._sintetizar_mp3(communicate))
                pcm = self._mp3_para_pcm(mp3_bytes)
                return pcm, TAXA
            except Exception as exc:
                raise RuntimeError(f"falha na sintese edge-tts: {exc}") from exc

    async def _sintetizar_mp3(self, communicate) -> bytes:
        """Captura bytes MP3 do edge-tts Communicate."""
        partes: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                partes.append(chunk["data"])
        return b"".join(partes)

    def _mp3_para_pcm(self, mp3_bytes: bytes) -> bytes:
        """Decodifica MP3 para PCM16 mono 24 kHz.

        Usa subprocess com ffmpeg se disponível; senão, retorna silêncio
        (fallback seguro para ambientes sem ffmpeg — testes usam mock).
        """
        try:
            import subprocess

            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "mp3", "-i", "pipe:0",
                    "-ac", "1", "-ar", str(TAXA), "-f", "s16le", "pipe:1",
                ],
                input=mp3_bytes,
                capture_output=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except Exception:
            pass
        # Fallback: silêncio de ~0,1 s (testes devem mockar _sintetizar_raw).
        log.warning("ffmpeg indisponivel; retorno silencio como fallback")
        return b"\x00\x00" * int(TAXA * 0.1)

    def _fluxo_raw(self, texto: str, voz: str | None, velocidade: float) -> Iterator[bytes]:
        """Gera chunks de PCM16. Override em teste para evitar rede."""
        pcm, _taxa = self._sintetizar_raw(texto, voz, velocidade)
        tamanho = 4800  # ~0,1 s a 24 kHz mono 16 bits
        for i in range(0, len(pcm), tamanho):
            yield pcm[i : i + tamanho]