import { describe, it, expect, vi } from "vitest";
import { criarFonteDeVoz } from "../src/conectores/voz/escolher";
import { Voz } from "../src/conectores/voz/cliente";
import { ElevenLabs } from "../src/conectores/nuvem/elevenlabs";
import { Gemini } from "../src/conectores/nuvem/gemini";
import { CONFIG_PADRAO } from "../src/config/config";

const base = { ...CONFIG_PADRAO, elevenlabs_chave: "k", gemini_chave: "g" };

describe("criarFonteDeVoz", () => {
  it("propria_ignora_chaves", () => {
    const f = vi.fn();
    const fonte = criarFonteDeVoz({ ...base, voz_provedor: "propria", voz_propria: "Ana Florence" }, f);
    expect(fonte).toBeInstanceOf(Voz);
    expect(fonte!.nome).toBe("Ana Florence");
    expect(f).not.toHaveBeenCalled();
  });
  it("propria_sem_url_e_null", () => { expect(criarFonteDeVoz({ ...base, voz_provedor: "propria", voz_url: "" })).toBeNull(); });
  it("openjarvis_e_null", () => { expect(criarFonteDeVoz({ ...base, voz_provedor: "openjarvis" })).toBeNull(); });
  it("nuvem_com_chave", () => {
    expect(criarFonteDeVoz({ ...base, voz_provedor: "elevenlabs", elevenlabs_voz: "v" })).toBeInstanceOf(ElevenLabs);
    expect(criarFonteDeVoz({ ...base, voz_provedor: "gemini" })).toBeInstanceOf(Gemini);
  });
  it("nuvem_sem_chave_e_null", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(criarFonteDeVoz({ ...base, voz_provedor: "elevenlabs", elevenlabs_chave: "" })).toBeNull();
    expect(criarFonteDeVoz({ ...base, voz_provedor: "gemini", gemini_chave: "" })).toBeNull();
  });
});
