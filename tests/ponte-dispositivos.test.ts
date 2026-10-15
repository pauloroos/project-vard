import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Ponte } from "../src/conectores/ponte/cliente";

describe("Ponte dispositivos reuniao", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let ponte: Ponte;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    ponte = new Ponte("http://127.0.0.1:4700");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("lerDispositivosReuniao", () => {
    it("retorna preferencia quando sucesso", async () => {
      const pref = { microfone_id: "m1", microfone_rotulo: "Mic", saida_id: "s1", saida_rotulo: "Spk" };
      fetchMock.mockResolvedValue({ ok: true, json: async () => pref });
      const r = await ponte.lerDispositivosReuniao();
      expect(r).toEqual(pref);
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:4700/reuniao/dispositivos",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });

    it("retorna null quando resposta nao ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });
      expect(await ponte.lerDispositivosReuniao()).toBeNull();
    });

    it("retorna null quando json invalido", async () => {
      fetchMock.mockResolvedValue({ ok: true, json: async () => { throw new Error("bad"); } });
      expect(await ponte.lerDispositivosReuniao()).toBeNull();
    });

    it("retorna null quando fetch falha (timeout/rede)", async () => {
      fetchMock.mockRejectedValue(new Error("network"));
      expect(await ponte.lerDispositivosReuniao()).toBeNull();
    });

    it("retorna null quando base vazia", async () => {
      const pSemBase = new Ponte("");
      expect(await pSemBase.lerDispositivosReuniao()).toBeNull();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  describe("gravarDispositivosReuniao", () => {
    const pref = { microfone_id: "m1", microfone_rotulo: "Mic", saida_id: "s1", saida_rotulo: "Spk" };

    it("retorna true quando sucesso", async () => {
      fetchMock.mockResolvedValue({ ok: true });
      expect(await ponte.gravarDispositivosReuniao(pref)).toBe(true);
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:4700/reuniao/dispositivos",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pref),
        }),
      );
    });

    it("retorna false quando resposta nao ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });
      expect(await ponte.gravarDispositivosReuniao(pref)).toBe(false);
    });

    it("retorna false quando fetch falha", async () => {
      fetchMock.mockRejectedValue(new Error("timeout"));
      expect(await ponte.gravarDispositivosReuniao(pref)).toBe(false);
    });

    it("retorna false quando base vazia", async () => {
      const pSemBase = new Ponte("");
      expect(await pSemBase.gravarDispositivosReuniao(pref)).toBe(false);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});