import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Item 2 do acabamento 0.9.5: a barra de rolagem dos modais (.modal-miolo)
 * deve usar o mesmo estilo escuro da janela (scrollbar-width: thin + scrollbar-color com --cor-elementos),
 * em vez de ficar branca por falta de regra.
 */
describe("Modal usa rolagem escura igual à janela", () => {
  let css: string;

  it(".modal-miolo tem scrollbar-width thin e scrollbar-color derivado de --cor-elementos", () => {
    css = readFileSync(resolve(__dirname, "../src/configuracoes.css"), "utf-8");
    const match = css.match(/\.modal-miolo\s*\{([^}]*)\}/s);
    expect(match, "bloco .modal-miolo deve existir").toBeTruthy();
    const bloco = match![1];

    expect(bloco).toMatch(/scrollbar-width\s*:\s*thin/);
    // scrollbar-color deve referenciar --cor-elementos (color-mix ou var direto), não branco nem ciano hardcoded
    expect(bloco).toMatch(/scrollbar-color/);
    expect(bloco).not.toMatch(/scrollbar-color\s*:\s*(white|#fff\b|rgba?\(\s*255)/i);
    expect(bloco).toMatch(/scrollbar-color[^;]*--cor-elementos/);
  });
});