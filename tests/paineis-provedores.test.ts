import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO, validarPaineis } from "../src/config/paineis";
import type { CliDetectada } from "../src/config/clis";

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

describe("paineis-provedores CLIs (T17a)", () => {
  const claude: CliDetectada = {
    tipo: "cli-claude",
    instalada: true,
    versao: "2.0.0-falso",
    modelos: ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
  };
  const agy: CliDetectada = {
    tipo: "cli-agy",
    instalada: true,
    versao: "0.9.0-falso",
    modelos: ["gemini-3.8-flash-low", "gemini-3.8-pro"],
  };

  const tick = () => new Promise((r) => setTimeout(r, 0));

  beforeEach(() => {
    cfgEmMemoria = null;
    mockCofreExiste.mockReset();
  });

  async function abrir(comClis: CliDetectada[]) {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const aba = new AbaPaineisProvedores(el, { detectar: async () => comClis });
    await aba.montar();
    (el.querySelector("#btn-adicionar-provedor") as HTMLButtonElement).click();
    return el;
  }

  function preencherCli(raiz: HTMLElement, tipo: string, modelo: string) {
    (raiz.querySelector("#prov-id") as HTMLInputElement).value = "claude-1";
    (raiz.querySelector("#prov-nome") as HTMLInputElement).value = "Claude Code";
    const campoTipo = raiz.querySelector("#prov-tipo") as HTMLInputElement;
    campoTipo.value = tipo;
    campoTipo.dispatchEvent(new Event("input"));
    (raiz.querySelector("#prov-modelo") as HTMLInputElement).value = modelo;
  }

  it("cadastrar cli-claude pede confirmação e só grava confirmado", async () => {
    const raiz = await abrir([claude, agy]);
    preencherCli(raiz, "cli-claude", "claude-sonnet-5-5");
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();
    await tick();

    expect(raiz.querySelector("#confirmar-cli")!.hasAttribute("hidden")).toBe(false);
    expect(raiz.textContent).toContain("roda com poder completo no seu PC");
    expect(raiz.textContent).toContain("sem pedir permissão");
    expect(cfgEmMemoria?.provedores ?? []).toHaveLength(0);   // ainda nada gravado

    (raiz.querySelector("#btn-confirmar-cli") as HTMLButtonElement).click();
    await tick();

    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0]).toMatchObject({
      id: "claude-1",
      tipo: "cli-claude",
      modelo: "claude-sonnet-5-5",
      url_base: "",
      yolo: true,
      enxuto: false,
    });
    expect(cfgEmMemoria!.provedores[0].credencial_ref).toBeUndefined();
  });

  it("cancelar a confirmação não grava", async () => {
    const raiz = await abrir([claude, agy]);
    preencherCli(raiz, "cli-agy", "gemini-3.8-flash-low");
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();
    await tick();
    expect(raiz.querySelector("#confirmar-cli")!.hasAttribute("hidden")).toBe(false);

    (raiz.querySelector("#btn-cancelar-cli") as HTMLButtonElement).click();
    await tick();

    expect(cfgEmMemoria?.provedores ?? []).toHaveLength(0);
    expect(raiz.textContent).toContain("nada foi gravado");
  });

  it("yolo vem marcado e enxuto desmarcado; opções gravadas", async () => {
    const raiz = await abrir([claude, agy]);
    preencherCli(raiz, "cli-claude", "claude-haiku-5-5");

    expect((raiz.querySelector("#prov-yolo") as HTMLInputElement).checked).toBe(true);
    expect((raiz.querySelector("#prov-enxuto") as HTMLInputElement).checked).toBe(false);

    (raiz.querySelector("#prov-yolo") as HTMLInputElement).checked = false;
    (raiz.querySelector("#prov-enxuto") as HTMLInputElement).checked = true;
    (raiz.querySelector("#prov-esforco") as HTMLInputElement).value = "alto";
    (raiz.querySelector("#btn-salvar-provedor") as HTMLButtonElement).click();
    (raiz.querySelector("#btn-confirmar-cli") as HTMLButtonElement).click();
    await tick();

    expect(cfgEmMemoria!.provedores[0]).toMatchObject({ yolo: false, enxuto: true, esforco: "alto" });
  });

  it("tipo cli só aparece na lista quando detectado", async () => {
    const raiz = await abrir([claude]);                       // agy não instalada
    const opcoes = [...raiz.querySelectorAll<HTMLOptionElement>("#lista-tipos option")].map((o) => o.value);
    expect(opcoes).toContain("cli-claude");
    expect(opcoes).not.toContain("cli-agy");
    expect(raiz.textContent).not.toContain("cli-agy");

    const vazia = await abrir([]);                            // nenhuma CLI detectada
    expect(vazia.querySelectorAll("#lista-tipos option")).toHaveLength(0);
    expect(vazia.textContent).not.toContain("cli-claude");
  });

  it("modelo vem por lista da detecção", async () => {
    const raiz = await abrir([claude, agy]);
    preencherCli(raiz, "cli-agy", "gemini-3.8-flash-low");
    const modelos = [...raiz.querySelectorAll<HTMLOptionElement>("#lista-modelo option")].map((o) => o.value);
    expect(modelos).toEqual(["gemini-3.8-flash-low", "gemini-3.8-pro"]);
  });

  it("validação recusa url_base e credencial em tipo cli", () => {
    const base = {
      versao: 1 as const,
      provedores: [{ id: "c1", nome: "Claude", tipo: "cli-claude", url_base: "", modelo: "claude-sonnet-5-5" }],
      ativo: null,
      reserva: null,
      agentes: PAINEIS_PADRAO.agentes,
      mcps: [],
    };
    expect(() => validarPaineis({
      ...base,
      provedores: [{ ...base.provedores[0], url_base: "http://127.0.0.1:1234" }],
    })).toThrow(/url_base/);
    expect(() => validarPaineis({
      ...base,
      provedores: [{ ...base.provedores[0], credencial_ref: "provedor:x" }],
    })).toThrow(/credencial/);

    const lido = validarPaineis(base);
    expect(lido.provedores[0].yolo).toBe(true);              // padrão do 0.8
    expect(lido.provedores[0].enxuto).toBe(false);
    expect(lido.provedores[0].url_base).toBe("");
  });
});