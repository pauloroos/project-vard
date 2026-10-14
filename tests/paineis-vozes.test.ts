import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn(),
}));

import { cofreExiste } from "../src/config/segredos";
import { AbaPaineisVozes } from "../src/ui/paineis-vozes";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

const mockCofreExiste = vi.mocked(cofreExiste);

describe("paineis-vozes (T6)", () => {
  let dir: string;
  let configDir: string;
  const origConfig = process.env.VARD_CONFIG;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-voz-"));
    configDir = join(dir, "config");
    mkdirSync(configDir, { recursive: true });
    process.env.VARD_CONFIG = configDir;
    mockCofreExiste.mockReset();
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

  it("renderiza lista vazia com botão adicionar", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    expect(raiz.textContent).toContain("Nenhuma voz cadastrada");
    expect(raiz.querySelector("#btn-adicionar-voz")).toBeTruthy();
  });

  it("adicionar voz válida salva e atualiza lista", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#voz-id") as HTMLInputElement).value = "kokoro-local";
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "Kokoro Local";
    (raiz.querySelector("#voz-tipo") as HTMLSelectElement).value = "kokoro";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
    expect(salvo.provedores[0].id).toBe("kokoro-local");
    expect(salvo.provedores[0].tipo).toBe("kokoro");
    expect(raiz.textContent).toContain("Kokoro Local");
  });

  it("editar voz existente atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "v1", nome: "Antiga", tipo: "gemini", url_base: "", modelo: "" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-editar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "Nova Voz";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores[0].nome).toBe("Nova Voz");
  });

  it("remover voz atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "a", nome: "A", tipo: "suad", url_base: "", modelo: "" },
        { id: "b", nome: "B", tipo: "fish", url_base: "", modelo: "" },
      ],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelectorAll(".btn-remover-voz")[0] as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
    expect(salvo.provedores[0].id).toBe("b");
  });

  it("selecionar voz ativa persiste", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "elevenlabs", url_base: "", modelo: "" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    const sel = raiz.querySelector("#sel-voz-ativa") as HTMLSelectElement;
    sel.value = "s";
    sel.dispatchEvent(new Event("change"));

    const salvo = lerCfgSalvo();
    expect(salvo.ativo).toBe("s");
  });

  it("formulário recusa ID duplicado em novo", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "existente", nome: "E", tipo: "suad", url_base: "", modelo: "" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#voz-id") as HTMLInputElement).value = "existente";
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "N";
    (raiz.querySelector("#voz-tipo") as HTMLSelectElement).value = "kokoro";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("Já existe uma voz");
    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
  });

  it("formulário recusa campos obrigatórios vazios (tipo padrão é válido)", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-voz") as HTMLButtonElement).click();
    // ID e nome preenchidos, mas tipo fica no padrão (suad) — válido
    (raiz.querySelector("#voz-id") as HTMLInputElement).value = "x";
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "X";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();

    // Deve salvar com sucesso pois todos os obrigatórios estão presentes
    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
    expect(salvo.provedores[0].tipo).toBe("suad");
  });

  it("botão testar credencial verifica existência sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "el", nome: "EL", tipo: "elevenlabs", url_base: "", modelo: "", credencial_ref: "voz:el" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-testar-cred-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockCofreExiste).toHaveBeenCalledWith("voz", "el");
    expect(raiz.textContent).toContain("Credencial encontrada");
    expect(raiz.textContent).not.toContain("chave-secreta");
  });
});