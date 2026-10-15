import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { definirPreferencia } from "../src/audio/dispositivos";
import { aplicarSaidaNoContexto } from "../src/audio/boca";

describe("aplicarSaidaNoContexto", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    definirPreferencia({ saida_id: "", saida_rotulo: "" });
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("retorna false quando saida_id vazio", async () => {
    const ctx = {} as AudioContext;
    const ok = await aplicarSaidaNoContexto(ctx);
    expect(ok).toBe(false);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("chama setSinkId com saida_id quando suportado", async () => {
    definirPreferencia({ saida_id: "spk-1", saida_rotulo: "Caixa USB" });
    const setSinkId = vi.fn().mockResolvedValue(undefined);
    const ctx = { setSinkId } as unknown as AudioContext;
    const ok = await aplicarSaidaNoContexto(ctx);
    expect(ok).toBe(true);
    expect(setSinkId).toHaveBeenCalledWith("spk-1");
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("retorna false silenciosamente quando setSinkId nao existe", async () => {
    definirPreferencia({ saida_id: "spk-x", saida_rotulo: "Fone BT" });
    const ctx = {} as AudioContext; // sem setSinkId
    const ok = await aplicarSaidaNoContexto(ctx);
    expect(ok).toBe(false);
    // O código só avisa no catch do setSinkId; ausência da função é retorno silencioso.
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("retorna false e avisa quando setSinkId rejeita", async () => {
    definirPreferencia({ saida_id: "spk-fail", saida_rotulo: "HDMI" });
    const setSinkId = vi.fn().mockRejectedValue(new Error("denied"));
    const ctx = { setSinkId } as unknown as AudioContext;
    const ok = await aplicarSaidaNoContexto(ctx);
    expect(ok).toBe(false);
    expect(setSinkId).toHaveBeenCalledWith("spk-fail");
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Saída preferida "HDMI" indisponível'),
    );
  });
});