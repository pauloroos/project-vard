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
  it("openjarvis_com_voz_kokoro_usa_o_kokoro_do_servico_de_voz", () => {
    // Config antiga (Kokoro pelo OpenJarvis): a mesma voz sai do serviço de voz do Vard; sem o Kokoro lá, o
    // serviço recusa e a frase segue a reserva de sempre.
    const fonte = criarFonteDeVoz({ ...base, voz_provedor: "openjarvis", voz: "pm_alex" });
    expect(fonte).toBeInstanceOf(Voz);
    expect(fonte!.nome).toBe("pm_alex");
  });
  it("openjarvis_sem_servico_de_voz_ou_com_voz_desconhecida_e_null", () => {
    expect(criarFonteDeVoz({ ...base, voz_provedor: "openjarvis", voz: "pm_alex", voz_url: "" })).toBeNull();
    expect(criarFonteDeVoz({ ...base, voz_provedor: "openjarvis", voz: "voz-ficticia" })).toBeNull();
  });
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
