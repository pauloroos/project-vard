/** O que o núcleo lê de um analisador. O AnalyserNode já cumpre; a sala usa EspectroRemoto. */
export interface FonteDeEspectro {
  readonly frequencyBinCount: number;
  readonly fftSize: number;
  getByteFrequencyData(array: Uint8Array<ArrayBuffer>): void;
  getFloatTimeDomainData(array: Float32Array<ArrayBuffer>): void;
}

/** Um canal como viaja no evento sala:niveis: bins de frequência (0..255) e RMS linear. */
export interface Niveis { bins: number[]; rms: number }

/** Lê um analisador (do microfone ou da boca) para mandar à sala. */
export function lerNiveis(an: FonteDeEspectro | null): Niveis {
  if (!an) return { bins: [], rms: 0 };
  const f = new Uint8Array(an.frequencyBinCount);
  an.getByteFrequencyData(f);
  const t = new Float32Array(an.fftSize);
  an.getFloatTimeDomainData(t);
  let soma = 0;
  for (let i = 0; i < t.length; i++) soma += t[i] * t[i];
  return { bins: Array.from(f), rms: Math.sqrt(soma / t.length) };
}

/** Analisador falso, alimentado pelos eventos do widget (fftSize 256 como os reais). */
export class EspectroRemoto implements FonteDeEspectro {
  readonly frequencyBinCount = 128;
  readonly fftSize = 256;
  private bins = new Uint8Array(128);
  private rms = 0;

  atualizar(n: Partial<Niveis> | null | undefined) {
    this.bins.fill(0);
    const bins: unknown[] = n && Array.isArray(n.bins) ? n.bins : [];
    for (let i = 0; i < Math.min(bins.length, this.bins.length); i++) {
      const v = Number(bins[i]);
      this.bins[i] = Number.isFinite(v) ? Math.max(0, Math.min(255, Math.trunc(v))) : 0;
    }
    const rms = Number(n?.rms);
    this.rms = Number.isFinite(rms) && rms > 0 ? rms : 0;
  }

  getByteFrequencyData(a: Uint8Array<ArrayBuffer>) { a.set(this.bins.subarray(0, a.length)); }
  /** Sinal constante com o RMS recebido: o RMS calculado do outro lado bate. */
  getFloatTimeDomainData(a: Float32Array<ArrayBuffer>) { a.fill(this.rms); }
}
