/** Testes da etapa 'cerebro' do assistente de primeiro uso (T3).
 * Cobre: montagem da UI, escolha entre OpenJarvis/próprio, teste de conexão
 * com dublê HTTP, salvamento da escolha e limpeza de recursos.
 * Nenhum teste real contra LM Studio ou API externa. */
vi.mock("../src/config/paineis", async (original) => {
  const mod = await original<typeof import("../src/config/paineis")>();
  return { ...mod, lerPaineis: vi.fn().mockResolvedValue(mod.PAINEIS_PADRAO), gravarPaineis: vi.fn().mockResolvedValue(undefined) };
});
vi.mock("../src/config/config", () => ({ atualizarConfig: vi.fn().mockResolvedValue(undefined) }));

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { montarEtapaCerebro, type DepsEtapaCerebro } from "../src/ui/primeiro-uso-cerebro";
import type { EstadoPrimeiroUso } from "../src/config/primeiro-uso";

function estadoInicial(overrides: Partial<EstadoPrimeiroUso> = {}): EstadoPrimeiroUso {
  return {
    schema: 1,
    etapa: "cerebro",
    concluido: false,
    pendencias: [],
    ...overrides,
  };
}

function depsPadrao(overrides: Partial<DepsEtapaCerebro> = {}): DepsEtapaCerebro & { aoSalvarSpy: ReturnType<typeof vi.fn> } {
  const aoSalvarSpy = vi.fn();
  return {
    ponteUrl: "http://127.0.0.1:9999",
    estadoInicial: estadoInicial(),
    aoSalvar: aoSalvarSpy,
    ...overrides,
    aoSalvarSpy,
  };
}

describe("montarEtapaCerebro", () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    // Dublê global do fetch para evitar chamadas reais
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    container.remove();
  });

  it("renderiza radio buttons de escolha do cérebro", () => {
    const deps = depsPadrao();
    montarEtapaCerebro(container, deps);

    const radios = container.querySelectorAll<HTMLInputElement>('input[name="cerebro-escolha"]');
    expect(radios.length).toBe(2);
    const valores = Array.from(radios).map((r) => r.value);
    expect(valores).toContain("openjarvis");
    expect(valores).toContain("proprio");
  });

  it("seleciona OpenJarvis por padrão quando cerebro_id não está definido", () => {
    const deps = depsPadrao();
    montarEtapaCerebro(container, deps);

    const ojRadio = container.querySelector<HTMLInputElement>('input[value="openjarvis"]');
    expect(ojRadio?.checked).toBe(true);
    // Formulário próprio não deve aparecer
    expect(container.querySelector("#cerebro-proprio-form")).toBeNull();
  });

  it("mostra formulário do cérebro próprio quando escolhido", async () => {
    const deps = depsPadrao({
      estadoInicial: estadoInicial({ cerebro_id: "proprio" }),
    });
    montarEtapaCerebro(container, deps);

    // Aguarda renderização
    await new Promise((r) => setTimeout(r, 0));

    const formProprio = container.querySelector("#cerebro-proprio-form");
    expect(formProprio).not.toBeNull();
    expect(container.querySelector('select')).not.toBeNull();
    expect(container.querySelector('input[type="url"]')).not.toBeNull();
  });

  it("chama POST /primeiro-uso/cerebro/testar ao clicar em Testar", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, detalhe: "resposta_recebida", primeiro_token_ms: 42 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const deps = depsPadrao({
      estadoInicial: estadoInicial({ cerebro_id: "proprio" }),
    });
    montarEtapaCerebro(container, deps);

    // Preenche campos obrigatórios
    await new Promise(r => setTimeout(r, 0));
    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://provedor.invalid";
    modeloInput.value = "llama-3";

    // Clica em Testar
    const btnTestar = container.querySelector("button") as HTMLButtonElement;
    btnTestar.click();

    await new Promise((r) => setTimeout(r, 50));

    expect(mockFetch).toHaveBeenCalledWith(
      "http://127.0.0.1:9999/primeiro-uso/cerebro/testar",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("habilita botão Salvar após teste bem-sucedido", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, detalhe: "resposta_recebida", primeiro_token_ms: 42 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const deps = depsPadrao({
      estadoInicial: estadoInicial({ cerebro_id: "proprio" }),
    });
    montarEtapaCerebro(container, deps);

    await new Promise(r => setTimeout(r, 0));
    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://provedor.invalid";
    modeloInput.value = "llama-3";

    const botoes = container.querySelectorAll("button");
    const btnTestar = botoes[0] as HTMLButtonElement;
    const btnSalvar = botoes[1] as HTMLButtonElement;

    expect(btnSalvar.disabled).toBe(true);

    btnTestar.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(btnSalvar.disabled).toBe(false);
  });

  it("chama atualizarEstadoPrimeiroUso ao salvar e dispara aoSalvar", async () => {
    const novoEstado = estadoInicial({ cerebro_id: "proprio", etapa: "voz" });
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true, detalhe: "resposta_recebida", primeiro_token_ms: 42 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => novoEstado,
      });
    vi.stubGlobal("fetch", mockFetch);

    const deps = depsPadrao({
      estadoInicial: estadoInicial({ cerebro_id: "proprio" }),
    });
    montarEtapaCerebro(container, deps);

    await new Promise(r => setTimeout(r, 0));
    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://provedor.invalid";
    modeloInput.value = "llama-3";

    const botoes = container.querySelectorAll("button");
    const btnTestar = botoes[0] as HTMLButtonElement;
    const btnSalvar = botoes[1] as HTMLButtonElement;

    btnTestar.click();
    await new Promise((r) => setTimeout(r, 50));

    btnSalvar.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(deps.aoSalvarSpy).toHaveBeenCalledWith(novoEstado);
  });

  it("limpa recursos ao chamar função de retorno", () => {
    const deps = depsPadrao();
    const limpar = montarEtapaCerebro(container, deps);

    expect(container.innerHTML).not.toBe("");
    limpar();
    expect(container.innerHTML).toBe("");
  });

  it("não mostra formulário próprio quando OpenJarvis está selecionado", () => {
    const deps = depsPadrao({
      estadoInicial: estadoInicial({ cerebro_id: "openjarvis" }),
    });
    montarEtapaCerebro(container, deps);

    expect(container.querySelector("#cerebro-proprio-form")).toBeNull();
    // Botão Salvar deve estar presente mesmo sem formulário
    const btnSalvar = container.querySelector("button");
    expect(btnSalvar).not.toBeNull();
  });
});
import { montarAssistentePrimeiroUso } from "../src/ui/primeiro-uso";

