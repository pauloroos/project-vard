import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn(),
}));
import { cofreExiste } from "../src/config/segredos";
import { AbaPaineisMcps } from "../src/ui/paineis-mcps";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

const mockCofreExiste = vi.mocked(cofreExiste);

describe("paineis-mcps (T7)", () => {
  let dir: string;
  let configDir: string;
  const origConfig = process.env.VARD_CONFIG;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-mcp-"));
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
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    expect(raiz.textContent).toContain("Nenhum MCP cadastrado");
    expect(raiz.querySelector("#btn-adicionar-mcp")).toBeTruthy();
  });

  it("adicionar mcp stdio válido salva e atualiza lista", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-id") as HTMLInputElement).value = "fs";
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "Filesystem";
    // Garante que o tipo está em stdio e dispara change para ativar campos
    const sel = raiz.querySelector("#mcp-tipo") as HTMLSelectElement;
    sel.value = "stdio";
    sel.dispatchEvent(new Event("change"));
    (raiz.querySelector("#mcp-command") as HTMLInputElement).value = "node server.js";
    (raiz.querySelector("#mcp-args") as HTMLInputElement).value = "--verbose --port 3000";
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.mcps).toHaveLength(1);
    expect(salvo.mcps[0].id).toBe("fs");
    expect(salvo.mcps[0].command).toBe("node server.js");
    expect(salvo.mcps[0].args).toEqual(["--verbose", "--port", "3000"]);
    expect(raiz.textContent).toContain("Filesystem");
  });

  it("adicionar mcp http válido salva e atualiza lista", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-id") as HTMLInputElement).value = "api";
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "API Remota";
    const sel = raiz.querySelector("#mcp-tipo") as HTMLSelectElement;
    sel.value = "http";
    sel.dispatchEvent(new Event("change"));
    (raiz.querySelector("#mcp-url") as HTMLInputElement).value = "https://exemplo.com/mcp";
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.mcps).toHaveLength(1);
    expect(salvo.mcps[0].id).toBe("api");
    expect(salvo.mcps[0].url).toBe("https://exemplo.com/mcp");
    expect(salvo.mcps[0].command).toBeUndefined();
  });

  it("editar mcp existente atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m1", nome: "Antigo", habilitado: true, command: "old" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector(".btn-editar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "Novo Nome";
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.mcps[0].nome).toBe("Novo Nome");
  });

  it("remover mcp atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      mcps: [
        { id: "a", nome: "A", habilitado: true, command: "c1" },
        { id: "b", nome: "B", habilitado: true, url: "u1" },
      ],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelectorAll(".btn-remover-mcp")[0] as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.mcps).toHaveLength(1);
    expect(salvo.mcps[0].id).toBe("b");
  });

  it("habilitar/desabilitar mcp persiste", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m", nome: "M", habilitado: true, command: "c" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector(".btn-toggle-mcp") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.mcps[0].habilitado).toBe(false);
  });

  it("formulário recusa ID duplicado", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      mcps: [{ id: "existente", nome: "E", habilitado: true, command: "c" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-id") as HTMLInputElement).value = "existente";
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "N";
    (raiz.querySelector("#mcp-command") as HTMLInputElement).value = "c";
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("Já existe um MCP");
    const salvo = lerCfgSalvo();
    expect(salvo.mcps).toHaveLength(1);
  });

  it("formulário recusa stdio sem command", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-id") as HTMLInputElement).value = "x";
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "X";
    // Garante que o tipo está em stdio (padrão) e dispara change para mostrar campos
    const sel = raiz.querySelector("#mcp-tipo") as HTMLSelectElement;
    sel.value = "stdio";
    sel.dispatchEvent(new Event("change"));
    // command vazio
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("MCP stdio exige o campo Command");
  });

  it("formulário recusa http sem url", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-mcp") as HTMLButtonElement).click();
    (raiz.querySelector("#mcp-id") as HTMLInputElement).value = "x";
    (raiz.querySelector("#mcp-nome") as HTMLInputElement).value = "X";
    const sel = raiz.querySelector("#mcp-tipo") as HTMLSelectElement;
    sel.value = "http";
    sel.dispatchEvent(new Event("change"));
    // url vazia
    (raiz.querySelector("#btn-salvar-mcp") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("MCP HTTP exige o campo URL");
  });

  it("botão testar credencial verifica existência sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    salvarCfg({
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m", nome: "M", habilitado: true, command: "c", credencial_ref: "mcp:m" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisMcps(raiz);
    await aba.montar();
    (raiz.querySelector(".btn-testar-cred-mcp") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockCofreExiste).toHaveBeenCalledWith("mcp", "m");
    expect(raiz.textContent).toContain("Credencial encontrada");
    expect(raiz.textContent).not.toContain("chave-secreta");
  });
});