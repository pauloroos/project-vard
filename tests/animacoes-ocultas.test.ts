import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const RAIZ = join(__dirname, "..");
const ler = (arquivo: string) => readFileSync(join(RAIZ, arquivo), "utf8");

function blocoDePausa(css: string, raiz: string): string | null {
  // Encontra o bloco { ... } da regra que menciona o seletor-raiz e animation-play-state.
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*animation-play-state[^{}]*)\}/g)) {
    if (m[1].includes(raiz)) return `${m[1]} { ${m[2]} }`;
  }
  return null;
}

describe("pausa real das animações quando oculto", () => {
  it("widget: #app.invisivel pausa tudo com !important (vence a cascata)", () => {
    const css = ler("src/styles.css");
    const bloco = blocoDePausa(css, "#app.invisivel");
    expect(bloco, "regra de pausa de #app.invisivel não encontrada em src/styles.css").not.toBeNull();
    const regra = bloco as string;
    expect(regra).toMatch(/animation-play-state\s*:\s*paused\s*!important/);
    // Cobrir descendentes e pseudoelementos (a cascata redefine `animation` depois).
    expect(regra).toMatch(/#app\.invisivel\s*\*/);
    expect(regra).toMatch(/::before/);
    expect(regra).toMatch(/::after/);
  });

  it("sala: body.oculto pausa tudo com !important (vence a cascata)", () => {
    const css = ler("src/sala.css");
    const bloco = blocoDePausa(css, "body.oculto");
    expect(bloco, "regra de pausa de body.oculto não encontrada em src/sala.css").not.toBeNull();
    const regra = bloco as string;
    expect(regra).toMatch(/animation-play-state\s*:\s*paused\s*!important/);
    expect(regra).toMatch(/body\.oculto\s*\*/);
    expect(regra).toMatch(/::before/);
    expect(regra).toMatch(/::after/);
  });

  it("sala: visibilidade oculta marca o documento", () => {
    const fonte = ler("src/sala-main.ts");
    expect(fonte).toMatch(/classList\.toggle\(\s*["']oculto["']/);
  });

  it("widget: janela oculta também pausa as animações CSS", () => {
    const fonte = ler("src/main.ts");
    const css = ler("src/styles.css");
    expect(fonte).toMatch(/app\.classList\.toggle\("animacoes-ocultas",\s*oculto\)/);
    expect(blocoDePausa(css, "#app.animacoes-ocultas")).toMatch(/animation-play-state\s*:\s*paused\s*!important/);
  });
});
