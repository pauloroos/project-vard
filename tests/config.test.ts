import { describe, it, expect, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

import { carregarConfig, CONFIG_PADRAO } from "../src/config/config";

describe("carregarConfig", () => {
  beforeEach(() => invoke.mockReset());

  it("sem config salva devolve o padrao", async () => {
    invoke.mockResolvedValue(null);
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });

  it("mescla o padrao com o salvo", async () => {
    invoke.mockResolvedValue({ nome: "jarvis", velocidade: 1.2 });
    const c = await carregarConfig();
    expect(c.nome).toBe("jarvis");
    expect(c.velocidade).toBe(1.2);
    expect(c.idioma).toBe(CONFIG_PADRAO.idioma);
  });

  it("preserva atalhos parciais", async () => {
    invoke.mockResolvedValue({ atalhos: { falar: "Ctrl+Shift+F" } });
    const c = await carregarConfig();
    expect(c.atalhos.falar).toBe("Ctrl+Shift+F");
    expect(c.atalhos.parar).toBe(CONFIG_PADRAO.atalhos.parar);
    expect(c.atalhos.mostrar).toBe(CONFIG_PADRAO.atalhos.mostrar);
  });
});
