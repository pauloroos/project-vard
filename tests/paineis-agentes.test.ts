import { describe, it, expect, beforeEach, vi } from "vitest";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

// Estado em memória simulando o arquivo paineis.json via invoke
let cfgEmMemoria: PaineisConfig | null = null;

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation((cmd: string, args?: Record<string, unknown>) => {
    if (cmd === "ler_paineis") return Promise.resolve(cfgEmMemoria);
    if (cmd === "gravar_paineis") {
      cfgEmMemoria = (args?.valor as PaineisConfig) ?? null;
      return Promise.resolve(undefined);
    }
    if (cmd === "falhas_de_atalho") return Promise.resolve([]);
    return Promise.resolve(null);
  }),
}));

import { AbaPaineisAgentes } from "../src/ui/paineis-agentes";

describe("paineis-agentes (T11)", () => {
  beforeEach(() => {
    cfgEmMemoria = null;
  });

  function criarRaiz(): HTMLElement {
    const el = document.createElement("div");
    document.body.appendChild(el);
    return el;
  }

  it("renderiza todos os agentes", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();
    expect(raiz.querySelector('fieldset[data-agente="claude"]')).toBeTruthy();
    expect(raiz.querySelector('fieldset[data-agente="codex"]')).toBeTruthy();
    expect(raiz.querySelector('fieldset[data-agente="opencode"]')).toBeTruthy();
    expect(raiz.querySelector('fieldset[data-agente="agy"]')).toBeTruthy();
  });

  it("salvar modelo padrão válido persiste", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        claude: { padrao: "", modelos: ["sonnet", "opus"] },
      },
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="claude"]')!;
    (fs.querySelector(".inp-padrao") as HTMLInputElement).value = "sonnet";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();
    // Aguardar microtask do invoke
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.agentes.claude.padrao).toBe("sonnet");
  });

  it("salvar lista modelos persiste", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="codex"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "gpt-4o, o1, o3";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.agentes.codex.modelos).toEqual(["gpt-4o", "o1", "o3"]);
  });

  it("modelo padrão fora da lista gera erro", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        claude: { padrao: "", modelos: ["sonnet"] },
      },
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="claude"]')!;
    (fs.querySelector(".inp-padrao") as HTMLInputElement).value = "haiku";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(fs.querySelector(".msg-agente")?.textContent).toContain("não está na lista");
    // Config não deve ter sido alterada
    expect(cfgEmMemoria!.agentes.claude.padrao).toBe("");
  });

  it("remover modelo da lista atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        opencode: { padrao: "mimo", modelos: ["mimo", "space-bunny", "cat-jam"] },
      },
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="opencode"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "mimo, cat-jam";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.agentes.opencode.modelos).toEqual(["mimo", "cat-jam"]);
  });

  it("adicionar modelo na lista atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        agy: { padrao: "", modelos: ["gemini-2.5"] },
      },
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="agy"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "gemini-2.5, gemini-3";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.agentes.agy.modelos).toEqual(["gemini-2.5", "gemini-3"]);
  });
});