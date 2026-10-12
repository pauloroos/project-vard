/** Toca WAVs pelo mesmo AudioContext do microfone; expõe um analisador para o núcleo reagir. */
export class Boca {
  readonly analisador: AnalyserNode;
  falando = false;
  private fonte: AudioBufferSourceNode | null = null;
  private fim: (() => void) | null = null;

  constructor(private contexto: AudioContext) {
    this.analisador = contexto.createAnalyser();
    this.analisador.fftSize = 256;
    this.analisador.smoothingTimeConstant = 0.8;
    this.analisador.connect(contexto.destination);
  }

  async tocar(wav: ArrayBuffer): Promise<void> {
    this.parar();
    if (this.contexto.state === "suspended") await this.contexto.resume();
    const buffer = await this.contexto.decodeAudioData(wav.slice(0));
    const fonte = this.contexto.createBufferSource();
    fonte.buffer = buffer;
    fonte.connect(this.analisador);
    this.fonte = fonte;
    this.falando = true;
    await new Promise<void>((resolve) => {
      const terminar = () => {
        if (this.fonte === fonte) { this.fonte = null; this.falando = false; }
        this.fim = null;
        resolve();
      };
      this.fim = terminar;
      fonte.onended = terminar;
      fonte.start();
    });
  }

  parar(): void {
    const f = this.fonte;
    if (!f) return;
    try { f.stop(); } catch { /* já parada */ }
    this.fim?.();
  }
}
