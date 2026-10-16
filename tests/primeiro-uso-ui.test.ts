import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch para rotas HTTP do núcleo
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("primeiro-uso UI", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    document.body.innerHTML = "";
  });

  it("monta assistente com IDs DOM estáveis quando concluido=false", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "nome", concluido: false, pendencias: [] }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    document.body.appendChild(raiz);
    const limpar = await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(limpar).not.toBeNull();
    expect(raiz.querySelector("#primeiro-uso-etapa")).not.toBeNull();
    expect(raiz.querySelector("#primeiro-uso-proximo")).not.toBeNull();
    limpar?.();
    expect(raiz.querySelector("#primeiro-uso-etapa")).toBeNull();
  });

  it("não monta assistente quando concluido=true (instalação existente)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    const limpar = await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(limpar).toBeNull();
    expect(raiz.querySelector("#primeiro-uso-etapa")).toBeNull();
  });

  it("não monta assistente quando ponte ausente", async () => {
    fetchMock.mockRejectedValue(new Error("rede"));
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    const limpar = await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(limpar).toBeNull();
  });

  it("renderiza campo de nome na etapa nome", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "nome", concluido: false, pendencias: [], nome_chamada: "" }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(raiz.querySelector("#primeiro-uso-nome-input")).not.toBeNull();
  });

  it("renderiza resumo na etapa resumo com ID primeiro-uso-resumo", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ schema: 1, etapa: "resumo", concluido: false, pendencias: [] }),
    });
    const { montarAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(raiz.querySelector("#primeiro-uso-resumo")).not.toBeNull();
  });

  it("reabrirAssistentePrimeiroUso chama POST /primeiro-uso/reabrir e monta", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }) });
    const { reabrirAssistentePrimeiroUso } = await import("../src/ui/primeiro-uso");
    const raiz = document.createElement("div");
    const limpar = await reabrirAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:4700" });
    expect(limpar).not.toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/primeiro-uso/reabrir"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});