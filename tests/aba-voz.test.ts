import { describe, it, expect, beforeEach } from "vitest";
import { opcoesDeVoz, problemaDeVoz, vozGeminiMarcada } from "../src/ui/aba-voz";
import { definirPreferencia, obterPreferencia } from "../src/audio/dispositivos";

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

describe("problemaDeVoz", () => {
  const ok = { voz_provedor: "propria" as const, elevenlabs_chave: "", elevenlabs_voz: "", gemini_chave: "" };
  it("provedor_local_nao_tem_problema", () => { expect(problemaDeVoz(ok)).toBeNull(); });
  it("elevenlabs_sem_chave_marca_a_chave", () => {
    expect(problemaDeVoz({ ...ok, voz_provedor: "elevenlabs", elevenlabs_voz: "v" })!.campos).toEqual(["elevenlabs_chave"]);
  });
  it("elevenlabs_sem_voz_marca_o_id", () => {
    expect(problemaDeVoz({ ...ok, voz_provedor: "elevenlabs", elevenlabs_chave: "k" })!.campos).toEqual(["elevenlabs_voz_id"]);
  });
  it("gemini_sem_chave_marca_a_chave", () => {
    expect(problemaDeVoz({ ...ok, voz_provedor: "gemini" })!.campos).toEqual(["gemini_chave"]);
    expect(problemaDeVoz({ ...ok, voz_provedor: "gemini", gemini_chave: "k" })).toBeNull();
  });
});

describe("vozGeminiMarcada", () => {
  it("vazia_vira_kore_e_a_salva_fica", () => {
    expect(vozGeminiMarcada("")).toBe("Kore");
    expect(vozGeminiMarcada("  ")).toBe("Kore");
    expect(vozGeminiMarcada("Puck")).toBe("Puck");
  });
});

describe("dispositivos na aba voz (T9c)", () => {
  beforeEach(() => {
    definirPreferencia({ microfone_id: "", microfone_rotulo: "", saida_id: "", saida_rotulo: "" });
  });

  it("definir_preferencia_atualiza_estado_imediatamente", () => {
    definirPreferencia({ microfone_id: "mic-1", microfone_rotulo: "Mic USB" });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("mic-1");
    expect(p.microfone_rotulo).toBe("Mic USB");
  });

  it("selecao_grava_os_4_campos_na_preferencia", () => {
    definirPreferencia({
      microfone_id: "m-x",
      microfone_rotulo: "Microfone X",
      saida_id: "s-y",
      saida_rotulo: "Caixa Y",
    });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("m-x");
    expect(p.saida_id).toBe("s-y");
    expect(p.microfone_rotulo).toBe("Microfone X");
    expect(p.saida_rotulo).toBe("Caixa Y");
  });

  it("nomes_duplicados_nao_quebram_selecao_por_deviceId", () => {
    definirPreferencia({ microfone_id: "dup-2", microfone_rotulo: "Mic Genérico" });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("dup-2");
  });

  it("preferencia_vazia_significa_padrao", () => {
    definirPreferencia({ microfone_id: "", saida_id: "" });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("");
    expect(p.saida_id).toBe("");
  });
});
