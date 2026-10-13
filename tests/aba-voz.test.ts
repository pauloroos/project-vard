import { describe, it, expect } from "vitest";
import { opcoesDeVoz } from "../src/ui/aba-voz";

const base: [string, string][] = [["", "A voz atual do serviço"], ["Ana", "Ana"]];

describe("opcoesDeVoz", () => {
  it("atual_vazia_ou_na_lista_nao_muda_nada", () => {
    expect(opcoesDeVoz(base, "")).toEqual(base);
    expect(opcoesDeVoz(base, "Ana")).toEqual(base);
  });
  it("atual_fora_da_lista_e_acrescentada", () => {
    expect(opcoesDeVoz(base, "Zed")).toEqual([...base, ["Zed", "Zed"]]);
  });
  it("rotulo_de_ausente_personalizado", () => {
    expect(opcoesDeVoz([["Kore", "Kore"]], "Xis", (v) => `${v} (fora da lista)`)).toEqual([["Kore", "Kore"], ["Xis", "Xis (fora da lista)"]]);
  });
});
