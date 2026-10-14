import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AbaPaineisAgentes } from "../src/ui/paineis-agentes";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

describe("paineis-agentes (T11)", () => {
  let dir: string;
  let configDir: string;
  const origConfig = process.env.VARD_CONFIG;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-ag-"));
    configDir = join(dir, "config");
    mkdirSync(configDir, { recursive: true });
    process.env.VARD_CONFIG = configDir;
  });

  afterEach(() => {
    if (origConfig === undefined) delete process.env.VARD_CONFIG;
    else process.env.VARD_CONFIG = origConfig;
    rmSync(dir, { recursive: true, force: true });
  });

  function criarRaiz(): HTMLElement {
    const el = document.createElement("div");
    document.body.appendChild(el);
    return el;
  }

  function salvarCfg(cfg: PaineisConfig) {
    writeFileSync(join(configDir, "paineis.json"), JSON.stringify(cfg), "utf-8");
  }

  function lerCfgSalvo(): PaineisConfig {
    return JSON.parse(readFileSync(join(configDir, "paineis.json"), "utf-8"));
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
    salvarCfg({
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        claude: { padrao: "", modelos: ["sonnet", "opus"] },
      },
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="claude"]')!;
    (fs.querySelector(".inp-padrao") as HTMLInputElement).value = "sonnet";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.agentes.claude.padrao).toBe("sonnet");
  });

  it("salvar lista modelos persiste", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="codex"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "gpt-4o, o1, o3";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.agentes.codex.modelos).toEqual(["gpt-4o", "o1", "o3"]);
  });

  it("modelo padrão fora da lista gera erro", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        claude: { padrao: "", modelos: ["sonnet"] },
      },
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="claude"]')!;
    (fs.querySelector(".inp-padrao") as HTMLInputElement).value = "haiku";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();

    expect(fs.querySelector(".msg-agente")?.textContent).toContain("não está na lista");
    // Config não deve ter sido alterada
    const salvo = lerCfgSalvo();
    expect(salvo.agentes.claude.padrao).toBe("");
  });

  it("remover modelo da lista atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        opencode: { padrao: "mimo", modelos: ["mimo", "space-bunny", "cat-jam"] },
      },
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="opencode"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "mimo, cat-jam";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.agentes.opencode.modelos).toEqual(["mimo", "cat-jam"]);
  });

  it("adicionar modelo na lista atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      agentes: {
        ...PAINEIS_PADRAO.agentes,
        agy: { padrao: "", modelos: ["gemini-2.5"] },
      },
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisAgentes(raiz);
    await aba.montar();

    const fs = raiz.querySelector('fieldset[data-agente="agy"]')!;
    (fs.querySelector(".inp-modelos") as HTMLInputElement).value = "gemini-2.5, gemini-3";
    (fs.querySelector(".btn-salvar-agente") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.agentes.agy.modelos).toEqual(["gemini-2.5", "gemini-3"]);
  });
});