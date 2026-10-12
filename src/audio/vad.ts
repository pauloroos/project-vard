export type EventoVad = "inicio" | "fim" | "teto" | null;
export class DetectorDeVoz {
  falando = false;
  private acimaDesde: number | null = null;
  private silencioDesde: number | null = null;
  private inicioFala = 0;
  private travado = false; // após o teto, só rearma depois de um silêncio
  constructor(private o: { limiar: number; inicioMs: number; fimMs: number; tetoMs: number }) {}
  reset() { this.falando = false; this.acimaDesde = this.silencioDesde = null; }
  alimentar(rms: number, agora: number): EventoVad {
    const acima = rms >= this.o.limiar;
    if (this.travado) { if (!acima) this.travado = false; return null; }
    if (!this.falando) {
      if (acima) { this.acimaDesde ??= agora; if (agora - this.acimaDesde >= this.o.inicioMs) { this.falando = true; this.inicioFala = agora; this.silencioDesde = null; return "inicio"; } }
      else this.acimaDesde = null;
      return null;
    }
    if (agora - this.inicioFala >= this.o.tetoMs) { this.reset(); this.travado = true; return "teto"; }
    if (acima) { this.silencioDesde = null; return null; }
    this.silencioDesde ??= agora;
    if (agora - this.silencioDesde >= this.o.fimMs) { this.reset(); return "fim"; }
    return null;
  }
}
