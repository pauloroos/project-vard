import { describe, it, expect, vi, beforeEach } from "vitest";
import { falaFixa } from "../src/audio/cache";

// Sem IndexedDB no Node: o cache sempre erra e a ordem das fontes é o que se prova aqui.
describe("falaFixa", () => {
  beforeEach(() => { vi.spyOn(console, "warn").mockImplementation(() => {}); });

  it("usa a voz própria quando ela responde", async () => {
    const wavVoz = new ArrayBuffer(60);
    const oj = vi.fn().mockResolvedValue(new ArrayBuffer(50));
    const wav = await falaFixa("Voltei.", [
      { origem: "voz", voz: "Voz Teste", sintetizar: async () => wavVoz },
      { origem: "oj", voz: "pm_alex", sintetizar: oj },
    ]);
    expect(wav).toBe(wavVoz);
    expect(oj).not.toHaveBeenCalled();
  });

  it("voz própria fora: cai na reserva", async () => {
    const wavOj = new ArrayBuffer(50);
    const wav = await falaFixa("Voltei.", [
      { origem: "voz", voz: "Voz Teste", sintetizar: async () => { throw new Error("fora"); } },
      { origem: "oj", voz: "pm_alex", sintetizar: async () => wavOj },
    ]);
    expect(wav).toBe(wavOj);
    expect(console.warn).toHaveBeenCalledWith("voz própria falhou, usei a reserva", expect.any(Error));
  });

  it("todas falham: rejeita com o último erro", async () => {
    await expect(falaFixa("Voltei.", [{ origem: "oj", voz: "pm_alex", sintetizar: async () => { throw new Error("sem fala"); } }]))
      .rejects.toThrow("sem fala");
  });
});
