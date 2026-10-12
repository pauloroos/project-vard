import { describe, it, expect } from "vitest";
import { DetectorDeVoz } from "../src/audio/vad";

describe("DetectorDeVoz", () => {
  const novo = () => new DetectorDeVoz({ limiar: 0.02, inicioMs: 150, fimMs: 900, tetoMs: 12000 });
  it("começa após 150 ms acima do limiar e termina após 900 ms de silêncio", () => {
    const d = novo(); let t = 0; const ev: string[] = [];
    for (; t < 200; t += 50) { const e = d.alimentar(0.1, t); if (e) ev.push(e); }
    expect(ev).toEqual(["inicio"]);
    for (; t < 1200; t += 50) { const e = d.alimentar(0.0, t); if (e) ev.push(e); }
    expect(ev).toEqual(["inicio", "fim"]);
  });
  it("um estalo curto não começa", () => {
    const d = novo(); expect(d.alimentar(0.5, 0)).toBeNull(); expect(d.alimentar(0.0, 50)).toBeNull(); expect(d.falando).toBe(false);
  });
  it("teto de 12 s encerra mesmo falando", () => {
    const d = novo(); let t = 0; let ev: string | null = null;
    for (; t <= 12500; t += 100) { const e = d.alimentar(0.1, t); if (e === "teto") ev = e; }
    expect(ev).toBe("teto"); expect(d.falando).toBe(false);
  });
});
