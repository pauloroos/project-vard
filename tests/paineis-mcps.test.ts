import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { StatusPonte } from "../src/conectores/ponte/cliente";

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
import { AbaPaineisMcps, AVISO_SERVICOS_DESLIGADOS, VAZIO_LISTA } from "../src/ui/paineis-mcps";

const mockCofreExiste = vi.mocked(cofreExiste);
const PONTE_NO_AR: StatusPonte = { ok: true, modo: "normal" };

/** Espera uma volta do evento (o salvar é assíncrono: grava, redesenha e fecha o modal). */
const esperar = () => new Promise((r) => setTimeout(r, 0));

describe("paineis-mcps (T7) — Ferramentas (MCP)", () => {
  beforeEach(() => {
    cfgEmMemoria = null;
    mockCofreExiste.mockReset();
  });

  afterEach(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); // fecha modal aberto
    document.body.innerHTML = "";
  });

  function criarRaiz(): HTMLElement {
    const el = document.createElement("div");
    document.body.appendChild(el);
    return el;
  }

  async function montar(raiz: HTMLElement, ponteNoAr = true) {
    const aba = new AbaPaineisMcps(raiz, { statusPonte: async () => (ponteNoAr ? PONTE_NO_AR : null) });
    await aba.montar();
    return aba;
  }

  function modal(): HTMLElement {
    const m = document.querySelector<HTMLElement>(".modal");
    if (!m) throw new Error("modal não está aberto");
    return m;
  }

  function campo(id: string): HTMLInputElement {
    return modal().querySelector<HTMLInputElement>(`#${id}`)!;
  }

  function clicarSalvar() {
    (modal().querySelector<HTMLButtonElement>(".modal-acoes button.primaria")!).click();
  }

  function preencher(v: { id?: string; nome?: string; tipo?: "stdio" | "http"; command?: string; args?: string; url?: string; cred?: string }) {
    if (v.id !== undefined) campo("mcp-id").value = v.id;
    if (v.nome !== undefined) campo("mcp-nome").value = v.nome;
    if (v.tipo) {
      const sel = modal().querySelector<HTMLSelectElement>("#mcp-tipo")!;
      sel.value = v.tipo;
      sel.dispatchEvent(new Event("change"));
    }
    if (v.command !== undefined) campo("mcp-command").value = v.command;
    if (v.args !== undefined) campo("mcp-args").value = v.args;
    if (v.url !== undefined) campo("mcp-url").value = v.url;
    if (v.cred !== undefined) campo("mcp-cred").value = v.cred;
  }

  function abrirModalAdicionar(raiz: HTMLElement) {
    (raiz.querySelector<HTMLButtonElement>(".cards-vazio button, .cards-adicionar")!).click();
  }

  function card(raiz: HTMLElement, id: string): HTMLElement {
    const el = raiz.querySelector<HTMLElement>(`.card[data-id="${id}"]`);
    if (!el) throw new Error(`card ${id} não encontrado`);
    return el;
  }

  function acaoCard(raiz: HTMLElement, id: string, rotulo: string): HTMLButtonElement {
    const b = [...card(raiz, id).querySelectorAll<HTMLButtonElement>(".card-acoes button")]
      .find((x) => x.textContent === rotulo);
    if (!b) throw new Error(`ação ${rotulo} não encontrada no card ${id}`);
    return b;
  }

  it("título interno da seção é Ferramentas (MCP)", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    expect(raiz.querySelector(".mcp-titulo h2")!.textContent).toBe("Ferramentas (MCP)");
    expect(raiz.textContent).toContain("dão ferramentas ao Vard");
  });

  it("lista vazia mostra o estado vazio e o botão de adicionar", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    expect(raiz.textContent).toContain(VAZIO_LISTA);
    expect(raiz.querySelector(".cards-vazio button")!.textContent).toBe("Adicionar servidor");
  });

  it("adicionar servidor stdio pelo modal salva e vira card", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "fs", nome: "Filesystem", tipo: "stdio", command: "node", args: "--verbose --port 3000" });
    clicarSalvar();
    await esperar();

    expect(document.querySelector(".modal")).toBeNull();
    expect(cfgEmMemoria!.mcps).toHaveLength(1);
    expect(cfgEmMemoria!.mcps[0]).toMatchObject({
      id: "fs", nome: "Filesystem", habilitado: true, command: "node", args: ["--verbose", "--port", "3000"],
    });
    const c = card(raiz, "fs");
    expect(c.querySelector(".card-etiqueta")!.textContent).toBe("stdio");
    expect(c.textContent).toContain("Habilitado");
    expect(c.textContent).toContain("comando: node --verbose --port 3000");
  });

  it("adicionar servidor http pelo modal salva com credencial por referência", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "api", nome: "API Remota", tipo: "http", url: "https://exemplo.com/mcp", cred: "cofre:api_mcp" });
    clicarSalvar();
    await esperar();

    expect(cfgEmMemoria!.mcps).toHaveLength(1);
    expect(cfgEmMemoria!.mcps[0]).toMatchObject({
      id: "api", url: "https://exemplo.com/mcp", credencial_ref: "cofre:api_mcp",
    });
    expect(cfgEmMemoria!.mcps[0].command).toBeUndefined();
    const c = card(raiz, "api");
    expect(c.querySelector(".card-etiqueta")!.textContent).toBe("http");
    expect(c.textContent).toContain("url: https://exemplo.com/mcp");
    expect(c.textContent).toContain("credencial: cofre:api_mcp");
  });

  it("trocar o tipo no modal mostra só os campos daquele tipo", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    const grupoStdio = modal().querySelector<HTMLElement>("#mcp-grupo-stdio")!;
    const grupoHttp = modal().querySelector<HTMLElement>("#mcp-grupo-http")!;
    expect(grupoStdio.hidden).toBe(false);
    expect(grupoHttp.hidden).toBe(true);
    preencher({ tipo: "http" });
    expect(grupoStdio.hidden).toBe(true);
    expect(grupoHttp.hidden).toBe(false);
  });

  it("editar servidor abre o modal preenchido e grava o novo nome", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m1", nome: "Antigo", habilitado: true, command: "old" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    acaoCard(raiz, "m1", "Editar").click();

    expect(modal().querySelector(".modal-titulo")!.textContent).toBe("Editar servidor MCP");
    expect(campo("mcp-id").value).toBe("m1");
    expect(modal().querySelector<HTMLInputElement>("#mcp-id")!.readOnly).toBe(true);
    expect(modal().querySelector<HTMLInputElement>("#mcp-command")!.value).toBe("old");
    preencher({ nome: "Novo Nome" });
    clicarSalvar();
    await esperar();

    expect(cfgEmMemoria!.mcps).toHaveLength(1);
    expect(cfgEmMemoria!.mcps[0].nome).toBe("Novo Nome");
    expect(card(raiz, "m1").querySelector("h3")!.textContent).toBe("Novo Nome");
  });

  it("remover some do card e grava a lista menor", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [
        { id: "a", nome: "A", habilitado: true, command: "c1" },
        { id: "b", nome: "B", habilitado: true, url: "u1" },
      ],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    acaoCard(raiz, "a", "Remover").click();
    await esperar();

    expect(cfgEmMemoria!.mcps).toHaveLength(1);
    expect(cfgEmMemoria!.mcps[0].id).toBe("b");
    expect(raiz.querySelector('.card[data-id="a"]')).toBeNull();
    expect(raiz.textContent).toContain("A removido.");
  });

  it("habilitar e desabilitar trocam o selo e persistem", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m", nome: "M", habilitado: true, command: "c" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    acaoCard(raiz, "m", "Desabilitar").click();
    await esperar();

    expect(cfgEmMemoria!.mcps[0].habilitado).toBe(false);
    expect(card(raiz, "m").textContent).toContain("Desabilitado");
    expect(raiz.textContent).toContain("M desabilitado.");

    acaoCard(raiz, "m", "Habilitar").click();
    await esperar();
    expect(cfgEmMemoria!.mcps[0].habilitado).toBe(true);
    expect(card(raiz, "m").textContent).toContain("Habilitado");
  });

  it("identificador repetido é recusado e o modal continua aberto", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "existente", nome: "E", habilitado: true, command: "c" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "existente", nome: "N", command: "c" });
    clicarSalvar();
    await esperar();

    expect(document.querySelector(".modal")).not.toBeNull();
    expect(modal().querySelector(".modal-aviso")!.textContent).toContain("Já existe um servidor");
    expect(cfgEmMemoria!.mcps).toHaveLength(1);
  });

  it("stdio sem comando é recusado no modal", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "x", nome: "X", tipo: "stdio" });
    clicarSalvar();
    await esperar();

    expect(modal().querySelector(".modal-aviso")!.textContent).toContain("stdio exige o campo Comando");
    expect(cfgEmMemoria).toBeNull();
  });

  it("http sem url é recusado no modal", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "x", nome: "X", tipo: "http" });
    clicarSalvar();
    await esperar();

    expect(modal().querySelector(".modal-aviso")!.textContent).toContain("http exige o campo URL");
  });

  it("referência de credencial fora do formato tipo:id é recusada", async () => {
    const raiz = criarRaiz();
    await montar(raiz);
    abrirModalAdicionar(raiz);
    preencher({ id: "x", nome: "X", command: "c", cred: "sem-formato" });
    clicarSalvar();
    await esperar();

    expect(modal().querySelector(".modal-aviso")!.textContent).toContain("formato tipo:id");
  });

  it("sem credencial o card não oferece Testar", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "s", nome: "S", habilitado: true, command: "c" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    expect(raiz.textContent).not.toContain("Testar");
  });

  it("testar credencial marca ok no card sem expor valor", async () => {
    mockCofreExiste.mockResolvedValue(true);
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m", nome: "M", habilitado: true, command: "c", credencial_ref: "mcp:m" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    acaoCard(raiz, "m", "Testar").click();
    await new Promise((r) => setTimeout(r, 20));

    expect(mockCofreExiste).toHaveBeenCalledWith("mcp", "m");
    expect(card(raiz, "m").textContent).toContain("credencial ok");
    expect(raiz.textContent).toContain("Credencial de M encontrada no cofre.");
    expect(document.body.textContent).not.toContain("chave-secreta");
  });

  it("testar credencial ausente marca ausente e avisa", async () => {
    mockCofreExiste.mockResolvedValue(false);
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "api", nome: "API", habilitado: true, url: "https://x", credencial_ref: "cofre:api" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    acaoCard(raiz, "api", "Testar").click();
    await new Promise((r) => setTimeout(r, 20));

    expect(card(raiz, "api").textContent).toContain("credencial ausente");
    expect(raiz.textContent).toContain("não está no cofre");
  });

  it("aviso de serviços desligados aparece no topo quando a ponte está fora", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "m", nome: "M", habilitado: true, command: "c" }],
    };
    const raiz = criarRaiz();
    await montar(raiz, false);
    await esperar();

    const aviso = raiz.querySelector<HTMLElement>("#mcp-aviso-servicos")!;
    expect(aviso.hidden).toBe(false);
    expect(aviso.textContent).toBe(AVISO_SERVICOS_DESLIGADOS);
    expect(aviso.role).toBe("alert");
    expect(raiz.firstElementChild).toBe(aviso); // no topo
    expect(raiz.querySelector(".card")).not.toBeNull(); // a lista continua visível
  });

  it("sem aviso quando a ponte responde", async () => {
    const raiz = criarRaiz();
    await montar(raiz, true);
    await esperar();

    expect(raiz.querySelector<HTMLElement>("#mcp-aviso-servicos")!.hidden).toBe(true);
  });

  it("com oito servidores aparece a busca que filtra os cards", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: Array.from({ length: 8 }, (_, i) => ({
        id: `srv-${i}`, nome: `Servidor ${i}`, habilitado: i % 2 === 0,
        ...(i % 2 === 0 ? { command: `cmd${i}` } : { url: `https://exemplo.com/${i}` }),
      })),
    };
    const raiz = criarRaiz();
    await montar(raiz);

    const busca = raiz.querySelector<HTMLInputElement>(".cards-busca")!;
    expect(busca).not.toBeNull();
    busca.value = "srv-3";
    busca.dispatchEvent(new Event("input"));
    const visiveis = [...raiz.querySelectorAll<HTMLElement>(".card")].filter((c) => !c.hidden);
    expect(visiveis.map((c) => c.dataset.id)).toEqual(["srv-3"]);
  });

  it("o card http sem credencial também não oferece Testar", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      mcps: [{ id: "h", nome: "H", habilitado: false, url: "https://exemplo.com/mcp" }],
    };
    const raiz = criarRaiz();
    await montar(raiz);
    expect([...card(raiz, "h").querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "Habilitar", "Editar", "Remover",
    ]);
  });
});