describe("integração da etapa cérebro", () => {
  afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = ""; });
  it("monta pelo deps.cerebro e pular persiste pendência", async () => {
    const inicial = estadoInicial();
    const fetch = vi.fn().mockImplementation(async (_url, opcoes) => ({ ok: true,
      json: async () => opcoes?.method === "PUT" ? { ...inicial, ...JSON.parse(opcoes.body) } : inicial }));
    vi.stubGlobal("fetch", fetch);
    const limpar = await montarAssistentePrimeiroUso(document.body, { ponteUrl: "http://nucleo.invalid", cerebro: {} });
    expect(document.querySelector('[name="cerebro-escolha"]')).not.toBeNull();
    document.querySelector<HTMLButtonElement>("#cerebro-pular")!.click();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledWith("http://nucleo.invalid/primeiro-uso",
      expect.objectContaining({ body: expect.stringContaining("cerebro_nao_testado") })));
    limpar?.();
    expect(document.querySelector("#primeiro-uso-etapa")).toBeNull();
  });

  it("próximo sem teste preserva a pendência crítica", async () => {
    const inicial = estadoInicial();
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => inicial });
    vi.stubGlobal("fetch", fetch);
    const limpar = await montarAssistentePrimeiroUso(document.body, { ponteUrl: "http://nucleo.invalid", cerebro: {} });
    document.querySelector<HTMLButtonElement>("#primeiro-uso-proximo")!.click();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledWith("http://nucleo.invalid/primeiro-uso",
      expect.objectContaining({ body: expect.stringContaining("cerebro_nao_testado") })));
    limpar?.();
  });
});

import { PAINEIS_PADRAO, gravarPaineis } from "../src/config/paineis";
import { atualizarConfig } from "../src/config/config";

