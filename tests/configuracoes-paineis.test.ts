import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn().mockResolvedValue(false),
  cofreLer: vi.fn().mockResolvedValue(null),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation((cmd: string) => {
    if (cmd === "falhas_de_atalho") return Promise.resolve([]);
    return Promise.resolve(null);
  }),
}));

import { Configuracoes, type Aba } from "../src/ui/configuracoes";
import type { Config } from "../src/config/config";
import { CONFIG_PADRAO } from "../src/config/config";
import { PAINEIS_PADRAO } from "../src/config/paineis";

describe("configuracoes-paineis (T8)", () => {
  let dir: string;
  let configDir: string;
  const origConfig = process.env.VARD_CONFIG;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-cfg-painel-"));
    configDir = join(dir, "config");
    mkdirSync(configDir, { recursive: true });
    process.env.VARD_CONFIG = configDir;
    // Garante que paineis.json existe para evitar erro de leitura
    writeFileSync(join(configDir, "paineis.json"), JSON.stringify(PAINEIS_PADRAO), "utf-8");
  });

  afterEach(() => {
    if (origConfig === undefined) delete process.env.VARD_CONFIG;
    else process.env.VARD_CONFIG = origConfig;
    rmSync(dir, { recursive: true, force: true });
  });

  function criarRaiz(): HTMLElement {
    const el = document.createElement("div");
    el.id = "painel";
    document.body.appendChild(el);
    return el;
  }

  function criarDeps() {
    return {
      criarOj: () => ({ saude: async () => true, fala: async () => true, modelos: async () => [] }) as any,
      statusPonte: async () => null,
      modoPonte: async () => false,
      ponte: () => ({}) as any,
      atualizacao: {
        url: "",
        buscar: async () => "",
        instalar: async () => {},
        versao: async () => "0.6.0",
      },
    };
  }

  it("abas paineis aparecem na navegação", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    const botoes = Array.from(raiz.querySelectorAll<HTMLButtonElement>("nav button")).map((b) => b.dataset.aba);
    expect(botoes).toContain("paineis-provedores");
    expect(botoes).toContain("paineis-vozes");
    expect(botoes).toContain("paineis-mcps");
  });

  it("container cfg-paineis-provedores existe", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-paineis-provedores")).toBeTruthy();
  });

  it("container cfg-paineis-vozes existe", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-paineis-vozes")).toBeTruthy();
  });

  it("container cfg-paineis-mcps existe", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-paineis-mcps")).toBeTruthy();
  });

  it("abrir aba paineis-provedores renderiza conteúdo", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("paineis-provedores" as Aba);
    // Aguarda montagem assíncrona
    await new Promise((r) => setTimeout(r, 50));
    const container = raiz.querySelector("#cfg-paineis-provedores") as HTMLElement;
    expect(container.innerHTML.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Provedores");
  });

  it("abrir aba paineis-vozes renderiza conteúdo", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("paineis-vozes" as Aba);
    await new Promise((r) => setTimeout(r, 50));
    const container = raiz.querySelector("#cfg-paineis-vozes") as HTMLElement;
    expect(container.innerHTML.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Vozes");
  });

  it("abrir aba paineis-mcps renderiza conteúdo", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("paineis-mcps" as Aba);
    await new Promise((r) => setTimeout(r, 50));
    const container = raiz.querySelector("#cfg-paineis-mcps") as HTMLElement;
    expect(container.innerHTML.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("MCP");
  });

  it("aba paineis-agentes aparece na navegação", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    const botoes = Array.from(raiz.querySelectorAll<HTMLButtonElement>("nav button")).map((b) => b.dataset.aba);
    expect(botoes).toContain("paineis-agentes");
  });

  it("container cfg-paineis-agentes existe", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-paineis-agentes")).toBeTruthy();
  });

  it("abrir aba paineis-agentes renderiza conteúdo", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("paineis-agentes" as Aba);
    await new Promise((r) => setTimeout(r, 50));
    const container = raiz.querySelector("#cfg-paineis-agentes") as HTMLElement;
    expect(container.innerHTML.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Claude");
  });
});