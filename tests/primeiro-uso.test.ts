import { describe, it, expect, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

// Mock fetch para rotas HTTP do núcleo
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("primeiro-uso estado e fluxo", () => {
  beforeEach(() => {
    invoke.mockReset();
    fetchMock.mockReset();
  });

  describe("lerEstadoPrimeiroUso", () => {
    it("devolve estado inicial quando não há progresso salvo", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }),
      });
      const { lerEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await lerEstadoPrimeiroUso("http://127.0.0.1:4700");
      expect(estado).not.toBeNull();
      expect(estado!.etapa).toBe("importar");
      expect(estado!.concluido).toBe(false);
    });

    it("retoma etapa salva após reinício", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "nome", concluido: false, pendencias: [], nome_chamada: "Aurora" }),
      });
      const { lerEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await lerEstadoPrimeiroUso("http://127.0.0.1:4700");
      expect(estado!.etapa).toBe("nome");
      expect(estado!.nome_chamada).toBe("Aurora");
    });

    it("instalação preexistente devolve concluido=true", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
      });
      const { lerEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await lerEstadoPrimeiroUso("http://127.0.0.1:4700");
      expect(estado!.concluido).toBe(true);
    });

    it("ponte ausente devolve null sem erro", async () => {
      fetchMock.mockRejectedValue(new Error("rede"));
      const { lerEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await lerEstadoPrimeiroUso("http://127.0.0.1:4700");
      expect(estado).toBeNull();
    });
  });

  describe("atualizarEstadoPrimeiroUso", () => {
    it("avança etapa e preserva escolhas anteriores", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "cerebro", concluido: false, pendencias: [], nome_chamada: "Aurora", cerebro_id: "local" }),
      });
      const { atualizarEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await atualizarEstadoPrimeiroUso("http://127.0.0.1:4700", { etapa: "cerebro", cerebro_id: "local" });
      expect(estado).not.toBeNull();
      expect(estado!.etapa).toBe("cerebro");
      expect(estado!.nome_chamada).toBe("Aurora");
    });

    it("nome vazio é recusado com erro nome_vazio", async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ erro: "nome_vazio" }),
      });
      const { atualizarEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await atualizarEstadoPrimeiroUso("http://127.0.0.1:4700", { nome_chamada: "   " });
      expect(estado).toBeNull();
    });

    it("pular preserva pendência", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "voz", concluido: false, pendencias: ["microfone_nao_testado"] }),
      });
      const { atualizarEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await atualizarEstadoPrimeiroUso("http://127.0.0.1:4700", { etapa: "voz", pendencias: ["microfone_nao_testado"] });
      expect(estado!.pendencias).toContain("microfone_nao_testado");
    });

    it("concluir marca concluido=true e não reabre sozinho", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
      });
      const { atualizarEstadoPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await atualizarEstadoPrimeiroUso("http://127.0.0.1:4700", { concluido: true });
      expect(estado!.concluido).toBe(true);
    });
  });

  describe("reabrirPrimeiroUso", () => {
    it("reabre assistente sem apagar escolhas salvas", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "resumo", concluido: false, pendencias: [], nome_chamada: "Aurora" }),
      });
      const { reabrirPrimeiroUso } = await import("../src/config/primeiro-uso");
      const estado = await reabrirPrimeiroUso("http://127.0.0.1:4700");
      expect(estado).not.toBeNull();
      expect(estado!.concluido).toBe(false);
      expect(estado!.nome_chamada).toBe("Aurora");
    });
  });

  describe("deveMostrarAssistente", () => {
    it("true quando concluido=false", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }),
      });
      const { deveMostrarAssistente } = await import("../src/config/primeiro-uso");
      const mostrar = await deveMostrarAssistente("http://127.0.0.1:4700");
      expect(mostrar).toBe(true);
    });

    it("false quando concluido=true (instalação preexistente)", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
      });
      const { deveMostrarAssistente } = await import("../src/config/primeiro-uso");
      const mostrar = await deveMostrarAssistente("http://127.0.0.1:4700");
      expect(mostrar).toBe(false);
    });

    it("false quando ponte ausente (não bloqueia app)", async () => {
      fetchMock.mockRejectedValue(new Error("rede"));
      const { deveMostrarAssistente } = await import("../src/config/primeiro-uso");
      const mostrar = await deveMostrarAssistente("http://127.0.0.1:4700");
      expect(mostrar).toBe(false);
    });
  });
});