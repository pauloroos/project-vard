import { describe, it, expect, vi } from "vitest";
import { Boca } from "../src/audio/boca";

class FonteFalsa {
  buffer: { duration: number; length: number } | null = null;
  onended: (() => void) | null = null;
  inicio = -1;
  parada = false;
  connect() {}
  start(t = 0) { this.inicio = t; }
  stop() { this.parada = true; }
}

function contextoFalso() {
  const fontes: FonteFalsa[] = [];
  const ctx = {
    currentTime: 0, state: "running", destination: {},
    createAnalyser: () => ({ connect() {}, fftSize: 0, smoothingTimeConstant: 0 }),
    createBuffer: (_c: number, n: number, taxa: number) => { const d = new Float32Array(n); return { duration: n / taxa, length: n, getChannelData: () => d }; },
    createBufferSource: () => { const f = new FonteFalsa(); fontes.push(f); return f; },
    resume: async () => {},
  };
  return { ctx: ctx as unknown as AudioContext, fontes };
}

/** Fluxo controlado à mão: `mandar` enfileira bytes, `fechar` encerra. */
function fluxoManual() {
  let c!: ReadableStreamDefaultController<Uint8Array>;
  const cancelado = vi.fn();
  const corpo = new ReadableStream<Uint8Array>({ start(x) { c = x; }, cancel: cancelado });
  return { corpo, cancelado, mandar: (n: number) => c.enqueue(new Uint8Array(n)), fechar: () => c.close() };
}

const tique = async (n = 5) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };

describe("Boca.tocarFluxo", () => {
  it("agenda os pedaços um atrás do outro e resolve quando o último termina", async () => {
    const { ctx, fontes } = contextoFalso();
    const boca = new Boca(ctx);
    const f = fluxoManual();
    let resolvido = false;
    const p = boca.tocarFluxo(f.corpo, 24000).then(() => { resolvido = true; });
    f.mandar(4801); // 0,1 s mais meio sample: o byte solto vai para o próximo pedaço
    await tique();
    expect(boca.falando).toBe(true);
    f.mandar(4799);
    f.mandar(4800);
    f.fechar();
    await tique();
    expect(fontes.map((x) => x.buffer?.length)).toEqual([2400, 2400, 2400]);
    expect(fontes[0].inicio).toBeCloseTo(0.02);
    expect(fontes[1].inicio).toBeCloseTo(0.12);
    expect(fontes[2].inicio).toBeCloseTo(0.22);
    expect(resolvido).toBe(false);
    fontes[0].onended?.(); fontes[1].onended?.();
    await tique();
    expect(resolvido).toBe(false);
    fontes[2].onended?.();
    await p;
    expect(boca.falando).toBe(false);
  });

  it("espera ~100 ms de áudio antes do primeiro trecho", async () => {
    const { ctx, fontes } = contextoFalso();
    const boca = new Boca(ctx);
    const f = fluxoManual();
    const p = boca.tocarFluxo(f.corpo, 24000);
    f.mandar(2000); // 1000 amostras = 42 ms
    await tique();
    expect(fontes).toHaveLength(0);
    f.mandar(4000);
    await tique();
    expect(fontes.map((x) => x.buffer?.length)).toEqual([3000]);
    f.fechar();
    await tique();
    fontes[0].onended?.();
    await p;
  });

  it("parar corta o som, cancela a leitura e resolve", async () => {
    const { ctx, fontes } = contextoFalso();
    const boca = new Boca(ctx);
    const f = fluxoManual();
    const p = boca.tocarFluxo(f.corpo, 24000);
    f.mandar(4800);
    await tique();
    boca.parar();
    await p;
    expect(fontes[0].parada).toBe(true);
    expect(f.cancelado).toHaveBeenCalled();
    expect(boca.falando).toBe(false);
  });

  it("abort do sinal tem o mesmo efeito", async () => {
    const { ctx, fontes } = contextoFalso();
    const boca = new Boca(ctx);
    const f = fluxoManual();
    const ac = new AbortController();
    const p = boca.tocarFluxo(f.corpo, 24000, ac.signal);
    f.mandar(4800);
    await tique();
    ac.abort();
    await p;
    expect(fontes[0].parada).toBe(true);
    expect(f.cancelado).toHaveBeenCalled();
  });

  it("fala mais curta que o pre-buffer ainda toca", async () => {
    const { ctx, fontes } = contextoFalso();
    const boca = new Boca(ctx);
    const f = fluxoManual();
    const p = boca.tocarFluxo(f.corpo, 24000);
    f.mandar(200);
    f.fechar();
    await tique();
    expect(fontes.map((x) => x.buffer?.length)).toEqual([100]);
    fontes[0].onended?.();
    await p;
  });
});
