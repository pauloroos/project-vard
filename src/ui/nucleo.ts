import { Aneis, R_INT } from "./aneis";
import { simplex2 } from "./ruido";
import type { FonteDeEspectro } from "../sala/espectro";

export type Estado = "repouso" | "ouvindo" | "transcrevendo" | "pensando" | "falando" | "jogo" | "erro" | "fora";

/** Cor principal, cor de brilho e opacidade global por estado. */
const PALETA: Record<Estado, { c: [number, number, number]; g: [number, number, number]; alfa: number }> = {
  repouso: { c: [0, 240, 255], g: [0, 162, 255], alfa: 1 },
  ouvindo: { c: [0, 240, 255], g: [0, 162, 255], alfa: 1 },
  transcrevendo: { c: [0, 240, 255], g: [0, 162, 255], alfa: 1 },
  falando: { c: [0, 240, 255], g: [0, 162, 255], alfa: 1 },
  pensando: { c: [255, 153, 0], g: [255, 190, 70], alfa: 1 },
  jogo: { c: [120, 124, 130], g: [70, 74, 80], alfa: 0.8 },
  erro: { c: [255, 56, 56], g: [200, 20, 20], alfa: 1 },
  fora: { c: [0, 240, 255], g: [0, 162, 255], alfa: 0.4 },
};

interface Alvo {
  velExt: number; velResto: number; escala: number; fft: number;
  pulso: number; respira: number; agita: number;
}
const ALVOS: Record<Estado, Alvo> = {
  repouso: { velExt: 1, velResto: 1, escala: 1, fft: 0, pulso: 0, respira: 1, agita: 0.35 },
  ouvindo: { velExt: 0.25, velResto: 1, escala: 1, fft: 1, pulso: 0.4, respira: 0.5, agita: 0.5 },
  transcrevendo: { velExt: 0.25, velResto: 1, escala: 1, fft: 0.5, pulso: 0.2, respira: 0.5, agita: 0.4 },
  pensando: { velExt: 3.2, velResto: 3.6, escala: 0.93, fft: 0, pulso: 0, respira: 0.3, agita: 1.5 },
  falando: { velExt: 1.5, velResto: 1.8, escala: 1, fft: 1, pulso: 1, respira: 0.2, agita: 0.9 },
  jogo: { velExt: 0, velResto: 0, escala: 1, fft: 0, pulso: 0, respira: 0, agita: 0 },
  erro: { velExt: 0.4, velResto: 0.4, escala: 1, fft: 0, pulso: 0, respira: 0.6, agita: 0.3 },
  fora: { velExt: 0.5, velResto: 0.5, escala: 1, fft: 0, pulso: 0, respira: 0.6, agita: 0.25 },
};

const LADO_BASE = 320; // geometria desenhada em 320x320 e escalada para o lado pedido
const BARRAS = 48;
const SLOTS = 24; // BARRAS / 2, espelhado
const CAMADAS = 3; // graves no centro, médios no meio, agudos na borda
const R_FFT = [56, 70, 84];
const COMP_FFT = 12;
const GANHO_BANDA = [1.0, 1.35, 2.3];
const PARTICULAS = 260;
const R_ESFERA = 44;
const ONDAS = 5;
/** O núcleo é desenhado em 320x320 e reduzido: o anel externo fica com ~220 px de diâmetro. */
const ESCALA_VISUAL = 0.8;

export class Nucleo {
  private estado: Estado = "repouso";
  private entrada: FonteDeEspectro | null = null;
  private saida: FonteDeEspectro | null = null;
  private dadosFreq: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private dadosTempoE: Float32Array<ArrayBuffer> = new Float32Array(0);
  private dadosTempoS: Float32Array<ArrayBuffer> = new Float32Array(0);
  private faixas = new Int16Array(CAMADAS * SLOTS * 2);
  private faixasPara = 0;
  private fftAlvo = new Float32Array(CAMADAS * SLOTS);
  private fft = new Float32Array(CAMADAS * SLOTS);
  private raf = 0;
  private rodando = false;
  private iniciado = false;
  private ctx: CanvasRenderingContext2D;
  private aneis = new Aneis();
  private corEscolhida: { c: [number, number, number]; g: [number, number, number] } | null = null;

  // parâmetros suavizados
  private p: Alvo = { ...ALVOS.repouso };
  private cor = new Float32Array(7); // c(3) g(3) alfa
  private energiaS = 0; // nível do canal ativo suavizado, 0..1
  private ultimoT = 0;
  private fase = 0; // rotação da esfera
  private tRuido = 0;
  private tResp = 0;

  // esfera: pontos de Fibonacci pré-calculados
  private px = new Float32Array(PARTICULAS);
  private py = new Float32Array(PARTICULAS);
  private pz = new Float32Array(PARTICULAS);

