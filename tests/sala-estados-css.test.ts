import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const lerCss = (arquivo: string) => readFileSync(resolve(__dirname, "../src", arquivo), "utf8");

function contrasteSala(css: string, tokens: string, estado: string): number[] {
  document.body.innerHTML = '<div id="relogio"></div><div id="estado"></div><div id="ouvido"></div><div id="resposta"></div>';
  document.body.dataset.estado = estado;
  const estilo = document.createElement("style");
  estilo.textContent = `${tokens}\n${css.replace(/@import[^;]+;/, "")}`;
  document.head.append(estilo);
  try {
    const regras = Array.from(estilo.sheet!.cssRules).filter((r): r is CSSStyleRule => r instanceof CSSStyleRule);
    const raiz = regras.find((r) => r.selectorText === ":root")!;
    const fundo = [6, 27, 34]; // amostra fixa, não uma renderização dos gradientes
    const luminancia = (rgb: number[]) => rgb.reduce((soma, valor, i) => {
      const c = valor / 255;
      return soma + [0.2126, 0.7152, 0.0722][i] * (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    }, 0);
    return ["relogio", "estado", "ouvido", "resposta"].map((id) => {
      const elemento = document.getElementById(id)!;
      const candidatas = regras.filter((r) => !r.selectorText.includes("::") && elemento.matches(r.selectorText));
      const valor = (propriedade: string) => {
        const regrasComValor = candidatas.filter((r) => r.style.getPropertyValue(propriedade));
        return regrasComValor[regrasComValor.length - 1]?.style.getPropertyValue(propriedade);
      };
      let cor = valor("color");
      expect(cor, `${estado}/${id}: cor ausente`).toBeTruthy();
      const token = cor.match(/^var\((--[\w-]+)\)$/);
      if (token) cor = raiz.style.getPropertyValue(token[1]).trim();
      const hexadecimal = cor.match(/^#([\da-f]{6})$/i);
      const rgb = cor.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);
      if (!hexadecimal && !rgb) throw new Error(`Cor não suportada em ${estado}/${id}: ${cor}`);
      const canais = hexadecimal ? [0, 2, 4].map((i) => parseInt(hexadecimal[1].slice(i, i + 2), 16)) : rgb!.slice(1).map(Number);
      const opacidade = Number(valor("opacity") ?? "1");
      expect(opacidade).toBeGreaterThanOrEqual(0);
      expect(opacidade).toBeLessThanOrEqual(1);
      const composta = canais.map((v, i) => v * opacidade + fundo[i] * (1 - opacidade));
      return (luminancia(composta) + 0.05) / (luminancia(fundo) + 0.05);
    });
  } finally {
    estilo.remove();
  }
}

describe("regras visuais de estado e foco", () => {
  it("mantém contraste dos estados sobre uma amostra escura da sala", () => {
    for (const estado of ["jogo", "pensando", "transcrevendo"]) {
      for (const contraste of contrasteSala(lerCss("sala.css"), lerCss("tokens.css"), estado)) {
        expect(contraste, estado).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
  it("detecta cor de estado ou token escuro demais", () => {
    const sala = lerCss("sala.css");
    const tokens = lerCss("tokens.css");
    expect(contrasteSala(sala.replace("#b0b4ba", "#101010"), tokens, "jogo")[0]).toBeLessThan(4.5);
    expect(contrasteSala(sala.replace("opacity: 1;", "opacity: 0.1;"), tokens, "jogo")[0]).toBeLessThan(4.5);
    expect(contrasteSala(sala, tokens.replace("#ffb020", "#101010"), "pensando")[0]).toBeLessThan(4.5);
    expect(contrasteSala(sala, tokens.replace("#b59cff", "#101010"), "transcrevendo")[0]).toBeLessThan(4.5);
  });
  it.each([
    ["jogo", "rgb(176, 180, 186)"],
    ["pensando", "var(--vard-ambar)"],
    ["transcrevendo", "var(--vard-violeta)"],
  ])("aplica a cor de %s aos textos da sala", (estado, cor) => {
    document.body.innerHTML = '<div id="relogio"></div><div id="estado"></div><div id="ouvido"></div><div id="resposta"></div>';
    document.body.dataset.estado = estado;
    const estilo = document.createElement("style");
    estilo.textContent = readFileSync(resolve(__dirname, "../src/sala.css"), "utf8").replace(/@import[^;]+;/, "");
    document.head.append(estilo);
    const regras = Array.from(estilo.sheet!.cssRules).filter((r): r is CSSStyleRule => r instanceof CSSStyleRule);
    for (const id of ["relogio", "estado", "ouvido", "resposta"]) {
      const elemento = document.getElementById(id)!;
      const candidatas = regras.filter((r) => r.style.color && !r.selectorText.includes("::") && elemento.matches(r.selectorText));
      expect(candidatas[candidatas.length - 1]?.style.color, id).toBe(cor);
    }
    estilo.remove();
  });

  it("revela a barra compacta quando um botão recebe foco", () => {
    document.body.innerHTML = '<div id="app" class="compacto"><div id="botoes"><button>Configurações</button></div></div>';
    const estilo = document.createElement("style");
    estilo.textContent = readFileSync(resolve(__dirname, "../src/styles.css"), "utf8").replace(/@import[^;]+;/, "");
    document.head.append(estilo);
    const botao = document.querySelector("button")!;
    const barra = document.getElementById("botoes")!;
    expect(getComputedStyle(barra).opacity).toBe("0");
    botao.focus();
    expect(getComputedStyle(barra).opacity).toBe("1");
    expect(getComputedStyle(barra).pointerEvents).toBe("auto");
    estilo.remove();
  });
});
