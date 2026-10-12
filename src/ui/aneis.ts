/** Três anéis concêntricos com escala (ticks), girando em sentidos opostos. A geometria é montada uma vez (Path2D). */

export const R_EXT = 138;
export const R_MED = 120;
export const R_INT = 102;

const GRAU = Math.PI / 180;
// graus por segundo: externo horário lento, médio anti-horário, interno horário mais rápido
const VEL_BASE = [5, -13, 22];

function arco(p: Path2D, r: number, deIni: number, deFim: number) {
  p.moveTo(Math.cos(deIni * GRAU) * r, Math.sin(deIni * GRAU) * r);
  p.arc(0, 0, r, deIni * GRAU, deFim * GRAU);
}

function ticks(p: Path2D, rBase: number, passo: number, comp: number, sentido: 1 | -1) {
  for (let g = 0; g < 360; g += passo) {
    const c = Math.cos(g * GRAU), s = Math.sin(g * GRAU);
    p.moveTo(c * rBase, s * rBase);
    p.lineTo(c * (rBase + sentido * comp), s * (rBase + sentido * comp));
  }
}

export interface EstiloAneis {
  /** cor principal e de brilho já em CSS */
  cor: string;
  brilho: string;
  /** escala dos anéis (1 = normal; <1 contrai) */
  escala: number;
  /** energia do espectro de saída, 0..1 */
  reacao: number;
  alfa: number;
}

export class Aneis {
  private angulos = [0, 0.9, 2.1];
  private readonly finosExt = new Path2D();
  private readonly ticksMenoresExt = new Path2D();
  private readonly ticksMaioresExt = new Path2D();
  private readonly arcosMed = new Path2D();
  private readonly finosMed = new Path2D();
  private readonly ticksMed = new Path2D();
  private readonly finosInt = new Path2D();
  private readonly nosInt = new Path2D();
  private readonly ticksInt = new Path2D();

  constructor() {
    // externo: aro fino + escala métrica (menor a cada 3 graus, maior a cada 15)
    arco(this.finosExt, R_EXT, 0, 360);
    ticks(this.ticksMenoresExt, R_EXT, 3, 3, -1);
    ticks(this.ticksMaioresExt, R_EXT, 15, 8, -1);
    // médio: arcos grossos com folgas + aro fino + ticks curtos
    const trechos = [[8, 62], [78, 120], [138, 196], [212, 244], [262, 322]];
    for (const [a, b] of trechos) arco(this.arcosMed, R_MED, a, b);
    arco(this.finosMed, R_MED - 7, 0, 360);
    ticks(this.ticksMed, R_MED - 7, 10, 4, -1);
    // interno: aro fino, nós a cada 30 graus e ticks para fora
    arco(this.finosInt, R_INT, 0, 360);
    for (let g = 0; g < 360; g += 30) {
      const x = Math.cos(g * GRAU) * R_INT, y = Math.sin(g * GRAU) * R_INT;
      this.nosInt.moveTo(x + 2.2, y);
      this.nosInt.arc(x, y, 2.2, 0, Math.PI * 2);
    }
    ticks(this.ticksInt, R_INT, 6, 3, 1);
  }

  /** velExt: multiplicador do anel externo; velResto: dos outros dois. */
  avancar(dt: number, velExt: number, velResto: number, reacao: number) {
    const extra = 1 + reacao * 2.5;
    this.angulos[0] += VEL_BASE[0] * velExt * extra * dt * GRAU;
    this.angulos[1] += VEL_BASE[1] * velResto * extra * dt * GRAU;
    this.angulos[2] += VEL_BASE[2] * velResto * extra * dt * GRAU;
  }

  desenhar(ctx: CanvasRenderingContext2D, e: EstiloAneis) {
    ctx.save();
    ctx.globalAlpha = e.alfa;
    ctx.scale(e.escala, e.escala);
    ctx.strokeStyle = e.cor;
    ctx.shadowColor = e.brilho;
    ctx.shadowBlur = 5 + e.reacao * 10;
    const fino = 1 + e.reacao * 0.8;

    ctx.save(); ctx.rotate(this.angulos[0]);
    ctx.lineWidth = fino; ctx.stroke(this.finosExt);
    ctx.lineWidth = 0.7; ctx.globalAlpha = e.alfa * 0.6; ctx.stroke(this.ticksMenoresExt);
    ctx.lineWidth = 1.3; ctx.globalAlpha = e.alfa; ctx.stroke(this.ticksMaioresExt);
    ctx.restore();

    ctx.save(); ctx.rotate(this.angulos[1]);
    ctx.lineWidth = 3.4 + e.reacao * 2; ctx.lineCap = "butt"; ctx.stroke(this.arcosMed);
    ctx.lineWidth = 0.8; ctx.globalAlpha = e.alfa * 0.7; ctx.stroke(this.finosMed);
    ctx.lineWidth = 0.9; ctx.stroke(this.ticksMed);
    ctx.restore();

    ctx.save(); ctx.rotate(this.angulos[2]);
    ctx.lineWidth = 1; ctx.globalAlpha = e.alfa * 0.8; ctx.stroke(this.finosInt);
    ctx.lineWidth = 0.8; ctx.stroke(this.ticksInt);
    ctx.lineWidth = 1.6; ctx.globalAlpha = e.alfa; ctx.stroke(this.nosInt);
    ctx.restore();

    ctx.restore();
  }
}
