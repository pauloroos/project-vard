import { describe, it, expect, vi, beforeEach } from "vitest";

const invokeMock = vi.fn();
const emitToMock = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invokeMock(...a) }));
vi.mock("@tauri-apps/api/event", () => ({
  emitTo: (...a: unknown[]) => emitToMock(...a),
  listen: vi.fn().mockResolvedValue(() => {}),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("assistente de primeiro uso na janela de Configurações", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    emitToMock.mockReset();
    fetchMock.mockReset();
    document.body.innerHTML = "";
  });

  it("widget NÃO monta assistente no #app quando deveMostrar=true (apenas verifica)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }),
    });
    const { abrirAssistenteSeNecessario } = await import("../src/ui/primeiro-uso-hospedeiro");
    const raiz = document.createElement("div");
    const resultado = await abrirAssistenteSeNecessario(
      {
        ponteUrl: "http://127.0.0.1:4700",
        salvarNome: vi.fn(),
        audio: {
          config: {} as never,
          transcrever: vi.fn(),
          suspenderEscuta: vi.fn(),
          salvar: vi.fn(),
        },
      },
      { raiz, apenasVerificar: true },
    );
    // Retorna true (deve abrir) mas NÃO monta nada no DOM
    expect(resultado).toBe(true);
    expect(raiz.querySelector("#primeiro-uso-etapa")).toBeNull();
    expect(raiz.childElementCount).toBe(0);
  });

  it("widget retorna false quando instalação existe (apenasVerificar)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
    });
    const { abrirAssistenteSeNecessario } = await import("../src/ui/primeiro-uso-hospedeiro");
    const resultado = await abrirAssistenteSeNecessario(
      {
        ponteUrl: "http://127.0.0.1:4700",
        salvarNome: vi.fn(),
        audio: {
          config: {} as never,
          transcrever: vi.fn(),
          suspenderEscuta: vi.fn(),
          salvar: vi.fn(),
        },
      },
      { apenasVerificar: true },
    );
    expect(resultado).toBe(false);
  });

  it("Configurações monta assistente no container próprio quando deveMostrar=true", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const container = document.createElement("div");
    container.id = "primeiro-uso-container";
    document.body.appendChild(container);
    const limpar = await montarAssistentePrimeiroUso(container, {
      ponteUrl: "http://127.0.0.1:4700",
    });
    expect(limpar).not.toBeNull();
    expect(container.querySelector("#primeiro-uso-etapa")).not.toBeNull();
    expect(container.hidden).toBe(false);
    limpar?.();
    expect(container.querySelector("#primeiro-uso-etapa")).toBeNull();
  });

  it("Configurações NÃO monta assistente quando concluido=true", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const container = document.createElement("div");
    container.id = "primeiro-uso-container";
    const limpar = await montarAssistentePrimeiroUso(container, {
      ponteUrl: "http://127.0.0.1:4700",
    });
    expect(limpar).toBeNull();
    expect(container.querySelector("#primeiro-uso-etapa")).toBeNull();
  });
});