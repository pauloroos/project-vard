import { describe, it, expect } from "vitest";
import { fluxoParaWav, pcm16ParaFloat, pcm16ParaWav, pcmParaWav, reamostrar } from "../src/audio/wav";

const txt = (v: DataView, o: number) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));

describe("wav", () => {
  it("gera cabeçalho RIFF/WAVE mono de 16 bits", () => {
    const buf = pcmParaWav(new Float32Array(16000), 16000);
    expect(buf.byteLength).toBe(44 + 32000);
    const v = new DataView(buf);
    expect(txt(v, 0)).toBe("RIFF"); expect(txt(v, 8)).toBe("WAVE");
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

describe("PCM 16 bits em fluxo", () => {
  // amostras 16384 (0x4000) e -16384 (0xC000) em little-endian
  const bytes = new Uint8Array([0x00, 0x40, 0x00, 0xc0]);

  it("converte para Float32", () => {
    const { amostras, sobra } = pcm16ParaFloat(bytes);
    expect(Array.from(amostras)).toEqual([0.5, -0.5]);
    expect(sobra.length).toBe(0);
  });
  it("amostra partida entre dois pedaços não se perde", () => {
    const a = pcm16ParaFloat(bytes.subarray(0, 3));
    expect(Array.from(a.amostras)).toEqual([0.5]);
    expect(a.sobra.length).toBe(1);
    const b = pcm16ParaFloat(bytes.subarray(3), a.sobra);
    expect(Array.from(b.amostras)).toEqual([-0.5]);
    expect(b.sobra.length).toBe(0);
  });
  it("monta o WAV em volta do PCM e lê o fluxo inteiro", async () => {
    const corpo = new ReadableStream<Uint8Array>({
      start(c) { c.enqueue(bytes.subarray(0, 1)); c.enqueue(bytes.subarray(1)); c.close(); },
    });
    const wav = await fluxoParaWav(corpo, 24000);
    expect(wav.byteLength).toBe(48);
    const v = new DataView(wav);
    expect(txt(v, 0)).toBe("RIFF"); expect(txt(v, 36)).toBe("data");
    expect(v.getUint32(24, true)).toBe(24000);
    expect(v.getUint32(40, true)).toBe(4);
    expect(v.getInt16(44, true)).toBe(16384);
    expect(v.getInt16(46, true)).toBe(-16384);
    expect(pcm16ParaWav(new Uint8Array(5), 24000).byteLength).toBe(48); // byte ímpar descartado
  });
});
