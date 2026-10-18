import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { Config } from "../src/config/config";
import { CONFIG_PADRAO } from "../src/config/config";

// Estado em memória simulando o arquivo paineis.json via invoke
let cfgEmMemoria: PaineisConfig | null = null;
let configEmMemoria: Config = { ...CONFIG_PADRAO };

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation((cmd: string, args?: Record<string, unknown>) => {
    if (cmd === "ler_paineis") return Promise.resolve(cfgEmMemoria);
    if (cmd === "gravar_paineis") {
      cfgEmMemoria = (args?.valor as PaineisConfig) ?? null;
      return Promise.resolve(undefined);
    }
    if (cmd === "ler_config") return Promise.resolve(configEmMemoria);
    if (cmd === "gravar_config") {
      configEmMemoria = (args?.valor as Config) ?? configEmMemoria;
      return Promise.resolve(undefined);
    }
    return Promise.resolve(null);
  }),
}));

vi.mock("../src/config/clis", () => ({
  detectarClis: vi.fn().mockResolvedValue([]),
}));

// Mock de atualizarConfig para refletir mudanças no configEmMemoria
vi.mock("../src/config/config", async () => {
  const actual = await vi.importActual<typeof import("../src/config/config")>("../src/config/config");
  return {
    ...actual,
    atualizarConfig: vi.fn(async (patch: Partial<Config>) => {
      configEmMemoria = { ...configEmMemoria, ...patch };
      return configEmMemoria;
    }),
  };
});

import { AbaModelos, resumoTeste, type DepsQuemResponde } from "../src/ui/aba-modelos";
import { detectarClis } from "../src/config/clis";

const mockDetectarClis = vi.mocked(detectarClis);

function criarRaiz(): HTMLElement {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return el;
}

function criarDeps(overrides: Partial<DepsQuemResponde> = {}): DepsQuemResponde {
  return {
    criarOj: () => ({
      modelos: async () => ["modelo-oj-1", "modelo-oj-2"],
      perguntar: async () => "ok",
    }) as any,
    statusPonte: async () => ({ ok: true, modo: "ligado" }) as any,
    ponteUrl: "http://127.0.0.1:8765",
    config: { ...configEmMemoria },
    ...overrides,
  };
}

