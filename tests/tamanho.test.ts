import { describe, it, expect } from "vitest";
import { ladoDoTamanho, ladoMudou, medidasDoWidget } from "../src/ui/tamanho";

describe("tamanho do widget", () => {
  it("presets", () => {
    expect(ladoDoTamanho({ tamanho: "pequeno", tamanho_px: 999 })).toBe(240);
    expect(ladoDoTamanho({ tamanho: "medio", tamanho_px: 999 })).toBe(320);
    expect(ladoDoTamanho({ tamanho: "grande", tamanho_px: 999 })).toBe(480);
  });
  it("personalizado_limita_160_800", () => {
    expect(ladoDoTamanho({ tamanho: "personalizado", tamanho_px: 100 })).toBe(160);
    expect(ladoDoTamanho({ tamanho: "personalizado", tamanho_px: 900 })).toBe(800);
    expect(ladoDoTamanho({ tamanho: "personalizado", tamanho_px: 401.6 })).toBe(402);
    expect(ladoDoTamanho({ tamanho: "personalizado", tamanho_px: Number.NaN })).toBe(320);
  });
  it("medidas_escalam", () => {
    expect(medidasDoWidget(320)).toEqual({ lado: 320, largura: 320, altura: 360, escala: 1 });
    expect(medidasDoWidget(480)).toEqual({ lado: 480, largura: 480, altura: 540, escala: 1.5 });
    expect(medidasDoWidget(160).altura).toBe(180);
  });
});

describe("ladoMudou", () => {
  it("so_quando_o_lado_muda_de_fato", () => {
    expect(ladoMudou({ tamanho: "medio", tamanho_px: 320 }, { tamanho: "grande", tamanho_px: 320 })).toBe(true);
    expect(ladoMudou({ tamanho: "medio", tamanho_px: 320 }, { tamanho: "medio", tamanho_px: 700 })).toBe(false); // px só vale no personalizado
    expect(ladoMudou({ tamanho: "personalizado", tamanho_px: 320 }, { tamanho: "medio", tamanho_px: 700 })).toBe(false); // 320 = médio
    expect(ladoMudou({ tamanho: "personalizado", tamanho_px: 300 }, { tamanho: "personalizado", tamanho_px: 310 })).toBe(true);
  });
});
