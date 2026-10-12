import { describe, it, expect, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

import { carregarConfig, CONFIG_PADRAO, urlLocal, avisosDeUrl } from "../src/config/config";

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

describe("urlLocal", () => {
  it("aceita 127.0.0.1 e localhost", () => {
    expect(urlLocal("http://127.0.0.1:8000")).toBe(true);
    expect(urlLocal("http://localhost:5173/")).toBe(true);
  });
  it("recusa outros hosts, esquemas e lixo", () => {
    expect(urlLocal("http://10.0.0.5:8000")).toBe(false);
    expect(urlLocal("http://127.0.0.1.evil.com")).toBe(false);
    expect(urlLocal("ftp://127.0.0.1")).toBe(false);
    expect(urlLocal("isto nao e url")).toBe(false);
    expect(urlLocal("")).toBe(false);
  });
  it("avisosDeUrl lista só os campos fora da máquina", () => {
    expect(avisosDeUrl(CONFIG_PADRAO)).toEqual([]);
    const a = avisosDeUrl({ ...CONFIG_PADRAO, ponte_url: "http://10.0.0.5:4700" });
    expect(a).toHaveLength(1);
    expect(a[0]).toContain("Ponte");
  });
});
