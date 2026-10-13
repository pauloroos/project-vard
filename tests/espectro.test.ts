import { describe, it, expect } from "vitest";
import { EspectroRemoto, lerNiveis } from "../src/sala/espectro";

describe("espectro remoto", () => {
  it("espectro_remoto_ida_e_volta", () => {
    const r = new EspectroRemoto();
    r.atualizar({ bins: [300, -5, 7.9, 128], rms: 0.3 });
    const n = lerNiveis(r);
    expect(n.bins.slice(0, 5)).toEqual([255, 0, 7, 128, 0]);
    expect(n.bins.length).toBe(128);
    expect(n.rms).toBeCloseTo(0.3, 5);
  });
  it("niveis_ruins_viram_zero", () => {
    const r = new EspectroRemoto();
    r.atualizar({ bins: [9, 9], rms: 0.5 });
    r.atualizar(null);
    expect(lerNiveis(r)).toEqual({ bins: new Array(128).fill(0), rms: 0 });
    r.atualizar({ bins: "x" as unknown as number[], rms: Number.NaN });
    expect(lerNiveis(r).rms).toBe(0);
  });
});
