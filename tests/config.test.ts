import { describe, it, expect, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

import { carregarConfig, CONFIG_PADRAO, urlLocal, avisosDeUrl, gatilhos } from "../src/config/config";

describe("carregarConfig", () => {
  beforeEach(() => invoke.mockReset());

  it("sem config salva devolve o padrao", async () => {
    invoke.mockResolvedValue(null);
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });

  it("mescla o padrao com o salvo", async () => {
    invoke.mockResolvedValue({ nome: "jarvis", velocidade: 1.2, voz_url: "" });
    const c = await carregarConfig();
    expect(c.voz_url).toBe(""); // vazio salvo é escolha (voz própria desligada), não volta ao padrão
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

  it("atalhos novos têm padrão e o salvo antigo (só três) continua valendo", async () => {
    invoke.mockResolvedValue({ atalhos: { falar: "Ctrl+Shift+F", parar: "Ctrl+Alt+Period", mostrar: "Ctrl+Alt+V" } });
    const c = await carregarConfig();
    expect(c.atalhos.falar).toBe("Ctrl+Shift+F");
    expect(c.atalhos.config).toBe("Ctrl+Alt+Comma");
    expect(c.atalhos.escuta).toBe("Ctrl+Alt+E");
  });
});

describe("carregarConfig com arquivo ruim", () => {
  beforeEach(() => { invoke.mockReset(); vi.spyOn(console, "warn").mockImplementation(() => {}); });

  it("invoke rejeitando (JSON inválido) cai para o padrão", async () => {
    invoke.mockRejectedValue("expected value at line 1 column 1");
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });
  it("lixo no lugar do objeto cai para o padrão", async () => {
    invoke.mockResolvedValue("lixo");
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
    invoke.mockResolvedValue([1, 2]);
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });
  it("tipos errados são descartados chave a chave", async () => {
    invoke.mockResolvedValue({ variantes: "vard", velocidade: "rápido", nome: "jarvis", atalhos: { falar: 3 } });
    const c = await carregarConfig();
    expect(c.variantes).toEqual(CONFIG_PADRAO.variantes);
    expect(c.velocidade).toBe(CONFIG_PADRAO.velocidade);
    expect(c.nome).toBe("jarvis");
    expect(c.atalhos).toEqual(CONFIG_PADRAO.atalhos);
  });
});

describe("gatilhos", () => {
  it("com o nome padrão mantém as variantes", () => {
    expect(gatilhos(CONFIG_PADRAO)).toEqual(CONFIG_PADRAO.variantes);
  });
  it("com outro nome usa o nome e só as variantes próprias", () => {
    expect(gatilhos({ nome: "Jarvis", variantes: [...CONFIG_PADRAO.variantes, "jarvi"] })).toEqual(["jarvis", "jarvi"]);
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
    expect(avisosDeUrl({ ...CONFIG_PADRAO, ponte_url: "" })).toEqual([]); // vazio = ponte desligada
  });
  it("serviço de voz: fora da máquina avisa, vazio desliga sem aviso", () => {
    expect(CONFIG_PADRAO.voz_url).toBe("http://127.0.0.1:4710");
    const a = avisosDeUrl({ ...CONFIG_PADRAO, voz_url: "http://192.168.0.9:4710" });
    expect(a).toHaveLength(1);
    expect(a[0]).toContain("Serviço de voz");
    expect(avisosDeUrl({ ...CONFIG_PADRAO, voz_url: "" })).toEqual([]);
  });
});
