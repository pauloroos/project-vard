import { describe, it, expect } from "vitest";
import { ESPELHO_INICIAL, MAX_TEXTO, formatarHora, reduzir, salaExiste } from "../src/sala/espelho";

describe("espelho da sala", () => {
  it("estado_valido_muda", () => {
    expect(reduzir(ESPELHO_INICIAL, { tipo: "estado", estado: "pensando", detalhe: "" }).estado).toBe("pensando");
  });
  it("estado_invalido_nao_muda", () => {
    expect(reduzir(ESPELHO_INICIAL, { tipo: "estado", estado: "dançando", detalhe: "" })).toBe(ESPELHO_INICIAL);
  });
  it("ouvido_novo_apaga_resposta", () => {
    const com = reduzir(reduzir(ESPELHO_INICIAL, { tipo: "ouvido", texto: "que horas são" }), { tipo: "resposta", texto: "Agora são 13h." });
    expect(com).toMatchObject({ ouvido: "que horas são", resposta: "Agora são 13h." });
    expect(reduzir(com, { tipo: "ouvido", texto: "e amanhã?" })).toMatchObject({ ouvido: "e amanhã?", resposta: "" });
  });
  it("malformado_nao_muda", () => {
    for (const ev of [null, "x", 3, {}, { tipo: "ouvido", texto: 3 }, { tipo: "resposta" }, { tipo: "retrato", espelho: null }, { tipo: "outro" }]) {
      expect(reduzir(ESPELHO_INICIAL, ev)).toBe(ESPELHO_INICIAL);
    }
  });
  it("resposta_longa_cortada", () => {
    const r = reduzir(ESPELHO_INICIAL, { tipo: "resposta", texto: "a".repeat(1000) }).resposta;
    expect(r.length).toBe(MAX_TEXTO);
    expect(r.endsWith("...")).toBe(true);
  });
  it("retrato_substitui", () => {
    const sujo = reduzir(ESPELHO_INICIAL, { tipo: "ouvido", texto: "velho" });
    expect(reduzir(sujo, { tipo: "retrato", espelho: { estado: "falando", detalhe: "", ouvido: "oi", resposta: "Oi." } }))
      .toEqual({ estado: "falando", detalhe: "", ouvido: "oi", resposta: "Oi." });
  });
  it("relogio", () => {
    expect(formatarHora(new Date(2026, 9, 12, 9, 5))).toBe("09:05");
    expect(formatarHora(new Date(2026, 9, 12, 23, 59))).toBe("23:59");
  });
  it("sala_existe_so_com_janela", () => {
    expect(salaExiste(null)).toBe(false);
    expect(salaExiste(undefined)).toBe(false);
    expect(salaExiste({ label: "sala" })).toBe(true);
  });
});
