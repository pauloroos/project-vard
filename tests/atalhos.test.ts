import { describe, it, expect } from "vitest";
import { combinacaoDoEvento, conflitos, avisoAltGr, exibirAtalho, normalizarAtalho, validarAtalhos } from "../src/config/atalhos";
import { CONFIG_PADRAO } from "../src/config/config";

const ev = (code: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("atalhos", () => {
  it("normaliza_variacoes", () => {
    expect(normalizarAtalho("ctrl+alt+.")).toBe("Ctrl+Alt+Period");
    expect(normalizarAtalho("Alt + Ctrl + m")).toBe("Ctrl+Alt+M");
    expect(normalizarAtalho("Ctrl+Alt+KeyM")).toBe("Ctrl+Alt+M");
    expect(normalizarAtalho("Ctrl+Alt+,")).toBe("Ctrl+Alt+Comma");
    expect(normalizarAtalho("Win+Shift+F5")).toBe("Shift+Super+F5");
    expect(normalizarAtalho("Control+Alt+space")).toBe("Ctrl+Alt+Space");
  });
  it("recusa_invalidos", () => {
    for (const t of ["M", "Shift+M", "Ctrl+Alt", "Ctrl+M+N", "Ctrl+Alt+Banana", ""]) expect(normalizarAtalho(t)).toBeNull();
  });
  it("combinacao_do_evento", () => {
    expect(combinacaoDoEvento(ev("KeyM", { ctrlKey: true, altKey: true }))).toBe("Ctrl+Alt+M");
    expect(combinacaoDoEvento(ev("Comma", { ctrlKey: true, altKey: true }))).toBe("Ctrl+Alt+Comma");
    expect(combinacaoDoEvento(ev("ControlLeft", { ctrlKey: true }))).toBeNull();
    expect(combinacaoDoEvento(ev("KeyM"))).toBeNull();
  });
  it("conflito_detectado", () => {
    expect(conflitos(CONFIG_PADRAO.atalhos)).toEqual([]);
    // Usa o novo padrão Alt+Super+V como base; outra tecla com mesma combinação deve conflitar
    const a = { ...CONFIG_PADRAO.atalhos, escuta: "alt+super+v" };
    expect(conflitos(a)).toEqual([["mostrar", "escuta"]]);
    expect(validarAtalhos(a).escuta).toContain("Mostrar/ocultar");
    expect(validarAtalhos({ ...CONFIG_PADRAO.atalhos, config: "M" }).config).toContain("inválida");
  });
  it("padroes_validos", () => {
    for (const v of Object.values(CONFIG_PADRAO.atalhos)) expect(normalizarAtalho(v)).toBe(v);
    expect(Object.keys(validarAtalhos(CONFIG_PADRAO.atalhos))).toEqual([]);
  });
  it("exibe_amigavel", () => {
    expect(exibirAtalho("Ctrl+Alt+Comma")).toBe("Ctrl+Alt+,");
    expect(exibirAtalho("Ctrl+Alt+Space")).toBe("Ctrl+Alt+Espaço");
    expect(exibirAtalho("Super+F")).toBe("Win+F");
  });
});

describe("avisoAltGr", () => {
  it("avisa em Ctrl+Alt+<tecla do AltGr> com a tecla exata", () => {
    expect(avisoAltGr("Ctrl+Alt+Comma")).toBe("Em teclados ABNT2, Ctrl+Alt+, é a mesma tecla que AltGr+, (ç, /, ?, °...). Prefira outra tecla.");
    expect(avisoAltGr("ctrl+alt+q")).toBe("Em teclados ABNT2, Ctrl+Alt+Q é a mesma tecla que AltGr+Q (ç, /, ?, °...). Prefira outra tecla.");
    for (const k of ["W", "E", "R", "C", "2", "3", "4", "5", "6"]) expect(avisoAltGr(`Ctrl+Alt+${k}`)).toContain(`AltGr+${k}`);
  });
  it("não avisa nos padrões nem em outras combinações", () => {
    for (const a of ["Ctrl+Alt+P", "Ctrl+Alt+L", "Ctrl+Alt+V", "Ctrl+Alt+F", "Ctrl+Alt+Space", "Ctrl+Shift+E", "Alt+E", "Ctrl+Alt+Shift+E", "lixo", ""]) expect(avisoAltGr(a)).toBeNull();
  });
});
