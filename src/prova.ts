// Só carregado em desenvolvimento (VITE_PROVA=falando|ouvindo|pensando|repouso): prova visual sem microfone nem gesto.
import type { Estado } from "./fala/conversa";
import type { Hud } from "./ui/hud";
import type { Nucleo } from "./ui/nucleo";

/** AnalyserNode sintético: espectro com picos que mexem no tempo e senoide no domínio do tempo. */
function analisadorFalso(amplitude: number): AnalyserNode {
  const falso = {
    fftSize: 256,
    frequencyBinCount: 128,
    getByteFrequencyData(a: Uint8Array) {
      const t = performance.now() / 1000;
      for (let i = 0; i < a.length; i++) {
        const envelope = Math.exp(-i / 35);
        const vibra = 0.55 + 0.45 * Math.sin(t * 7 + i * 0.9) * Math.sin(t * 3.1 + i * 0.37);
        a[i] = Math.max(0, Math.min(255, 255 * amplitude * envelope * vibra * 1.6));
      }
    },
    getFloatTimeDomainData(a: Float32Array) {
      const t = performance.now() / 1000;
      const env = 0.5 + 0.5 * Math.sin(t * 5);
      for (let i = 0; i < a.length; i++) a[i] = amplitude * 0.35 * env * Math.sin(i * 0.4);
    },
  };
  return falso as unknown as AnalyserNode;
}

export function ativarProva(modo: string, nucleo: Nucleo, hud: Hud) {
  const estado = (["repouso", "ouvindo", "transcrevendo", "pensando", "falando", "jogo", "erro", "fora"].includes(modo) ? modo : "repouso") as Estado;
  nucleo.setAnalisadores(analisadorFalso(estado === "ouvindo" || estado === "transcrevendo" ? 0.8 : 0.02), analisadorFalso(estado === "falando" ? 0.9 : 0.02));
  hud.setMudo(false);
  hud.setTaxa(48000);
  hud.setLatencia(320);
  nucleo.setEstado(estado);
  hud.setEstado(estado);
}
