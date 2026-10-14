import { describe, it, expect, vi, beforeEach } from "vitest";
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

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn(),
}));

import { cofreExiste } from "../src/config/segredos";
import { AbaPaineisProvedores } from "../src/ui/paineis-provedores";

const mockCofreExiste = vi.mocked(cofreExiste);

describe("paineis-provedores (T5)", () => {
  beforeEach(() => {
    cfgEmMemoria = null;
    mockCofreExiste.mockReset();
  });

  function criarRaiz(): HTMLElement {
    const el = document.createElement("div");
    document.body.appendChild(el);
    return el;
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

    (raiz.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();
    (raiz.querySelector("#prov-id") as HTMLInputElement).value = "suad";
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "Suad Local";
    (raiz.querySelector("#prov-tipo") as HTMLInputElement).value = "local";
    (raiz.querySelector("#prov-url") as HTMLInputElement).value = "http://127.0.0.1:8000";
    (raiz.querySelector("#prov-modelo") as HTMLInputElement).value = "gemma-3";
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0].id).toBe("suad");
    expect(cfgEmMemoria!.provedores[0].nome).toBe("Suad Local");
    expect(raiz.textContent).toContain("Suad Local");
  });

  it("editar provedor existente atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "x", nome: "Antigo", tipo: "t", url_base: "u", modelo: "m" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-editar") as HTMLButtonElement).click();
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "Novo Nome";
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();

    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.provedores[0].nome).toBe("Novo Nome");
  });

  it("remover provedor atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "a", nome: "A", tipo: "t", url_base: "u", modelo: "m" },
        { id: "b", nome: "B", tipo: "t", url_base: "u", modelo: "m" },
      ],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelectorAll(".btn-remover")[0] as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0].id).toBe("b");
  });

  it("selecionar ativo/reserva persiste", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    const selAtivo = raiz.querySelector("#sel-ativo") as HTMLSelectElement;
    selAtivo.value = "s";
    selAtivo.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 0));

    expect(cfgEmMemoria!.ativo).toBe("s");
  });

  it("formulário recusa ID duplicado em novo", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "existente", nome: "E", tipo: "t", url_base: "u", modelo: "m" }],
    };
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
    await new Promise((r) => setTimeout(r, 0));

    expect(raiz.textContent).toContain("Já existe um provedor");
    expect(cfgEmMemoria!.provedores).toHaveLength(1);
  });

  it("formulário recusa campos obrigatórios vazios", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(raiz.textContent).toContain("Preencha todos os campos obrigatórios");
  });

  it("botão testar credencial verifica existência sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m", credencial_ref: "provedor:s" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisProvedores(raiz);
    await aba.montar();

    (raiz.querySelector(".btn-testar-cred") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockCofreExiste).toHaveBeenCalledWith("provedor", "s");
    expect(raiz.textContent).toContain("Credencial encontrada");
    expect(raiz.textContent).not.toContain("chave-secreta");
  });
});