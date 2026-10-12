// Prova contra o OpenJarvis de verdade. Só roda com HUD_REAL=1 (e o OpenJarvis no ar).
// Opcionais: HUD_REAL_URL (padrão http://127.0.0.1:8000) e HUD_REAL_WAV (um WAV falado dizendo "Preflight").
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { OpenJarvis } from "../src/conectores/openjarvis/cliente";

const real = process.env.HUD_REAL === "1";
const url = process.env.HUD_REAL_URL ?? "http://127.0.0.1:8000";
const wavPath = process.env.HUD_REAL_WAV ?? "";

describe.skipIf(!real)("OpenJarvis real", () => {
  const oj = new OpenJarvis(url);

  it.skipIf(!existsSync(wavPath))("transcreve um WAV falado", async () => {
    const b = readFileSync(wavPath);
    const wav = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
    const texto = await oj.transcrever(wav, "pt");
    console.log("TRANSCRICAO:", texto);
    expect(texto.toLowerCase()).toContain("preflight");
  }, 60000);

  it("responde sobre a hora", async () => {
    const r = await oj.perguntar([
      { role: "system", content: "Responda em até duas frases, para ser lido em voz alta." },
      { role: "user", content: "Vard, que horas são?" },
    ]);
    console.log("RESPOSTA:", r);
    expect(r.length).toBeGreaterThan(3);
    expect(r).toMatch(/\d/);
  }, 120000);

  it("sintetiza a resposta em WAV maior que 10 kB", async () => {
    const wav = await oj.sintetizar("São quatorze e trinta, senhor.", "pm_alex", 1.05);
    console.log("WAV BYTES:", wav.byteLength);
    expect(wav.byteLength).toBeGreaterThan(10000);
    expect(new TextDecoder().decode(wav.slice(0, 4))).toBe("RIFF");
  }, 60000);
});