describe("AbaModelos (Núcleo)", () => {
  it("caixa do OpenJarvis persiste a opção extra e avisa sobre reiniciar serviços", async () => {
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
    const aoMudarUsoOpenJarvis = vi.fn();
    const deps = criarDeps({ aoMudarUsoOpenJarvis });
    const raiz = criarRaiz();
    await new AbaModelos(raiz, deps).carregar();
    const card = raiz.querySelector<HTMLElement>('[data-id="__oj__"]')!;
    const caixa = card.querySelector<HTMLInputElement>('input[type="checkbox"]');
    expect(caixa?.checked).toBe(false);
    expect(caixa?.closest("label")?.textContent).toContain("Manter o OpenJarvis ligado mesmo quando ele não responde");
    caixa!.click();
    await vi.waitFor(() => expect(configEmMemoria.usar_openjarvis).toBe(true));
    expect(configEmMemoria.cerebro).toBe("proprio");
    expect(deps.config.usar_openjarvis).toBe(true);
    expect(aoMudarUsoOpenJarvis).toHaveBeenCalledWith(true);
    expect(card.querySelector('[role="status"]')?.textContent).toContain("reiniciar os serviços");
    caixa!.click();
    await vi.waitFor(() => expect(configEmMemoria.usar_openjarvis).toBe(false));
  });
  it("CLI localizada pelo instalador é reconhecida no cadastro mesmo fora do PATH antigo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ itens: [{
      id: "claude", nome: "Claude Code", descricao: "CLI", comando: [],
      fonte: "https://code.claude.com/docs/en/setup", tipo_provedor: "cli-claude",
      url_base: "", tamanho_mb: null, manual: false, instalado: true, login: "ausente",
      estado: "aguardando", linhas: [],
    }] }))));
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps()).carregar();
    [...raiz.querySelectorAll<HTMLButtonElement>("button")].find(b => b.textContent === "Cadastrar provedor")!.click();
    await vi.waitFor(() => expect(raiz.querySelector(".modal")?.textContent).toContain("Encontrado no PC: Claude Code"));
    expect(raiz.querySelector<HTMLElement>(".qr-cli-nao-encontrado")?.hidden).toBe(true);
  });
  it("oferece instalação e pré-preenche cadastro ao cadastrar item detectado", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith("/instalaveis") ? { itens: [{
        id: "ollama", nome: "Ollama", descricao: "Servidor local", comando: [],
        fonte: "https://docs.ollama.com/windows", tipo_provedor: "ollama",
        url_base: "http://127.0.0.1:11434/v1", tamanho_mb: null, manual: false,
        instalado: true, login: "dispensado", estado: "aguardando", linhas: [],
      }] } : []
    ))));
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps()).carregar();
    const cadastrar = [...raiz.querySelectorAll<HTMLButtonElement>("button")].find(b => b.textContent === "Cadastrar provedor");
    expect(cadastrar).toBeTruthy(); cadastrar!.click();
    await vi.waitFor(() => expect(raiz.querySelector<HTMLInputElement>('input[placeholder="Nome do provedor"]')?.value).toBe("Ollama"));
    expect(raiz.querySelector<HTMLInputElement>('input[type="url"]')?.value).toBe("http://127.0.0.1:11434/v1");
    expect(raiz.querySelector<HTMLSelectElement>(".modal select")?.value).toBe("ollama");
    expect(raiz.querySelector(".modal-titulo")?.textContent).toBe("Adicionar provedor");
    vi.unstubAllGlobals();
  });
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]")));
    cfgEmMemoria = null;
    configEmMemoria = { ...CONFIG_PADRAO };
    mockDetectarClis.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renderiza card fixo do OpenJarvis e botão adicionar", async () => {
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();
    expect(raiz.textContent).toContain("OpenJarvis (servidor atual)");
    expect(raiz.textContent).toContain("Adicionar provedor");
  });

  it("OpenJarvis fora do ar mostra selo de aviso", async () => {
    const raiz = criarRaiz();
    const deps = criarDeps({
      criarOj: () => ({ modelos: async () => { throw new Error("fora"); } }) as any,
    });
    const aba = new AbaModelos(raiz, deps);
    await aba.carregar();
    expect(raiz.textContent).toContain("Fora do ar");
  });

  it("ponte fora mostra aviso U8 no topo", async () => {
    const raiz = criarRaiz();
    const deps = criarDeps({ statusPonte: async () => null });
    const aba = new AbaModelos(raiz, deps);
    await aba.carregar();
    // Aguardar renderização
    await new Promise((r) => setTimeout(r, 10));
    expect(raiz.textContent).toContain("Os serviços do Vard estão desligados");
  });

  it("Usar este no OpenJarvis grava cerebro=openjarvis", async () => {
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
    const raiz = criarRaiz();
    const deps = criarDeps({ config: { ...configEmMemoria } });
    const aba = new AbaModelos(raiz, deps);
    await aba.carregar();

    const btns = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button"));
    const usarOj = btns.find((b) => b.textContent === "Usar este");
    expect(usarOj).toBeTruthy();
    usarOj!.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(configEmMemoria.cerebro).toBe("openjarvis");
  });

  it("Testar do card manda o id do provedor para o núcleo usar a chave do cofre", async () => {
    const corpos: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).includes("/primeiro-uso/cerebro/testar")) {
        corpos.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify({ ok: true, detalhe: "resposta_recebida", primeiro_token_ms: 42 }));
      }
      return new Response("[]");
    }));
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "lm", nome: "LM Studio", tipo: "lmstudio", url_base: "http://localhost:1234/v1", modelo: "llama-3", credencial_ref: "provedor:lm" }],
    };
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();
    const testar = Array.from(raiz.querySelectorAll<HTMLButtonElement>('[data-id="lm"] button')).find((b) => b.textContent === "Testar");
    testar!.click();
    await new Promise((r) => setTimeout(r, 50));
    expect(corpos[0]).toMatchObject({ tipo: "lmstudio", provedor_id: "lm" });
    expect(raiz.textContent).toContain("Conexão OK (42 ms)");
    vi.unstubAllGlobals();
  });

  it("resumo do Testar: Codex instalado mostra a versão, CLI ausente avisa", () => {
    expect(resumoTeste({ ok: true, detalhe: "instalada codex-cli 0.1", primeiro_token_ms: null })).toBe("OK: instalada codex-cli 0.1");
    expect(resumoTeste({ ok: false, detalhe: "cli_nao_encontrada" })).toBe("CLI não encontrada neste PC.");
  });

  it("Usar este em provedor grava cerebro=proprio e paineis.ativo", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "lm", nome: "LM Studio", tipo: "lmstudio", url_base: "http://localhost:1234/v1", modelo: "llama-3" }],
    };
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "openjarvis" };
    const raiz = criarRaiz();
    const deps = criarDeps({ config: { ...configEmMemoria } });
    const aba = new AbaModelos(raiz, deps);
    await aba.carregar();

    const btns = Array.from(raiz.querySelectorAll<HTMLButtonElement>('[data-id="lm"] button'));
    const usarProv = btns.find((b) => b.textContent === "Usar este");
    expect(usarProv).toBeTruthy();
    usarProv!.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(configEmMemoria.cerebro).toBe("proprio");
    expect(cfgEmMemoria!.ativo).toBe("lm");
  });

  it("o provedor que já responde não mostra Usar este nem Reserva", async () => {
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      ativo: "a",
      provedores: [
        { id: "a", nome: "A", tipo: "lmstudio", url_base: "http://a", modelo: "m" },
        { id: "b", nome: "B", tipo: "lmstudio", url_base: "http://b", modelo: "m" },
      ],
    };
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps()).carregar();
    const rotulos = (id: string) => Array.from(raiz.querySelectorAll<HTMLButtonElement>(`[data-id="${id}"] button`)).map((b) => b.textContent);
    expect(rotulos("a")).not.toContain("Usar este");
    expect(rotulos("a")).not.toContain("Reserva");
    expect(rotulos("b")).toContain("Usar este");
  });

  it("Reserva alterna entre provedores", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "a", nome: "A", tipo: "lmstudio", url_base: "http://a", modelo: "m" },
        { id: "b", nome: "B", tipo: "lmstudio", url_base: "http://b", modelo: "m" },
      ],
    };
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btns = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button"));
    const reservaA = btns.filter((b) => b.textContent === "Reserva")[0];
    reservaA!.click();
    await new Promise((r) => setTimeout(r, 50));
    expect(cfgEmMemoria!.reserva).toBe("a");

    // Clicar de novo desmarca
    const btns2 = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button"));
    const reservaA2 = btns2.filter((b) => b.textContent === "Reserva")[0];
    reservaA2!.click();
    await new Promise((r) => setTimeout(r, 50));
    expect(cfgEmMemoria!.reserva).toBeNull();
  });

  it("Remover provedor atualiza lista e limpa ativo/reserva", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "x", nome: "X", tipo: "lmstudio", url_base: "http://x", modelo: "m" }],
      ativo: "x",
      reserva: "x",
    };
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btns = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button"));
    const remover = btns.find((b) => b.textContent === "Remover");
    remover!.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(cfgEmMemoria!.provedores).toHaveLength(0);
    expect(cfgEmMemoria!.ativo).toBeNull();
    expect(cfgEmMemoria!.reserva).toBeNull();
  });

  it("Modal valida endpoint vazio para provedor não-CLI", async () => {
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    expect(btnAdd).toBeTruthy();
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Preencher nome e modelo mas deixar URL vazia
    const inputs = Array.from(raiz.querySelectorAll<HTMLInputElement>("input"));
    const nomeInput = inputs.find((i) => i.placeholder?.includes("Nome"));
    const modeloInput = inputs.find((i) => i.placeholder?.includes("Modelo padrão"));
    if (nomeInput) nomeInput.value = "Teste";
    if (modeloInput) modeloInput.value = "modelo-x";

    const btnSalvar = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Salvar");
    expect(btnSalvar).toBeTruthy();
    btnSalvar!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Modal deve mostrar erro e não fechar
    expect(raiz.textContent).toContain("Preencha nome, tipo, endpoint e modelo");
  });

  it("Buscar modelos preenche select via fetch simulado", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string | URL | Request) => {
      const s = typeof url === "string" ? url : url.toString();
      if (s.includes("/primeiro-uso/cerebro/modelos")) {
        return new Response(JSON.stringify({ ok: true, modelos: [{ id: "m1" }, { id: "m2" }] }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: false }), { status: 404 });
    }));

    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    // Abrir modal
    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Preencher URL e clicar Buscar modelos
    const urlInput = Array.from(raiz.querySelectorAll<HTMLInputElement>("input")).find((i) => i.placeholder?.includes("localhost"));
    if (urlInput) urlInput.value = "http://localhost:1234/v1";

    const btnBuscar = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Buscar modelos");
    expect(btnBuscar).toBeTruthy();
    btnBuscar!.click();
    await new Promise((r) => setTimeout(r, 100));

    // O select de modelos é o segundo select dentro do modal (o primeiro é o de tipo)
    const modal = raiz.querySelector(".modal");
    expect(modal).toBeTruthy();
    const selects = Array.from(modal!.querySelectorAll<HTMLSelectElement>("select"));
    const modelosSel = selects[1];
    expect(modelosSel).toBeTruthy();
    const opcoes = Array.from(modelosSel!.options).map((o) => o.value);
    expect(opcoes).toContain("m1");
    expect(opcoes).toContain("m2");

    vi.unstubAllGlobals();
  });

  it("CLI detectada aparece sugerida no modal", async () => {
    mockDetectarClis.mockResolvedValue([
      { tipo: "cli-claude", instalada: true, versao: "2.1.301", modelos: ["claude-sonnet-5-5"] },
    ]);
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    // Abrir modal
    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Selecionar tipo cli-claude
    const selects = Array.from(raiz.querySelectorAll<HTMLSelectElement>("select"));
    const tipoSel = selects.find((s) => Array.from(s.options).some((o) => o.value === "cli-claude"));
    expect(tipoSel).toBeTruthy();
    tipoSel!.value = "cli-claude";
    tipoSel!.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));

    expect(raiz.textContent).toContain("Encontrado no PC");
    expect(raiz.textContent).toContain("Claude Code 2.1.301");
  });

  it("Agentes gravados pelo card da CLI com checkbox delegada", async () => {
    mockDetectarClis.mockResolvedValue([
      { tipo: "cli-claude", instalada: true, versao: "2.1.301", modelos: ["claude-sonnet-5-5"] },
    ]);
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    // Abrir modal
    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Selecionar CLI
    const selects = Array.from(raiz.querySelectorAll<HTMLSelectElement>("select"));
    const tipoSel = selects.find((s) => Array.from(s.options).some((o) => o.value === "cli-claude"));
    tipoSel!.value = "cli-claude";
    tipoSel!.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));

    // Preencher nome e modelo
    const inputs = Array.from(raiz.querySelectorAll<HTMLInputElement>("input"));
    const nomeInput = inputs.find((i) => i.placeholder?.includes("Nome"));
    const modeloInput = inputs.find((i) => i.placeholder?.includes("Modelo padrão"));
    if (nomeInput) nomeInput.value = "Claude CLI";
    if (modeloInput) modeloInput.value = "claude-sonnet-5-5";

    // Marcar checkbox delegada
    const checkboxes = Array.from(raiz.querySelectorAll<HTMLInputElement>("input[type='checkbox']"));
    const delegadaChk = checkboxes.find((c) => c.parentElement?.textContent?.includes("delegadas"));
    if (delegadaChk) delegadaChk.checked = true;

    // Salvar
    const btnSalvar = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Salvar");
    btnSalvar!.click();
    await new Promise((r) => setTimeout(r, 100));

    expect(cfgEmMemoria!.provedores).toHaveLength(1);
    expect(cfgEmMemoria!.provedores[0].tipo).toBe("cli-claude");
    expect(cfgEmMemoria!.agentes.claude.padrao).toBe("claude-sonnet-5-5");
  });

  it("Modal adapta campos para CLI: esconde endpoint/chave/buscar, mostra yolo/enxuto/C11 e detecção", async () => {
    mockDetectarClis.mockResolvedValue([
      { tipo: "cli-claude", instalada: true, versao: "2.1.301", modelos: ["claude-sonnet-5-5"] },
    ]);
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    // Selecionar tipo CLI
    const selects = Array.from(raiz.querySelectorAll<HTMLSelectElement>("select"));
    const tipoSel = selects.find((s) => Array.from(s.options).some((o) => o.value === "cli-claude"));
    tipoSel!.value = "cli-claude";
    tipoSel!.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));

    // Endpoint, chave e buscar devem estar escondidos
    const modal = raiz.querySelector(".modal")!;
    const labels = Array.from(modal.querySelectorAll<HTMLElement>(".campo-modal"));
    const endpointLabel = labels.find((l) => l.textContent?.includes("Endpoint"));
    const chaveLabel = labels.find((l) => l.textContent?.includes("Chave de API"));
    expect(endpointLabel?.hidden).toBe(true);
    expect(chaveLabel?.hidden).toBe(true);
    expect(modal.querySelector(".qr-modal-busca")?.closest("[hidden]")).toBeTruthy();

    // Yolo, enxuto, C11 e detecção visíveis
    expect(modal.textContent).toContain("Rodar sem pedir permissão (yolo)");
    expect(modal.textContent).toContain("Modo enxuto");
    expect(modal.textContent).toContain("poder completo");
    expect(modal.textContent).toContain("Encontrado no PC: Claude Code 2.1.301");
  });

  it("Codex/OpenCode: tarefas longas travada e marcada, aviso visível", async () => {
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    const selects = Array.from(raiz.querySelectorAll<HTMLSelectElement>("select"));
    const tipoSel = selects.find((s) => Array.from(s.options).some((o) => o.value === "cli-codex"));
    tipoSel!.value = "cli-codex";
    tipoSel!.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));

    const modal = raiz.querySelector(".modal")!;
    const checkboxes = Array.from(modal.querySelectorAll<HTMLInputElement>("input[type='checkbox']"));
    const delegadaChk = checkboxes.find((c) => c.parentElement?.textContent?.includes("delegadas"));
    expect(delegadaChk).toBeTruthy();
    expect(delegadaChk!.checked).toBe(true);
    expect(delegadaChk!.disabled).toBe(true);
    expect(modal.textContent).toContain("serve só para tarefas longas");
  });

  it("CLI não encontrada: mostra aviso e Testar recusa", async () => {
    mockDetectarClis.mockResolvedValue([]);
    const raiz = criarRaiz();
    const aba = new AbaModelos(raiz, criarDeps());
    await aba.carregar();

    const btnAdd = Array.from(raiz.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Adicionar provedor");
    btnAdd!.click();
    await new Promise((r) => setTimeout(r, 50));

    const selects = Array.from(raiz.querySelectorAll<HTMLSelectElement>("select"));
    const tipoSel = selects.find((s) => Array.from(s.options).some((o) => o.value === "cli-claude"));
    tipoSel!.value = "cli-claude";
    tipoSel!.dispatchEvent(new Event("change"));
    await new Promise((r) => setTimeout(r, 50));

    const modal = raiz.querySelector(".modal")!;
    expect(modal.textContent).toContain("Não encontrado neste PC");

    // Preencher nome e modelo para poder clicar Testar
    const inputs = Array.from(modal.querySelectorAll<HTMLInputElement>("input"));
    const nomeInput = inputs.find((i) => i.placeholder?.includes("Nome"));
    if (nomeInput) nomeInput.value = "Claude CLI";

    const btnTestar = Array.from(modal.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent === "Testar");
    expect(btnTestar).toBeTruthy();
    btnTestar!.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(modal.textContent).toContain("não encontrada neste PC");
  });

  it("LM Studio já cadastrado não volta como sugestão de instalação (bug do id x tipo)", async () => {
    const lmstudio = {
      id: "lmstudio", nome: "LM Studio", descricao: "Servidor local", comando: ["winget"],
      fonte: "https://lmstudio.ai/download", tipo_provedor: "lmstudio", url_base: "http://127.0.0.1:1234/v1",
      tamanho_mb: null, manual: false, instalado: false, login: "dispensado", estado: "aguardando", linhas: [],
    };
    const ollama = { ...lmstudio, id: "ollama", nome: "Ollama", tipo_provedor: "ollama", url_base: "http://127.0.0.1:11434/v1" };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith("/instalaveis") ? { itens: [lmstudio, ollama] } : [],
    ))));
    // Cadastro pelo modal: o id nasce do nome ("LM Studio" -> "lm-studio"), não do id do instalável.
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "lm-studio", nome: "LM Studio", tipo: "lmstudio", url_base: "http://localhost:1234/v1", modelo: "modelo-ficticio" }],
    };
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps()).carregar();
    const sugestoes = await vi.waitFor(() => {
      const s = raiz.querySelector<HTMLElement>(".nucleo-instalar");
      expect(s?.querySelector('[data-id="instalar-ollama"]')).toBeTruthy();
      return s!;
    });
    expect(sugestoes.querySelector('[data-id="instalar-lmstudio"]')).toBeNull();
    expect(sugestoes.textContent).not.toContain("LM Studio");
  });

  it("disposição em blocos: em uso agora, cadastrados, instalar e avançado recolhido", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith("/instalaveis") ? { itens: [] } : [],
    ))));
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps()).carregar();
    await vi.waitFor(() => expect(raiz.querySelector(".nucleo-instalar .cards-vazio")).toBeTruthy());
    const legendas = [...raiz.querySelectorAll(":scope > fieldset > legend")].map(l => l.textContent);
    expect(legendas).toEqual(["Em uso agora", "Provedores cadastrados", "Instalar ou conectar"]);
    const avancado = raiz.querySelector<HTMLDetailsElement>(":scope > details.nucleo-avancado")!;
    expect(avancado.open).toBe(false);
    expect(avancado.querySelector("summary")?.textContent).toContain("Opções avançadas");
    expect(avancado.querySelector('[data-id="__oj__"]')).toBeTruthy();
    expect(raiz.textContent).not.toContain("Quem responde");
  });

  it("em uso agora mostra o provedor ativo, o modelo e a reserva", async () => {
    cfgEmMemoria = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "lm", nome: "LM Studio", tipo: "lmstudio", url_base: "http://localhost:1234/v1", modelo: "modelo-a" },
        { id: "b", nome: "Servidor B", tipo: "ollama", url_base: "http://localhost:11434/v1", modelo: "modelo-b" },
      ],
      ativo: "lm",
      reserva: "b",
    };
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps({ config: { ...configEmMemoria } })).carregar();
    const agora = raiz.querySelector<HTMLElement>(".nucleo-agora")!;
    expect(agora.textContent).toContain("LM Studio");
    expect(agora.textContent).toContain("modelo-a");
    expect(agora.textContent).toContain("Reserva: Servidor B");
    expect(agora.textContent).not.toContain("OpenJarvis");
  });

  it("em uso agora com OpenJarvis mostra o estado dele; sem escolha, orienta", async () => {
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps({
      config: { ...CONFIG_PADRAO, cerebro: "openjarvis" },
      criarOj: () => ({ modelos: async () => { throw new Error("fora"); } }) as any,
    })).carregar();
    expect(raiz.querySelector(".nucleo-agora")?.textContent).toContain("OpenJarvis");
    expect(raiz.querySelector(".nucleo-agora")?.textContent).toContain("Fora do ar");

    const raiz2 = criarRaiz();
    await new AbaModelos(raiz2, criarDeps({ config: { ...CONFIG_PADRAO, cerebro: "proprio" } })).carregar();
    expect(raiz2.querySelector(".nucleo-agora")?.textContent).toContain("Nenhum provedor escolhido");
  });

  it("avançado aberto continua aberto depois de uma ação que redesenha a aba", async () => {
    configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
    const raiz = criarRaiz();
    await new AbaModelos(raiz, criarDeps({ config: { ...configEmMemoria } })).carregar();
    const avancado = raiz.querySelector<HTMLDetailsElement>("details.nucleo-avancado")!;
    avancado.open = true;
    avancado.dispatchEvent(new Event("toggle"));
    [...raiz.querySelectorAll<HTMLButtonElement>('[data-id="__oj__"] button')].find(b => b.textContent === "Usar este")!.click();
    await vi.waitFor(() => expect(configEmMemoria.cerebro).toBe("openjarvis"));
    await vi.waitFor(() => expect(raiz.querySelector(".nucleo-agora")?.textContent).toContain("OpenJarvis"));
    expect(raiz.querySelector<HTMLDetailsElement>("details.nucleo-avancado")?.open).toBe(true);
  });

  it("reabrir a aba reconsulta o status da ponte e atualiza o aviso sem recarregar a janela", async () => {
    let ponteOk = true;
    const raiz = criarRaiz();
    const deps = criarDeps({ statusPonte: async () => (ponteOk ? ({ ok: true, modo: "ligado" } as any) : null) });
    const aba = new AbaModelos(raiz, deps);

    // Primeira carga: ponte OK → sem aviso
    await aba.carregar();
    expect(raiz.querySelector(".qr-aviso-ponte")).toBeNull();

    // Ponte cai e aba é reaberta (carregar novamente)
    ponteOk = false;
    await aba.carregar();
    expect(raiz.querySelector(".qr-aviso-ponte")?.textContent).toContain("Os serviços do Vard estão desligados");

    // Ponte volta e aba é reaberta novamente
    ponteOk = true;
    await aba.carregar();
    expect(raiz.querySelector(".qr-aviso-ponte")).toBeNull();
  });

  describe("modal Editar OpenJarvis (endereços saíram da aba Geral)", () => {
    const abrirEditar = async (deps: DepsQuemResponde) => {
      const raiz = criarRaiz();
      await new AbaModelos(raiz, deps).carregar();
      [...raiz.querySelectorAll<HTMLButtonElement>('[data-id="__oj__"] button')].find((b) => b.textContent === "Editar")!.click();
      const modal = raiz.querySelector<HTMLElement>(".modal")!;
      const url = modal.querySelector<HTMLInputElement>("#nucleo-oj-url")!;
      const gui = modal.querySelector<HTMLInputElement>("#nucleo-oj-gui")!;
      const salvar = [...modal.querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((b) => b.textContent === "Salvar")!;
      return { raiz, modal, url, gui, salvar };
    };

    it("mostra endereço, interface de texto e modelo com os valores atuais", async () => {
      configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio", openjarvis_url: "http://127.0.0.1:8100", gui_url: "http://127.0.0.1:5200" };
      const { modal, url, gui } = await abrirEditar(criarDeps({ config: { ...configEmMemoria } }));
      expect(modal.querySelector(".modal-titulo")?.textContent).toBe("Editar OpenJarvis");
      const rotulos = [...modal.querySelectorAll(".campo-modal-rotulo")].map((r) => r.textContent);
      expect(rotulos).toEqual(["Endereço", "Interface de texto", "Modelo do OpenJarvis"]);
      expect(url.value).toBe("http://127.0.0.1:8100");
      expect(gui.value).toBe("http://127.0.0.1:5200");
      expect(modal.querySelector("select")).toBeTruthy();
    });

    it("Salvar grava os dois endereços, atualiza a config viva e o card, e avisa que vale após reiniciar", async () => {
      configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
      const dizer = vi.fn();
      const deps = criarDeps({ config: { ...configEmMemoria }, dizer });
      const { raiz, url, gui, salvar } = await abrirEditar(deps);
      url.value = "  http://127.0.0.1:8300/  ";
      gui.value = "http://localhost:5300";
      salvar.click();
      await vi.waitFor(() => expect(raiz.querySelector(".modal")).toBeNull());
      expect(configEmMemoria.openjarvis_url).toBe("http://127.0.0.1:8300/");
      expect(configEmMemoria.gui_url).toBe("http://localhost:5300");
      expect(deps.config.openjarvis_url).toBe("http://127.0.0.1:8300/");
      expect(deps.config.gui_url).toBe("http://localhost:5300");
      expect(raiz.querySelector('[data-id="__oj__"]')?.textContent).toContain("http://127.0.0.1:8300/");
      expect(dizer).toHaveBeenCalledWith(expect.stringContaining("Reinicie o Vard para aplicar: endereços"), false);
    });

    it("só o modelo mudou: grava sem pedir reinício", async () => {
      configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
      const dizer = vi.fn();
      const deps = criarDeps({ config: { ...configEmMemoria }, dizer });
      const { raiz, modal, salvar } = await abrirEditar(deps);
      modal.querySelector<HTMLSelectElement>("select")!.value = "modelo-oj-2";
      salvar.click();
      await vi.waitFor(() => expect(raiz.querySelector(".modal")).toBeNull());
      expect(configEmMemoria.modelo).toBe("modelo-oj-2");
      expect(configEmMemoria.openjarvis_url).toBe(CONFIG_PADRAO.openjarvis_url);
      expect(dizer).not.toHaveBeenCalledWith(expect.stringContaining("Reinicie"), expect.anything());
    });

    it("endereço vazio ou que não é http(s) não salva e avisa no modal", async () => {
      configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
      const deps = criarDeps({ config: { ...configEmMemoria } });
      const { modal, url, gui, salvar } = await abrirEditar(deps);
      url.value = "   ";
      salvar.click();
      await vi.waitFor(() => expect(modal.querySelector(".modal-aviso")?.textContent).toContain("Preencha o endereço"));
      expect(modal.isConnected).toBe(true);
      url.value = "http://127.0.0.1:8000";
      gui.value = "pasta/local";
      salvar.click();
      await vi.waitFor(() => expect(modal.querySelector(".modal-aviso")?.textContent).toContain("Interface de texto"));
      expect(modal.isConnected).toBe(true);
      expect(configEmMemoria.openjarvis_url).toBe(CONFIG_PADRAO.openjarvis_url);
      expect(configEmMemoria.gui_url).toBe(CONFIG_PADRAO.gui_url);
      expect(deps.config.gui_url).toBe(CONFIG_PADRAO.gui_url);
    });

    it("endereço fora da máquina marca o campo e salva com aviso, como o resto do painel", async () => {
      configEmMemoria = { ...CONFIG_PADRAO, cerebro: "proprio" };
      const dizer = vi.fn();
      const { raiz, url, salvar } = await abrirEditar(criarDeps({ config: { ...configEmMemoria }, dizer }));
      expect(url.classList.contains("aviso")).toBe(false);
      url.value = "http://servidor.exemplo:8000";
      url.dispatchEvent(new Event("input"));
      expect(url.classList.contains("aviso")).toBe(true);
      salvar.click();
      await vi.waitFor(() => expect(raiz.querySelector(".modal")).toBeNull());
      expect(configEmMemoria.openjarvis_url).toBe("http://servidor.exemplo:8000");
      expect(dizer).toHaveBeenCalledWith(expect.stringContaining("OpenJarvis: o endereço não é 127.0.0.1 nem localhost"), true);
    });
  });
});
