import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn().mockResolvedValue(false),
  cofreLer: vi.fn().mockResolvedValue(null),
}));

// A detecção de CLIs vem da ponte; aqui nenhuma detectada (nunca rede nos testes).
vi.mock("../src/config/clis", () => ({
  detectarClis: vi.fn().mockResolvedValue([]),
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
import { invoke } from "@tauri-apps/api/core";

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

  it("salvar sem escolher cor preserva a paleta padrão vazia", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO, cor_elementos: "" }, raiz, criarDeps());
    await painel.montar();
    expect(painel.lerFormulario().cor_elementos).toBe("");
  });

  it("mudar o slider e clicar em Salvar grava a nova opacidade", async () => {
    const raiz = criarRaiz();
    const aoSalvar = vi.fn();
    const painel = new Configuracoes({ ...CONFIG_PADRAO, opacidade_elementos: 0.8 }, raiz, { ...criarDeps(), aoSalvar });
    await painel.montar();
    vi.mocked(invoke).mockClear();
    const slider = raiz.querySelector<HTMLInputElement>("#cfg-opacidade-elementos")!;
    slider.value = "0.3";
    slider.dispatchEvent(new Event("input"));
    expect(raiz.querySelector("#cfg-opacidade-valor")?.textContent).toBe("30%");
    raiz.querySelector<HTMLButtonElement>("#cfg-salvar")!.click();
    await vi.waitFor(() => expect(aoSalvar).toHaveBeenCalledWith(expect.objectContaining({ opacidade_elementos: 0.3 })));
    expect(invoke).toHaveBeenCalledWith("gravar_config", { config: expect.objectContaining({ opacidade_elementos: 0.3 }) });
  });

  it("abrir Voz consulta o serviço e liga o card XTTS ao núcleo configurado", async () => {
    const buscar = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      return new Response(JSON.stringify(u.endsWith("/saude") ? { xtts: false, edge: true }
        : u.endsWith("/pacotes") ? { pacotes: [{ id: "xtts-v2", nome: "XTTS", versao: "1", tipo: "motor", descricao: "Motor", bytes_download: 1, licenca_url: "https://example.com/licenca", licenca_nome: "Licença fictícia" }] }
        : { vozes: [] }));
    });
    const confirmar = vi.spyOn(window, "confirm").mockReturnValue(false);
    try {
      const raiz = criarRaiz();
      const painel = new Configuracoes({ ...CONFIG_PADRAO, ponte_url: "http://127.0.0.1:4876", voz_provedor: "openjarvis" }, raiz, criarDeps());
      await painel.montar();
      painel.abrirAba("voz");
      await vi.waitFor(() => expect(buscar).toHaveBeenCalledWith(expect.stringContaining("/saude"), expect.anything()));
      await vi.waitFor(() => expect(raiz.querySelector('[data-motor="xtts"]')?.textContent).toContain("Instalar"));
      raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!.click();
      await vi.waitFor(() => expect(confirmar).toHaveBeenCalledOnce());
      expect(buscar).toHaveBeenCalledWith("http://127.0.0.1:4876/pacotes");
      expect(buscar.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    } finally { buscar.mockRestore(); confirmar.mockRestore(); }
  });

  it("aparência identifica a cor personalizada e acompanha bolinhas e prévia", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO, cor_elementos: "#a855f7" }, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector('label[for="cfg-cor-elementos"]')?.textContent).toBe("Personalizada");
    const input = raiz.querySelector<HTMLInputElement>("#cfg-cor-elementos")!;
    expect(raiz.querySelector<HTMLElement>(".aparencia-cor.ativa")?.dataset.cor).toBe("#a855f7");
    raiz.querySelector<HTMLButtonElement>('[data-cor="#22c55e"]')!.click();
    expect(raiz.querySelectorAll(".aparencia-cor.ativa")).toHaveLength(1);
    expect(raiz.querySelector<HTMLElement>(".aparencia-cor.ativa")?.dataset.cor).toBe("#22c55e");
    expect(raiz.querySelector('label[for="cfg-cor-elementos"]')?.textContent).toBe("Personalizada");
    expect(raiz.querySelector(".aparencia-personalizada.ativa")).toBeNull();
    expect(input.value).toBe("#22c55e");
    expect(raiz.querySelector<HTMLElement>("#cfg-aparencia-preview")!.style.color).toBe("rgb(34, 197, 94)");
    input.value = "#123456";
    input.dispatchEvent(new Event("input"));
    expect(raiz.querySelector(".aparencia-cor.ativa")).toBeNull();
    expect(raiz.querySelector<HTMLElement>("#cfg-aparencia-preview")!.style.color).toBe("rgb(18, 52, 86)");
    raiz.querySelector<HTMLInputElement>("#cfg-opacidade-elementos")!.value = "0.6";
    expect(painel.lerFormulario()).toMatchObject({ cor_elementos: "#123456", opacidade_elementos: 0.6 });
  });

  it("destaca o seletor livre só quando a cor não coincide com uma bolinha", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO, cor_elementos: "#123456" }, raiz, criarDeps());
    await painel.montar();
    const personalizada = raiz.querySelector<HTMLElement>(".aparencia-personalizada")!;
    const input = raiz.querySelector<HTMLInputElement>("#cfg-cor-elementos")!;
    expect(personalizada.classList.contains("ativa")).toBe(true);
    expect(raiz.querySelector(".aparencia-cor.ativa")).toBeNull();
    input.value = "#a855f7";
    input.dispatchEvent(new Event("input"));
    expect(personalizada.classList.contains("ativa")).toBe(false);
    expect(raiz.querySelector<HTMLElement>(".aparencia-cor.ativa")?.dataset.cor).toBe("#a855f7");
    expect(personalizada.querySelector("label")?.textContent).toBe("Personalizada");
    input.value = "#654321";
    input.dispatchEvent(new Event("input"));
    expect(personalizada.classList.contains("ativa")).toBe(true);
    raiz.querySelector<HTMLButtonElement>('[data-cor="#22c55e"]')!.click();
    expect(personalizada.classList.contains("ativa")).toBe(false);
    expect(raiz.querySelector<HTMLElement>(".aparencia-cor.ativa")?.dataset.cor).toBe("#22c55e");
  });

  it("abas do menu U7 aparecem na navegação (sem provedores/agentes separados)", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    const botoes = Array.from(raiz.querySelectorAll<HTMLButtonElement>("nav button")).map((b) => b.dataset.aba);
    // "Quem responde" absorveu provedores e agentes
    expect(botoes).toContain("modelos");
    expect(botoes).toContain("paineis-mcps");
    // Abas removidas não devem mais existir
    expect(botoes).not.toContain("paineis-provedores");
    expect(botoes).not.toContain("paineis-agentes");
    expect(botoes).not.toContain("paineis-vozes");
  });

  it("container cfg-paineis-mcps existe", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-paineis-mcps")).toBeTruthy();
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

  it("container cfg-modelos existe (seção Quem responde)", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    expect(raiz.querySelector("#cfg-modelos")).toBeTruthy();
  });

  it("abrir aba modelos renderiza conteúdo da seção Quem responde", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("modelos" as Aba);
    await new Promise((r) => setTimeout(r, 100));
    const container = raiz.querySelector("#cfg-modelos") as HTMLElement;
    expect(container.innerHTML.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("OpenJarvis");
  });
});
