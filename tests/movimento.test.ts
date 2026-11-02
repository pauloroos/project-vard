import { describe, expect, it } from "vitest";
import {
  cadenciaFps,
  intervaloMinimoMs,
  deveDesenharQuadro,
  prefereMovimentoReduzido,
} from "../src/ui/movimento";

describe("Auxiliares de movimento e cadência", () => {
  it("em repouso usa ~30 fps", () => {
    expect(cadenciaFps({ estado: "repouso", movimentoReduzido: false })).toBe(30);
  });

  it("em repouso com movimento reduzido usa cadência menor (10 fps)", () => {
    expect(cadenciaFps({ estado: "repouso", movimentoReduzido: true })).toBe(10);
  });

  it.each(["ouvindo", "transcrevendo", "pensando", "falando"] as const)(
    "em estado ativo (%s) sem movimento reduzido usa 60 fps",
    (estado) => {
      expect(cadenciaFps({ estado, movimentoReduzido: false })).toBe(60);
    }
  );

  it.each(["ouvindo", "transcrevendo", "pensando", "falando"] as const)(
    "em estado ativo (%s) com movimento reduzido usa 30 fps",
    (estado) => {
      expect(cadenciaFps({ estado, movimentoReduzido: true })).toBe(30);
    }
  );

  it("em jogo retorna 0 fps (parado)", () => {
    expect(cadenciaFps({ estado: "jogo", movimentoReduzido: false })).toBe(0);
    expect(cadenciaFps({ estado: "jogo", movimentoReduzido: true })).toBe(0);
  });

  it("quando oculto retorna 0 fps independente do estado", () => {
    expect(cadenciaFps({ estado: "repouso", movimentoReduzido: false, oculto: true })).toBe(0);
    expect(cadenciaFps({ estado: "falando", movimentoReduzido: false, oculto: true })).toBe(0);
    expect(cadenciaFps({ estado: "pensando", movimentoReduzido: true, oculto: true })).toBe(0);
  });

  it("intervaloMinimoMs calcula corretamente o intervalo em ms", () => {
    expect(intervaloMinimoMs(60)).toBeCloseTo(16.666, 2);
    expect(intervaloMinimoMs(30)).toBeCloseTo(33.333, 2);
    expect(intervaloMinimoMs(10)).toBe(100);
    expect(intervaloMinimoMs(0)).toBe(Infinity);
    expect(intervaloMinimoMs(-1)).toBe(Infinity);
  });

  it("deveDesenharQuadro sempre desenha o primeiro quadro (ultimoDesenho === 0)", () => {
    expect(deveDesenharQuadro(100, 0, 33.33)).toBe(true);
  });

  it("deveDesenharQuadro respeita intervalo mínimo com tolerância", () => {
    const intervalo = 33.33; // 30 fps
    // Pouco tempo decorrido
    expect(deveDesenharQuadro(110, 100, intervalo)).toBe(false);
    // Tempo suficiente (33.33 - 1.5 = 31.83ms)
    expect(deveDesenharQuadro(132, 100, intervalo)).toBe(true);
    expect(deveDesenharQuadro(140, 100, intervalo)).toBe(true);
  });

  it("deveDesenharQuadro não desenha se intervalo for zero ou infinito", () => {
    expect(deveDesenharQuadro(200, 100, Infinity)).toBe(false);
    expect(deveDesenharQuadro(200, 100, 0)).toBe(false);
  });

  it("prefereMovimentoReduzido consulta matchMedia com segurança", () => {
    expect(typeof prefereMovimentoReduzido()).toBe("boolean");
  });
});
