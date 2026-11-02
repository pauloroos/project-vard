import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function sRgbLuminancia(hex: string): number {
  const limpo = hex.trim().replace("#", "");
  const num = parseInt(limpo, 16);
  const r = ((num >> 16) & 255) / 255;
  const g = ((num >> 8) & 255) / 255;
  const b = (num & 255) / 255;
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function razaoContraste(hex1: string, hex2: string): number {
  const l1 = sRgbLuminancia(hex1);
  const l2 = sRgbLuminancia(hex2);
  const claro = Math.max(l1, l2);
  const escuro = Math.min(l1, l2);
  return (claro + 0.05) / (escuro + 0.05);
}

describe("Tokens de design e acessibilidade", () => {
  const caminhoTokens = resolve(__dirname, "../src/tokens.css");
  const css = readFileSync(caminhoTokens, "utf-8");

  it("não contém fontes remotas nem URLs externas", () => {
    expect(css).not.toMatch(/@font-face/i);
    expect(css).not.toMatch(/@import\s+url\s*\(\s*["']?https?:/i);
    expect(css).not.toMatch(/https?:\/\//i);
  });

  const tokensObrigatorios = [
    // Cores
    "--vard-fundo",
    "--vard-fundo-elevado",
    "--vard-superficie",
    "--vard-superficie-forte",
    "--vard-borda",
    "--vard-borda-forte",
    "--vard-texto",
    "--vard-texto-fraco",
    "--vard-ciano",
    "--vard-ciano-forte",
    "--vard-ambar",
    "--vard-violeta",
    "--vard-erro",
    // Vidro e profundidade
    "--vard-vidro",
    "--vard-vidro-borda",
    "--vard-brilho",
    "--vard-sombra-1",
    "--vard-sombra-2",
    "--vard-sombra-3",
    // Espaçamento
    "--vard-esp-1",
    "--vard-esp-2",
    "--vard-esp-3",
    "--vard-esp-4",
    "--vard-esp-5",
    "--vard-esp-6",
    // Raios
    "--vard-raio-1",
    "--vard-raio-2",
    "--vard-raio-3",
    "--vard-raio-4",
    "--vard-raio-pilula",
    // Tipografia
    "--vard-fonte-mono",
    "--vard-fonte-sans",
    "--vard-texto-1",
    "--vard-texto-2",
    "--vard-texto-3",
    "--vard-texto-4",
    "--vard-texto-5",
    "--vard-texto-6",
    // Movimento
    "--vard-duracao-1",
    "--vard-duracao-2",
    "--vard-foco",
  ];

  it.each(tokensObrigatorios)("define o token %s", (token) => {
    expect(css).toContain(token);
  });

  it("mantém aliases de compatibilidade com versões anteriores", () => {
    expect(css).toMatch(/--ciano\s*:\s*var\(--vard-ciano\)/);
    expect(css).toMatch(/--brilho\s*:\s*var\(--vard-brilho\)/);
    expect(css).toMatch(/--fundo\s*:\s*var\(--vard-fundo\)/);
    expect(css).toMatch(/--fundo-menu\s*:\s*var\(--vard-fundo-elevado\)/);
    expect(css).toMatch(/--borda\s*:\s*var\(--vard-borda\)/);
    expect(css).toMatch(/--mono\s*:\s*var\(--vard-fonte-mono\)/);
    expect(css).toMatch(/--sans\s*:\s*var\(--vard-fonte-sans\)/);
  });

  it("garante foco visível com :focus-visible e sem outline: none isolado", () => {
    expect(css).toMatch(/:focus-visible/);
    // Não pode ter outline: none sem substituto
    const matchesOutlineNone = css.match(/outline\s*:\s*none\s*;/g);
    if (matchesOutlineNone) {
      // Se houver, deve estar acompanhado de box-shadow ou outline no mesmo seletor
      expect(css).toMatch(/outline:\s*none[^;]*;\s*(box-shadow|outline)/s);
    }
  });

  it("garante regra para prefers-reduced-motion: reduce", () => {
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion\s*:\s*reduce\)/);
  });

  describe("Contraste WCAG AA (mínimo 4.5:1 para texto normal e 3.0:1 para elementos grandes/gráficos)", () => {
    // Extrai valores hexadecimais dos tokens
    const extrairHex = (nome: string): string => {
      const regex = new RegExp(`${nome}\\s*:\\s*(#[0-9a-fA-F]{6})`, "i");
      const match = css.match(regex);
      if (!match) throw new Error(`Token ${nome} não encontrado em formato hex.`);
      return match[1];
    };

    it("pares de texto atendem WCAG AA contra --vard-fundo", () => {
      const fundo = extrairHex("--vard-fundo");
      const texto = extrairHex("--vard-texto");
      const textoFraco = extrairHex("--vard-texto-fraco");
      const ciano = extrairHex("--vard-ciano");
      const ambar = extrairHex("--vard-ambar");
      const violeta = extrairHex("--vard-violeta");
      const erro = extrairHex("--vard-erro");

      expect(razaoContraste(texto, fundo)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(textoFraco, fundo)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(ciano, fundo)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(ambar, fundo)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(violeta, fundo)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(erro, fundo)).toBeGreaterThanOrEqual(4.5);
    });

    it("pares de texto atendem WCAG AA contra --vard-fundo-elevado", () => {
      const fundoElevado = extrairHex("--vard-fundo-elevado");
      const texto = extrairHex("--vard-texto");
      const textoFraco = extrairHex("--vard-texto-fraco");
      const ciano = extrairHex("--vard-ciano");

      expect(razaoContraste(texto, fundoElevado)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(textoFraco, fundoElevado)).toBeGreaterThanOrEqual(4.5);
      expect(razaoContraste(ciano, fundoElevado)).toBeGreaterThanOrEqual(4.5);
    });
  });
});
