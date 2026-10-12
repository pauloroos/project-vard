export type Estado = "repouso" | "ouvindo" | "pensando" | "falando" | "jogo" | "erro" | "fora";

const CORES: Record<Estado, string> = {
  repouso: "#f2b134", ouvindo: "#f2b134", falando: "#ffd166",
  pensando: "#4ea8de", jogo: "#5a5a5a", erro: "#c82828", fora: "#7a4a1e",
};
const PETALAS = 32;
const RAIO = 70;
const LADO = 320;

export class Nucleo {
  private estado: Estado = "repouso";
  private entrada: AnalyserNode | null = null;
  private saida: AnalyserNode | null = null;
  private valores = new Float32Array(PETALAS);
  private dados: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private raf = 0;
  private rodando = false;
  private iniciado = false;
  private ctx: CanvasRenderingContext2D;

  constructor(canvas: HTMLCanvasElement) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = LADO * dpr; canvas.height = LADO * dpr;
    canvas.style.width = `${LADO}px`; canvas.style.height = `${LADO}px`;
    this.ctx = canvas.getContext("2d")!;
    this.ctx.scale(dpr, dpr);
  }

  setEstado(e: Estado) {
    this.estado = e;
    if (!this.iniciado) return;
    if (e === "jogo") { this.parar(); this.desenhar(performance.now()); }
    else if (!this.rodando) this.iniciar();
  }

  setAnalisadores(entrada: AnalyserNode | null, saida: AnalyserNode | null) { this.entrada = entrada; this.saida = saida; }

  iniciar() {
    this.iniciado = true;
    if (this.rodando) return;
    if (this.estado === "jogo") { this.desenhar(performance.now()); return; }
    this.rodando = true;
    const laco = (t: number) => {
      if (!this.rodando) return;
      this.desenhar(t);
      this.raf = requestAnimationFrame(laco);
    };
    this.raf = requestAnimationFrame(laco);
  }

  parar() { this.rodando = false; cancelAnimationFrame(this.raf); }

  private alvos(): Float32Array | null {
    const an = this.estado === "falando" ? this.saida : this.estado === "ouvindo" ? this.entrada : null;
    if (!an) return null;
    if (this.dados.length !== an.frequencyBinCount) this.dados = new Uint8Array(an.frequencyBinCount);
    an.getByteFrequencyData(this.dados);
    const alvos = new Float32Array(PETALAS);
    // faixa de voz (primeiros ~60% dos bins) dividida em 32 bandas
    const util = Math.max(PETALAS, Math.floor(this.dados.length * 0.6));
    const por = util / PETALAS;
    for (let i = 0; i < PETALAS; i++) {
      let soma = 0, n = 0;
      for (let j = Math.floor(i * por); j < Math.floor((i + 1) * por) && j < this.dados.length; j++) { soma += this.dados[j]; n++; }
      alvos[i] = n ? soma / n / 255 : 0;
    }
    return alvos;
  }

  private desenhar(t: number) {
    const ctx = this.ctx;
    const alvos = this.alvos();
    for (let i = 0; i < PETALAS; i++) {
      const alvo = alvos ? alvos[i] : 0;
      this.valores[i] = this.valores[i] * 0.75 + alvo * 0.25;
    }
    const respira = this.estado === "repouso" ? 1 + 0.04 * Math.sin(t / 1200) : 1;
    const cor = CORES[this.estado];
    ctx.clearRect(0, 0, LADO, LADO);
    ctx.save();
    ctx.translate(LADO / 2, LADO / 2);
    ctx.strokeStyle = cor;
    ctx.lineWidth = 3; ctx.lineCap = "round";
    ctx.beginPath(); ctx.arc(0, 0, RAIO * respira, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < PETALAS; i++) {
      const ang = (i / PETALAS) * Math.PI * 2;
      const comp = (6 + this.valores[i] * 70) * respira;
      const r0 = RAIO * respira + 8;
      ctx.beginPath();
      ctx.moveTo(Math.cos(ang) * r0, Math.sin(ang) * r0);
      ctx.lineTo(Math.cos(ang) * (r0 + comp), Math.sin(ang) * (r0 + comp));
      ctx.stroke();
    }
    ctx.restore();
  }
}