  // ondas radiais (nascimento em ms, -1 = livre)
  private ondaNasc = new Float64Array(ONDAS).fill(-1);
  private ultimoDisparo = 0;

  private lado = LADO_BASE;

  constructor(private canvas: HTMLCanvasElement, lado = LADO_BASE) {
    this.ctx = canvas.getContext("2d")!;
    this.redimensionar(lado);
    const ouro = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < PARTICULAS; i++) {
      const y = 1 - (i / (PARTICULAS - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      this.px[i] = Math.cos(ouro * i) * r; this.py[i] = y; this.pz[i] = Math.sin(ouro * i) * r;
    }
    this.fixarCor(this.estado);
  }

  /** Muda o tamanho do desenho (tamanho do widget, tela cheia da sala). Canvas no tamanho real x DPR: nada desfoca. */
  redimensionar(lado: number) {
    const dpr = window.devicePixelRatio || 1;
    this.lado = lado;
    this.canvas.width = Math.round(lado * dpr); this.canvas.height = Math.round(lado * dpr);
    this.canvas.style.width = `${lado}px`; this.canvas.style.height = `${lado}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (this.iniciado && !this.rodando) this.desenhar(performance.now()); // parado (jogo): redesenha uma vez
  }

  setEstado(e: Estado) {
    this.estado = e;
    if (!this.iniciado) { this.fixarCor(e); return; }
    if (e === "jogo") {
      this.parar();
      this.p = { ...ALVOS.jogo }; this.fixarCor(e);
      this.desenhar(performance.now());
    } else if (!this.rodando) {
      this.iniciar();
    }
  }

  setAnalisadores(entrada: FonteDeEspectro | null, saida: FonteDeEspectro | null) { this.entrada = entrada; this.saida = saida; }

  /** Vazio restaura a paleta original. Estados de alerta conservam sua própria cor. */
  definirCor(hex: string | null) {
    if (hex && /^#[\da-f]{6}$/i.test(hex)) {
      const c: [number, number, number] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
      this.corEscolhida = { c, g: derivarBrilho(c) };
    } else this.corEscolhida = null;
    if (!this.iniciado) this.fixarCor(this.estado);
  }

  private paleta(e: Estado) {
    const pal = PALETA[e];
    return this.corEscolhida && ["repouso", "ouvindo", "falando", "fora"].includes(e)
      ? { ...this.corEscolhida, alfa: pal.alfa } : pal;
  }

  iniciar() {
    this.iniciado = true;
    if (this.rodando) return;
    this.ultimoT = 0;
    if (this.estado === "jogo") { this.p = { ...ALVOS.jogo }; this.fixarCor("jogo"); this.desenhar(performance.now()); return; }
    this.rodando = true;
    const laco = (t: number) => {
      if (!this.rodando) return;
      this.desenhar(t);
      this.raf = requestAnimationFrame(laco);
    };
    this.raf = requestAnimationFrame(laco);
  }

  parar() { this.rodando = false; cancelAnimationFrame(this.raf); this.raf = 0; }

  private fixarCor(e: Estado) {
    const pal = this.paleta(e);
    this.cor.set(pal.c, 0); this.cor.set(pal.g, 3); this.cor[6] = pal.alfa;
  }

  /** Mapeia, uma vez por tamanho de FFT, a faixa de bins de cada slot de cada camada. */
  private mapear(bins: number) {
    if (this.faixasPara === bins) return;
    this.faixasPara = bins;
    const util = Math.max(CAMADAS * SLOTS * 0.5, Math.floor(bins * 0.7));
    const bordas = [0, 0.12, 0.4, 1];
    for (let c = 0; c < CAMADAS; c++) {
      const ini = bordas[c] * util, fim = bordas[c + 1] * util;
      const larg = (fim - ini) / SLOTS;
      for (let s = 0; s < SLOTS; s++) {
        const a = Math.floor(ini + s * larg);
        const b = Math.max(a + 1, Math.floor(ini + (s + 1) * larg));
        const k = (c * SLOTS + s) * 2;
        this.faixas[k] = Math.min(a, bins - 1); this.faixas[k + 1] = Math.min(b, bins);
      }
    }
  }

  private lerFft(an: FonteDeEspectro) {
    if (this.dadosFreq.length !== an.frequencyBinCount) this.dadosFreq = new Uint8Array(an.frequencyBinCount);
    an.getByteFrequencyData(this.dadosFreq);
    this.mapear(this.dadosFreq.length);
    for (let c = 0; c < CAMADAS; c++) {
      for (let s = 0; s < SLOTS; s++) {
        const i = c * SLOTS + s, k = i * 2;
        let m = 0;
        for (let j = this.faixas[k]; j < this.faixas[k + 1]; j++) if (this.dadosFreq[j] > m) m = this.dadosFreq[j];
        const v = Math.pow(m / 255, 1.3) * GANHO_BANDA[c];
        this.fftAlvo[i] = v > 1 ? 1 : v;
      }
    }
  }

  /** RMS linear (0..1) do domínio do tempo do analisador; 0 se não houver. */
  private rmsEntrada(): number {
    const an = this.entrada;
    if (!an) return 0;
    if (this.dadosTempoE.length !== an.fftSize) this.dadosTempoE = new Float32Array(an.fftSize);
    an.getFloatTimeDomainData(this.dadosTempoE);
    return rms(this.dadosTempoE);
  }

  private rmsSaida(): number {
    const an = this.saida;
    if (!an) return 0;
    if (this.dadosTempoS.length !== an.fftSize) this.dadosTempoS = new Float32Array(an.fftSize);
    an.getFloatTimeDomainData(this.dadosTempoS);
    return rms(this.dadosTempoS);
  }

  private css(off: number, a: number): string {
    const k = this.cor;
    return `rgba(${k[off] | 0},${k[off + 1] | 0},${k[off + 2] | 0},${a})`;
  }

  private desenhar(t: number) {
    const ctx = this.ctx;
    const dt = this.ultimoT ? Math.min(0.05, (t - this.ultimoT) / 1000) : 0;
    this.ultimoT = t;
    const e = this.estado;
    const alvo = ALVOS[e];

    // suavização dos parâmetros (~150 ms) e da cor (~300 ms)
    if (e !== "jogo") {
      const kp = 1 - Math.exp(-dt / 0.15);
      const q = this.p;
      q.velExt += (alvo.velExt - q.velExt) * kp; q.velResto += (alvo.velResto - q.velResto) * kp;
      q.escala += (alvo.escala - q.escala) * kp; q.fft += (alvo.fft - q.fft) * kp;
      q.pulso += (alvo.pulso - q.pulso) * kp;
      q.respira += (alvo.respira - q.respira) * kp; q.agita += (alvo.agita - q.agita) * kp;
      const kc = 1 - Math.exp(-dt / 0.1);
      const pal = this.paleta(e);
      for (let i = 0; i < 3; i++) {
        this.cor[i] += (pal.c[i] - this.cor[i]) * kc;
        this.cor[3 + i] += (pal.g[i] - this.cor[3 + i]) * kc;
      }
      this.cor[6] += (pal.alfa - this.cor[6]) * kc;
    }
    const p = this.p;

    // níveis (medidores) e espectro
    const linE = this.rmsEntrada(), linS = this.rmsSaida();

    const fonteFft = e === "falando" ? this.saida : e === "ouvindo" ? this.entrada : null;
    if (fonteFft) this.lerFft(fonteFft); else this.fftAlvo.fill(0);
    const ks = fonteFft ? 0.4 : 0.15;
    let soma = 0;
    for (let i = 0; i < this.fft.length; i++) {
      this.fft[i] += (this.fftAlvo[i] - this.fft[i]) * ks;
      soma += this.fft[i];
    }
    const reacao = e === "falando" ? Math.min(1, (soma / this.fft.length) * 2.2) : 0;
    const alvoE = e === "falando" ? Math.min(1, linS * 4) : e === "ouvindo" ? Math.min(1, linE * 4) : 0;
    this.energiaS += (alvoE - this.energiaS) * (alvoE > this.energiaS ? 0.5 : 0.15);

    this.aneis.avancar(dt, p.velExt, p.velResto, reacao);
    this.tRuido += dt * (0.25 + 0.55 * p.agita);
    this.fase += dt * (0.25 + 0.5 * p.agita);
    this.tResp += dt;

    const alfa = this.cor[6];
    ctx.clearRect(0, 0, this.lado, this.lado);
    ctx.save();
    ctx.translate(this.lado / 2, this.lado / 2);
    const k = ESCALA_VISUAL * (this.lado / LADO_BASE);
    ctx.scale(k, k);

    // halo de fundo
    const halo = ctx.createRadialGradient(0, 0, 10, 0, 0, 142);
    halo.addColorStop(0, this.css(3, 0.10 * alfa));
    halo.addColorStop(0.7, this.css(3, 0.03 * alfa));
    halo.addColorStop(1, this.css(3, 0));
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(0, 0, 142, 0, Math.PI * 2); ctx.fill();

    this.aneis.desenhar(ctx, { cor: this.css(0, 1), brilho: this.css(3, 0.9), escala: p.escala, alfa, reacao });
    this.desenharFft(ctx, alfa, p.escala);
    this.desenharOndas(ctx, t, alfa, e === "falando");
    this.desenharEsfera(ctx, alfa);
    ctx.restore();
  }

  private desenharFft(ctx: CanvasRenderingContext2D, alfa: number, escala: number) {
    ctx.save();
    ctx.scale(escala, escala);
    ctx.lineCap = "round";
    ctx.lineWidth = 2;
    ctx.shadowColor = this.css(3, 1);
    ctx.shadowBlur = 4;
    const mix = this.p.fft;
    for (let c = 0; c < CAMADAS; c++) {
      ctx.strokeStyle = this.css(0, (0.55 + 0.15 * c) * alfa);
      ctx.beginPath();
      const r0 = R_FFT[c];
      for (let i = 0; i < BARRAS; i++) {
        const slot = i < SLOTS ? i : BARRAS - 1 - i;
        const v = this.fft[c * SLOTS + slot] * mix;
        const comp = 1.4 + v * COMP_FFT;
        const ang = (i / BARRAS) * Math.PI * 2 - Math.PI / 2;
        const co = Math.cos(ang), si = Math.sin(ang);
        ctx.moveTo(co * r0, si * r0);
        ctx.lineTo(co * (r0 + comp), si * (r0 + comp));
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  private desenharOndas(ctx: CanvasRenderingContext2D, t: number, alfa: number, falando: boolean) {
    if (falando && this.energiaS > 0.12 && t - this.ultimoDisparo > 260) {
      for (let i = 0; i < ONDAS; i++) {
        if (this.ondaNasc[i] < 0) { this.ondaNasc[i] = t; this.ultimoDisparo = t; break; }
      }
    }
    ctx.lineWidth = 1.6;
    for (let i = 0; i < ONDAS; i++) {
      const nasc = this.ondaNasc[i];
      if (nasc < 0) continue;
      const idade = (t - nasc) / 1000;
      if (idade > 1) { this.ondaNasc[i] = -1; continue; }
      ctx.strokeStyle = this.css(0, (1 - idade) * 0.55 * alfa);
      ctx.beginPath();
      ctx.arc(0, 0, 30 + idade * (R_INT - 4 - 30), 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  private desenharEsfera(ctx: CanvasRenderingContext2D, alfa: number) {
    const p = this.p;
    const respira = 1 + 0.05 * p.respira * Math.sin(2 * Math.PI * 0.8 * this.tResp);
    const pulso = 1 + p.pulso * this.energiaS * 0.35;
    const raio = R_ESFERA * respira * pulso;
    const amp = 0.22 + 0.2 * p.agita + this.energiaS * 0.3;

    const nucleo = ctx.createRadialGradient(0, 0, 0, 0, 0, raio * 1.5);
    nucleo.addColorStop(0, this.css(0, (0.55 + 0.3 * this.energiaS) * alfa));
    nucleo.addColorStop(0.45, this.css(3, 0.22 * alfa));
    nucleo.addColorStop(1, this.css(3, 0));
    ctx.fillStyle = nucleo;
    ctx.beginPath(); ctx.arc(0, 0, raio * 1.5, 0, Math.PI * 2); ctx.fill();

    const ca = Math.cos(this.fase), sa = Math.sin(this.fase);
    const tn = this.tRuido;
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = this.css(0, 1);
    for (let i = 0; i < PARTICULAS; i++) {
      const x = this.px[i], y = this.py[i], z = this.pz[i];
      const n = simplex2(x * 1.8 + tn, (y + z) * 1.8 - tn * 0.7);
      const r = raio * (1 + amp * n);
      const x1 = x * ca + z * sa;
      const z1 = -x * sa + z * ca;
      const prof = (z1 + 1) * 0.5;
      ctx.globalAlpha = (0.2 + 0.8 * prof) * alfa;
      const s = 1 + prof * 1.1;
      ctx.fillRect(x1 * r - s / 2, y * r - s / 2, s, s);
    }
    ctx.restore();
  }
}

/** Preserva matiz/saturação HSL e limita a luminosidade a 55–65% para o fundo escuro. */
function derivarBrilho(cor: [number, number, number]): [number, number, number] {
  const menor = Math.min(...cor) / 255;
  const maior = Math.max(...cor) / 255;
  const faixa = maior - menor;
  const luminosidade = (maior + menor) / 2;
  const alvo = Math.max(0.55, Math.min(0.65, luminosidade));
  if (faixa === 0) return [1, 1, 1].map(() => Math.round(alvo * 255)) as [number, number, number];
  const saturacao = faixa / (1 - Math.abs(2 * luminosidade - 1));
  const novaFaixa = (1 - Math.abs(2 * alvo - 1)) * saturacao;
  const base = alvo - novaFaixa / 2;
  return cor.map((v) => Math.round((base + (v / 255 - menor) / faixa * novaFaixa) * 255)) as [number, number, number];
}

function rms(buf: Float32Array): number {
  let soma = 0;
  for (let i = 0; i < buf.length; i++) soma += buf[i] * buf[i];
  return Math.sqrt(soma / buf.length);
}
