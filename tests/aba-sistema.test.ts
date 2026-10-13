import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { acoesDoModo, Confirmacao } from "../src/ui/aba-sistema";

describe("acoesDoModo", () => {
  it("ligado_permite_jogo_e_desligar", () => { expect(acoesDoModo("ligado")).toEqual({ ligar: false, jogo: true, desligar: true }); });
  it("jogo_e_parado_permitem_ligar_e_desligar", () => {
    expect(acoesDoModo("jogo")).toEqual({ ligar: true, jogo: false, desligar: true });
    expect(acoesDoModo("parado")).toEqual({ ligar: true, jogo: false, desligar: true });
  });
  it("transicao_erro_e_desconhecido_permitem_ligar_e_desligar", () => {
    for (const m of ["ligando", "erro", "desconhecido", ""]) expect(acoesDoModo(m)).toEqual({ ligar: true, jogo: false, desligar: true });
  });
  it("sem_ponte_nada", () => { expect(acoesDoModo(null)).toEqual({ ligar: false, jogo: false, desligar: false }); });
});

describe("Confirmacao", () => {
  let expirou: number;
  let c: Confirmacao;
  beforeEach(() => { vi.useFakeTimers(); expirou = 0; c = new Confirmacao(5000, () => { expirou++; }); });
  afterEach(() => vi.useRealTimers());
  it("segundo_clique_no_prazo_confirma", () => {
    expect(c.pedir("jogo")).toBe(false);
    vi.advanceTimersByTime(4999);
    expect(c.pedir("jogo")).toBe(true);
    expect(c.pedir("jogo")).toBe(false); // desarmou: começa de novo
  });
  it("prazo_estourado_volta_ao_inicio", () => {
    c.pedir("parar"); vi.advanceTimersByTime(5000);
    expect(expirou).toBe(1);
    expect(c.pedir("parar")).toBe(false);
  });
  it("verbo_diferente_reinicia", () => {
    c.pedir("jogo");
    expect(c.pedir("parar")).toBe(false);
    expect(c.pedir("parar")).toBe(true);
  });
});
