import { describe, it, expect } from "vitest";
import { cortarEmFrases } from "../src/fala/frases";

describe("fala por frase completa (FR-008)", () => {
  it("corta frases longas em múltiplas partes pela pontuação", () => {
    const texto = "Olá, tudo bem com você? Espero que sim, vamos começar.";
    const frases = cortarEmFrases(texto);
    // Duas frases separadas por ponto de interrogação e ponto final
    expect(frases.length).toBeGreaterThanOrEqual(2);
    expect(frases[0]).toContain("Olá, tudo bem com você?");
    expect(frases[frases.length - 1]).toContain("vamos começar.");
  });

  it("mantém fragmentos curtos juntos quando não há pontuação suficiente", () => {
    const texto = "Oi! Tudo bem?";
    const frases = cortarEmFrases(texto);
    expect(frases.length).toBeGreaterThanOrEqual(1);
    // Cada parte deve ter conteúdo significativo
    for (const f of frases) {
      expect(f.length).toBeGreaterThan(0);
    }
  });

  it("não fala fragmentos incompletos durante streaming simulado", () => {
    // Simula acumulação incremental: apenas frases completas (com pontuação) devem ser faladas
    const buffer: string[] = [];
    const acumulador: string[] = [];

    // Fragmentos como chegariam via TEXTO events
    const fragmentos = [
      "Olá, ",
      "tudo bem ",
      "com você? ",
      "Espero que sim, ",
      "vamos começar.",
    ];

    for (const frag of fragmentos) {
      buffer.push(frag);
      const textoAtual = buffer.join("");
      const frases = cortarEmFrases(textoAtual);
      // Só as frases completas (todas exceto possivelmente a última) são despachadas
      if (frases.length > 1) {
        // As primeiras são completas; a última pode ser parcial
        for (let i = 0; i < frases.length - 1; i++) {
          acumulador.push(frases[i]);
        }
        // Mantém o resto no buffer para o próximo evento
        buffer.length = 0;
        buffer.push(frases[frases.length - 1]);
      }
    }

    // Flush final: o que sobrou no buffer
    const resto = buffer.join("").trim();
    if (resto) acumulador.push(resto);

    // Deve ter pelo menos 2 frases completas despachadas
    expect(acumulador.length).toBeGreaterThanOrEqual(2);
    // A primeira frase despachada deve terminar com pontuação
    expect(acumulador[0]).toMatch(/[.!?…]$/);
  });

  it("flusha todo o texto restante no evento FIM", () => {
    const texto = "Frase sem pontuação final";
    const frases = cortarEmFrases(texto);
    // Sem pontuação, tudo vira uma única frase
    expect(frases).toEqual(["Frase sem pontuação final"]);
  });
});