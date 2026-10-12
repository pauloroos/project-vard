import { describe, it, expect } from "vitest";
import { pcmParaWav, reamostrar } from "../src/audio/wav";

describe("wav", () => {
  it("gera cabeçalho RIFF/WAVE mono de 16 bits", () => {
    const buf = pcmParaWav(new Float32Array(16000), 16000);
    expect(buf.byteLength).toBe(44 + 32000);
    const v = new DataView(buf);
    const txt = (o: number) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
    expect(txt(0)).toBe("RIFF"); expect(txt(8)).toBe("WAVE");
    expect(v.getUint16(22, true)).toBe(1);
    expect(v.getUint32(24, true)).toBe(16000);
    expect(v.getUint16(34, true)).toBe(16);
  });
  it("reamostra 48 kHz para 16 kHz", () => {
    const r = reamostrar(new Float32Array(48000).fill(0.5), 48000, 16000);
    expect(r.length).toBe(16000);
    expect(r[0]).toBeCloseTo(0.5); expect(r[15999]).toBeCloseTo(0.5);
  });
});
