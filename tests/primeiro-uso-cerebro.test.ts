/** Testes da etapa 'cerebro' do assistente de primeiro uso (T3).
 * Cobre: montagem da UI, escolha entre OpenJarvis/próprio, teste de conexão
 * com dublê HTTP, salvamento da escolha e limpeza de recursos.
 * Nenhum teste real contra LM Studio ou API externa. */
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
    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://localhost:1234";
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

    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://localhost:1234";
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

    const urlInput = container.querySelector('input[type="url"]') as HTMLInputElement;
    const modeloInput = container.querySelector('input[type="text"]') as HTMLInputElement;
    urlInput.value = "http://localhost:1234";
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