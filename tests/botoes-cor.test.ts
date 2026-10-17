import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Item 1 do acabamento 0.9.5: os botões redondos de baixo (#botoes button)
 * devem seguir --cor-elementos em vez de usar rgba(0, 240, 255, …) fixo.
 * Cor vazia = visual de hoje (--ciano como fallback da variável).
 */
describe("Botões redondos do widget seguem --cor-elementos", () => {
  let css: string;

  beforeEach(() => {
    css = readFileSync(resolve(__dirname, "../src/styles.css"), "utf-8");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("style");
  });

  it("fundo e borda dos botões usam var(--cor-elementos) ou color-mix derivado", () => {
    // Extrai o bloco #botoes button { ... }
    const match = css.match(/#botoes\s+button\s*\{([^}]*)\}/s);
    expect(match, "bloco #botoes button deve existir").toBeTruthy();
    const bloco = match![1];

    // Não deve conter ciano hardcoded
    expect(bloco).not.toMatch(/rgba\(\s*0\s*,\s*240\s*,\s*255/);

    // Deve referenciar --cor-elementos (direto ou via color-mix)
    expect(bloco).toMatch(/var\(--cor-elementos|color-mix\(.*--cor-elementos/);
  });

  it("hover também segue --cor-elementos em vez de ciano fixo", () => {
    const match = css.match(/#botoes\s+button:hover\s*\{([^}]*)\}/s);
    expect(match, "bloco #botoes button:hover deve existir").toBeTruthy();
    const bloco = match![1];

    expect(bloco).not.toMatch(/rgba\(\s*0\s*,\s*240\s*,\s*255/);
    expect(bloco).toMatch(/var\(--cor-elementos|color-mix\(.*--cor-elementos/);
  });

  it("quando --cor-elementos está vazio, fallback é --ciano (visual atual)", () => {
    // A variável --cor-elementos já tem fallback para var(--ciano) em aplicarAparencia;
    // aqui confirmamos que o CSS não reintroduz um valor hardcoded que quebraria isso.
    const match = css.match(/#botoes\s+button\s*\{([^}]*)\}/s);
    expect(match).toBeTruthy();
    // Nenhum valor hex/rgb fixo para cor de fundo/borda
    expect(match![1]).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});