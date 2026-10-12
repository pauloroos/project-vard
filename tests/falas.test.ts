import { describe, it, expect } from "vitest";
import { FALAS, saudacaoPara } from "../src/fala/falas";

function textos(o: object): string[] {
  return Object.values(o).flatMap((v) => (typeof v === "string" ? [v] : textos(v as object)));
}

describe("falas", () => {
  it("nenhuma fala cita termos técnicos", () => {
    for (const t of textos(FALAS)) {
      expect(t).not.toMatch(/openjarvis|modelo|servidor|cérebro|\bIA\b/i);
    }
  });
  it("saudação usa o nome configurado e continua sem termos técnicos", () => {
    expect(saudacaoPara("")).toBe("Oi.");
    expect(saudacaoPara("  ")).toBe("Oi.");
    expect(saudacaoPara("Ana")).toBe("Oi, Ana.");
    expect(saudacaoPara("Ana")).not.toMatch(/openjarvis|modelo|servidor|\bIA\b/i);
  });
});
