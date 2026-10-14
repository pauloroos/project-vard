import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn(),
}));

import { cofreExiste } from "../src/config/segredos";
import { AbaPaineisProvedores } from "../src/ui/paineis-provedores";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

const mockCofreExiste = vi.mocked(cofreExiste);

describe("paineis-provedores (T5)", () => {
  let dir: string;
  let configDir: string;
  const origConfig = process.env.VARD_CONFIG;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-prov-"));
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
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();
    expect(raiz.textContent).toContain("Nenhum provedor cadastrado");
    expect(raiz.querySelector("#btn-adicionar-provedor")).toBeTruthy();
  });

  it("adicionar provedor válido salva e atualiza lista", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    // Abrir formulário de novo
    (raiz.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();

    // Preencher campos
    (raiz.querySelector("#prov-id") as HTMLInputElement).value = "suad";
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "Suad Local";
    (raiz.querySelector("#prov-tipo") as HTMLInputElement).value = "local";
    (raiz.querySelector("#prov-url") as HTMLInputElement).value = "http://127.0.0.1:8000";
    (raiz.querySelector("#prov-modelo") as HTMLInputElement).value = "gemma-3";

    // Salvar
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
    expect(salvo.provedores[0].id).toBe("suad");
    expect(salvo.provedores[0].nome).toBe("Suad Local");
    expect(raiz.textContent).toContain("Suad Local");
  });

  it("editar provedor existente atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "x", nome: "Antigo", tipo: "t", url_base: "u", modelo: "m" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-editar") as HTMLButtonElement).click();
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "Novo Nome";
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores[0].nome).toBe("Novo Nome");
  });

  it("remover provedor atualiza config", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "a", nome: "A", tipo: "t", url_base: "u", modelo: "m" },
        { id: "b", nome: "B", tipo: "t", url_base: "u", modelo: "m" },
      ],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelectorAll(".btn-remover")[0] as HTMLButtonElement).click();

    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
    expect(salvo.provedores[0].id).toBe("b");
  });

  it("selecionar ativo/reserva persiste", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    const selAtivo = raiz.querySelector("#sel-ativo") as HTMLSelectElement;
    selAtivo.value = "s";
    selAtivo.dispatchEvent(new Event("change"));

    const salvo = lerCfgSalvo();
    expect(salvo.ativo).toBe("s");
  });

  it("formulário recusa ID duplicado em novo", async () => {
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "existente", nome: "E", tipo: "t", url_base: "u", modelo: "m" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();
    (raiz.querySelector("#prov-id") as HTMLInputElement).value = "existente";
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "N";
    (raiz.querySelector("#prov-tipo") as HTMLInputElement).value = "t";
    (raiz.querySelector("#prov-url") as HTMLInputElement).value = "u";
    (raiz.querySelector("#prov-modelo") as HTMLInputElement).value = "m";
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("Já existe um provedor");
    // Config não deve ter sido alterada (ainda só 1 provedor)
    const salvo = lerCfgSalvo();
    expect(salvo.provedores).toHaveLength(1);
  });

  it("formulário recusa campos obrigatórios vazios", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();
    // Deixar todos vazios
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    expect(raiz.textContent).toContain("Preencha todos os campos obrigatórios");
  });

  it("botão testar credencial verifica existência sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    salvarCfg({
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m", credencial_ref: "provedor:s" }],
    });
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-testar-cred") as HTMLButtonElement).click();
    // Aguardar promise
    await new Promise((r) => setTimeout(r, 50));

    expect(mockCofreExiste).toHaveBeenCalledWith("provedor", "s");
    expect(raiz.textContent).toContain("Credencial encontrada");
    // Valor real nunca aparece
    expect(raiz.textContent).not.toContain("chave-secreta");
  });
});