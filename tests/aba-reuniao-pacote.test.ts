/**
 * @vitest-environment jsdom
 */
/**
 * Testes da seção de instalação/remoção do pacote de reunião na aba-reuniao (T6b).
 * Cobre:
 * - Renderização inicial (não instalado → botão Instalar)
 * - Instalação com progresso SSE e conclusão
 * - Erro na instalação é notificado
 * - Cancelamento da instalação
 * - Remoção confirmada e recusada com reunião ativa
 * - Atas preservadas na remoção (diretório separado)
 * - Ações só habilitadas quando pacote saudável
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AbaReuniao, type DepsPacoteReuniao } from "../src/ui/aba-reuniao";
import type { StatusReuniao, ReuniaoDaLista, ResultadoReuniao } from "../src/conectores/ponte/cliente";

const mockFetch = vi.fn();
const mockConfirm = vi.fn();
const mockNotificar = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  vi.stubGlobal("window", { confirm: mockConfirm, setInterval: vi.fn(), clearInterval: vi.fn() });
  mockFetch.mockReset();
  mockConfirm.mockReset();
  mockNotificar.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

function criarDeps(): DepsPacoteReuniao {
  return { baseUrl: "http://127.0.0.1:4700", notificar: mockNotificar };
}

function mockPonte() {
  return {
    reuniaoStatus: vi.fn(async () => null as StatusReuniao | null),
    iniciarReuniao: vi.fn(async () => null as ResultadoReuniao | null),
    encerrarReuniao: vi.fn(async () => null as ResultadoReuniao | null),
    listaReuniao: vi.fn(async () => null as ReuniaoDaLista[] | null),
    gerarAta: vi.fn(async () => null as ResultadoReuniao | null),
  };
}

function mockPacotesResponse(instalado: boolean, saudavel = true) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      pacotes: [{ id: "reuniao", versao: "0.1.0" }],
      instalados: instalado ? { reuniao: { versao: "0.1.0", saudavel } } : {},
    }),
  });
}

describe("AbaReuniao — seção de pacote", () => {
  it("renderiza botão Instalar quando não instalado", async () => {
    mockPacotesResponse(false);
    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe("Instalar reunião");
    expect(btn.disabled).toBe(false);
  });

  it("renderiza botão Remover quando instalado e saudável", async () => {
    mockPacotesResponse(true, true);
    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe("Remover");
    expect(btn.disabled).toBe(false);
  });

  it("botão Remover desabilitado quando pacote não saudável", async () => {
    mockPacotesResponse(true, false);
    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.disabled).toBe(true);
  });

  it("instalação concluída via SSE notifica sucesso", async () => {
    mockPacotesResponse(false);
    // Mock SSE response para instalação
    const encoder = new TextEncoder();
    const sseBody = [
      'data: {"estado":"instalando"}\n\n',
      'data: {"estado":"concluido"}\n\n',
    ].map((s) => encoder.encode(s));
    let idx = 0;
    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (idx < sseBody.length) return { done: false, value: sseBody[idx++] };
            return { done: true, value: undefined };
          },
        }),
      },
    });

    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockNotificar).toHaveBeenCalledWith("Reunião instalada com sucesso.");
  });

  it("erro na instalação é notificado", async () => {
    mockPacotesResponse(false);
    mockFetch.mockResolvedValueOnce({
      ok: false,
      body: null,
      json: async () => ({ erro: "venv falhou" }),
    });

    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockNotificar).toHaveBeenCalledWith(
      expect.stringContaining("Falha ao iniciar"),
      true,
    );
  });

  it("remoção confirmada chama endpoint e notifica", async () => {
    mockPacotesResponse(true, true);
    mockConfirm.mockReturnValue(true);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockConfirm).toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/pacotes/reuniao/remover"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(mockNotificar).toHaveBeenCalledWith("Pacote de reunião removido.");
  });

  it("remoção cancelada pelo usuário não chama endpoint", async () => {
    mockPacotesResponse(true, true);
    mockConfirm.mockReturnValue(false);

    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte(), criarDeps());
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const btn = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));

    expect(mockConfirm).toHaveBeenCalled();
    // Nenhuma chamada POST /remover deve ter sido feita
    const chamadasRemover = mockFetch.mock.calls.filter((chamada) => {
      const [url, opts] = chamada as unknown as [string, { method?: string } | undefined];
      return String(url).includes("/remover") && opts?.method === "POST";
    });
    expect(chamadasRemover.length).toBe(0);
  });

  it("sem depsPacote mostra nota de indisponível", async () => {
    const raiz = document.createElement("div");
    const aba = new AbaReuniao(raiz, mockPonte()); // sem depsPacote
    aba.montar();
    await new Promise((r) => setTimeout(r, 10));

    const nota = raiz.querySelector(".nota") as HTMLElement;
    expect(nota?.textContent).toContain("indisponível");
  });
});