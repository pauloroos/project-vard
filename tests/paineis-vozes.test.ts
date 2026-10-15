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
import { AbaPaineisVozes } from "../src/ui/paineis-vozes";

const mockCofreExiste = vi.mocked(cofreExiste);

describe("paineis-vozes (T6)", () => {
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
    (raiz.querySelector("#voz-id") as HTMLInputElement).value = "kokoro";
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "Kokoro Local";
    (raiz.querySelector("#voz-tipo") as HTMLSelectElement).value = "kokoro";
    (raiz.querySelector("#voz-url") as HTMLInputElement).value = "http://127.0.0.1:9000";
    (raiz.querySelector("#voz-modelo") as HTMLInputElement).value = "kokoro-v1";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0].id).toBe("kokoro");
    expect(cfgEmMemoria!.provedores[0].nome).toBe("Kokoro Local");
    expect(raiz.textContent).toContain("Kokoro Local");
  });

  it("editar voz existente atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "x", nome: "Antigo", tipo: "suad", url_base: "u", modelo: "m" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    (raiz.querySelector(".btn-editar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "Novo Nome";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.provedores[0].nome).toBe("Novo Nome");
  });

  it("remover voz atualiza config", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "a", nome: "A", tipo: "suad", url_base: "u", modelo: "m" },
        { id: "b", nome: "B", tipo: "kokoro", url_base: "u", modelo: "m" },
      ],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    (raiz.querySelectorAll(".btn-remover-voz")[0] as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0].id).toBe("b");
  });

  it("selecionar voz ativa persiste", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "suad", url_base: "u", modelo: "m" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    const selAtivo = raiz.querySelector("#sel-voz-ativa") as HTMLSelectElement;
    selAtivo.value = "s";
    selAtivo.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 0));
    expect(cfgEmMemoria!.ativo).toBe("s");
  });

  it("formulário recusa ID duplicado em novo", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "existente", nome: "E", tipo: "suad", url_base: "u", modelo: "m" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#voz-id") as HTMLInputElement).value = "existente";
    (raiz.querySelector("#voz-nome") as HTMLInputElement).value = "N";
    (raiz.querySelector("#voz-tipo") as HTMLSelectElement).value = "suad";
    (raiz.querySelector("#voz-url") as HTMLInputElement).value = "u";
    (raiz.querySelector("#voz-modelo") as HTMLInputElement).value = "m";
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(raiz.textContent).toContain("Já existe uma voz");
    expect(cfgEmMemoria!.provedores).toHaveLength(1);
  });

  it("formulário recusa campos obrigatórios vazios", async () => {
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    (raiz.querySelector("#btn-adicionar-voz") as HTMLButtonElement).click();
    (raiz.querySelector("#btn-salvar-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(raiz.textContent).toContain("Preencha todos os campos obrigatórios");
  });

  it("botão testar credencial verifica existência sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "s", nome: "S", tipo: "suad", url_base: "u", modelo: "m", credencial_ref: "voz:s" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaPaineisVozes(raiz);
    await aba.montar();
    (raiz.querySelector(".btn-testar-cred-voz") as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 50));
    expect(mockCofreExiste).toHaveBeenCalledWith("voz", "s");
    expect(raiz.textContent).toContain("Credencial encontrada");
    expect(raiz.textContent).not.toContain("chave-secreta");
  });
});