describe("escolha manual e falhas", () => {
  let container: HTMLDivElement;
  let limpar: (() => void) | undefined;
  beforeEach(() => { container = document.createElement("div"); document.body.append(container); vi.clearAllMocks(); });
  afterEach(() => { limpar?.(); container.remove(); vi.unstubAllGlobals(); });
  async function montar() {
    limpar = montarEtapaCerebro(container, depsPadrao({ estadoInicial: estadoInicial({ cerebro_id: "proprio" }) }));
    await new Promise(r => setTimeout(r, 0));
    container.querySelector<HTMLInputElement>('input[type="url"]')!.value = "http://provedor.invalid";
    container.querySelector<HTMLInputElement>('input[type="text"]')!.value = "novo";
  }
  it("lista baixados apenas ao pedir e preserva seleção", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, modelos: [
      { id: "antigo", instancias: [{ id: "residente" }] }, { id: "novo", instancias: [] }] }) });
    vi.stubGlobal("fetch", fetch); await montar();
    expect(fetch).not.toHaveBeenCalled();
    container.querySelector<HTMLButtonElement>("#cerebro-listar")!.click();
    await vi.waitFor(() => expect(container.querySelector("#cerebro-modelos")!.textContent).toContain("novo (baixado)"));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toContain("/modelos");
  });
  it("mudança de endpoint invalida teste e resposta antiga não libera salvar", async () => {
    let resolver!: (v: unknown) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(r => { resolver = r; })));
    await montar();
    container.querySelector<HTMLButtonElement>("button")!.click();
    await new Promise(r => setTimeout(r, 0));
    const input = container.querySelector<HTMLInputElement>('input[type="url"]')!;
    input.value = "http://outro.invalid"; input.dispatchEvent(new Event("input"));
    resolver({ ok: true, json: async () => ({ ok: true, primeiro_token_ms: 1 }) });
    await new Promise(r => setTimeout(r, 0));
    expect(container.querySelectorAll<HTMLButtonElement>("button")[1].disabled).toBe(true);
  });
  it("falha permite tentar novamente e pular sem alterar provedor ativo", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: false, detalhe: "conexao" }) });
    vi.stubGlobal("fetch", fetch); await montar();
    const b = container.querySelector<HTMLButtonElement>("button")!; b.click();
    await vi.waitFor(() => expect(container.textContent).toContain("Falha: conexao"));
    expect(b.disabled).toBe(false);
    expect(container.querySelectorAll<HTMLButtonElement>("button")[1].disabled).toBe(true);
    container.querySelector<HTMLButtonElement>("#cerebro-pular")!.click();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(gravarPaineis).not.toHaveBeenCalled(); expect(atualizarConfig).not.toHaveBeenCalled();
  });
  it("retoma provedor escolhido e salva modelo sem substituir reserva nem agentes", async () => {
    const cfg = structuredClone(PAINEIS_PADRAO);
    cfg.provedores = [{ id: "cpu", nome: "Local CPU", tipo: "lmstudio", url_base: "http://cpu.invalid", modelo: "antigo" },
      { id: "externo", nome: "Direto", tipo: "anthropic", url_base: "https://externo.invalid", modelo: "remoto" }];
    cfg.ativo = "cpu"; cfg.reserva = "externo";
    const gravar = vi.fn().mockResolvedValue(undefined);
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, primeiro_token_ms: 2 }) });
    vi.stubGlobal("fetch", fetch);
    limpar = montarEtapaCerebro(container, depsPadrao({ estadoInicial: estadoInicial({ cerebro_id: "proprio" }),
      lerProvedores: async () => cfg, gravarProvedores: gravar }));
    await new Promise(r => setTimeout(r, 0));
    expect(container.querySelector<HTMLInputElement>('input[type="url"]')!.value).toBe("http://cpu.invalid");
    const modelo = container.querySelector<HTMLInputElement>('input[type="text"]')!;
    modelo.value = "novo"; modelo.dispatchEvent(new Event("input"));
    container.querySelector<HTMLButtonElement>("button")!.click();
    await vi.waitFor(() => expect(container.querySelectorAll<HTMLButtonElement>("button")[1].disabled).toBe(false));
    container.querySelectorAll<HTMLButtonElement>("button")[1].click();
    await vi.waitFor(() => expect(gravar).toHaveBeenCalled());
    expect(gravar.mock.calls[0][0]).toMatchObject({ ativo: "cpu", reserva: "externo", agentes: cfg.agentes });
    expect(gravar.mock.calls[0][0].provedores.find((p: { id: string }) => p.id === "externo")).toEqual(cfg.provedores[1]);
  });
  it("troca recusada não valida conexão", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: false, detalhe: "descarga_nao_confirmada" }) });
    vi.stubGlobal("fetch", fetch); await montar();
    container.querySelector<HTMLButtonElement>("#cerebro-trocar")!.click();
    await vi.waitFor(() => expect(container.textContent).toContain("descarga_nao_confirmada"));
    expect(fetch.mock.calls[0][0]).toContain("/trocar");
    expect(container.querySelectorAll<HTMLButtonElement>("button")[1].disabled).toBe(true);
  });
});
