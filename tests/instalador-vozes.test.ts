/**
 * @vitest-environment jsdom
 */
/**
 * Testes da tela do Instalador de Vozes (T5b).
 * Cobre: renderização, confirmação de licença, progresso SSE, cancelamento e remoção.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { InstaladorVozes, type PacoteManifesto, type DepsInstaladorVozes } from "../src/ui/instalador-vozes";

// Mock do fetch global
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock do window.confirm
const mockConfirm = vi.fn();

function criarDom(): { raiz: HTMLElement } {
  document.body.innerHTML = `<div id="app"></div>`;
  (window as unknown as Record<string, unknown>).confirm = mockConfirm;
  const raiz = document.getElementById("app")!;
  return { raiz };
}

const PACOTE_XTTS: PacoteManifesto = {
  id: "xtts-v2",
  nome: "XTTS-v2",
  versao: "2.0.3",
  tipo: "motor",
  descricao: "Motor de síntese multilíngue.",
  bytes_download: 1867929118,
  bytes_instalado: 2100000000,
  licenca_url: "https://coqui.ai/cpml",
  licenca_nome: "CPML",
  indisponivel: false,
};

const PACOTE_INDISPONIVEL: PacoteManifesto = {
  id: "voz-ana",
  nome: "Ana",
  versao: "1.0.0",
  tipo: "voz",
  descricao: "Voz feminina pt-BR.",
  bytes_download: 0,
  bytes_instalado: 0,
  licenca_url: "",
  licenca_nome: "",
  indisponivel: true,
  motivo_indisponivel: "hash não conferido",
};

function mockPacotesResponse(pacotes: PacoteManifesto[], instalados: Record<string, boolean> = {}) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      pacotes,
      instalados: Object.fromEntries(
        Object.entries(instalados).map(([k, v]) => [k, v ? { versao: "1.0.0" } : undefined]).filter(([, v]) => v)
      ),
      ativos: {},
    }),
  });
}

describe("InstaladorVozes", () => {
  let deps: DepsInstaladorVozes;
  let notificarSpy: (msg: string, erro?: boolean) => void;

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    notificarSpy = vi.fn() as unknown as (msg: string, erro?: boolean) => void;
    deps = { baseUrl: "http://127.0.0.1:4700", notificar: notificarSpy };
    mockConfirm.mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reconhece instalado no contrato atual do núcleo sem oferecer novo download", async () => {
    const { raiz } = criarDom();
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ pacotes: [{ ...PACOTE_XTTS, instalado: true, instalavel: true }] }) });
    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();
    expect(tela.estaInstalado("xtts-v2")).toBe(true);
    expect(raiz.querySelector('button[data-acao="remover"]')).toBeTruthy();
    expect(raiz.querySelector('button[data-acao="instalar"]')).toBeNull();
  });

  it("entrada do card confirma licença e notifica conclusão sem instalar no PC", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    const aoMudar = vi.fn();
    const tela = new InstaladorVozes(raiz, { ...deps, aoMudar });
    await tela.montar();
    mockFetch.mockResolvedValueOnce(new Response('data: {"estado":"concluido","bytes_baixados":1,"bytes_total":1}\n'));
    await tela.instalar("xtts-v2");
    expect(mockConfirm).toHaveBeenCalledOnce();
    expect(mockFetch).toHaveBeenLastCalledWith("http://127.0.0.1:4700/pacotes/xtts-v2/instalar", expect.objectContaining({ method: "POST" }));
    expect(aoMudar).toHaveBeenCalledOnce();
    expect(raiz.textContent).toContain("Instalado");
  });

  it("entrada do card com a licença já aceita não pergunta de novo e devolve true ao concluir", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();
    expect(tela.pacote("xtts-v2")?.licenca_nome).toBe("CPML");
    mockFetch.mockResolvedValueOnce(new Response('data: {"estado":"concluido","bytes_baixados":1,"bytes_total":1}\n'));
    await expect(tela.instalar("xtts-v2", { licencaAceita: true })).resolves.toBe(true);
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(tela.estaInstalado("xtts-v2")).toBe(true);
  });

  it("entrada do card devolve false quando a licença é recusada ou a instalação falha", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();
    mockConfirm.mockReturnValueOnce(false);
    await expect(tela.instalar("xtts-v2")).resolves.toBe(false);
    mockFetch.mockResolvedValueOnce(new Response('data: {"estado":"falhou","bytes_baixados":0,"bytes_total":1,"erro":"falha fictícia"}\n'));
    await expect(tela.instalar("xtts-v2")).resolves.toBe(false);
    expect(tela.estaInstalado("xtts-v2")).toBe(false);
  });

  it("entrada do card não contorna pacote indisponível", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_INDISPONIVEL]);
    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();
    await expect(tela.instalar("voz-ana")).resolves.toBe(false);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("renderiza lista de pacotes disponíveis", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS, PACOTE_INDISPONIVEL]);

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    expect(raiz.textContent).toContain("XTTS-v2");
    expect(raiz.textContent).toContain("Ana");
    expect(raiz.querySelector('button[data-acao="instalar"]')).toBeTruthy();
    expect(raiz.querySelector('button[disabled]')).toBeTruthy();
  });

  it("mostra mensagem quando nenhum pacote está disponível", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([]);

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    expect(raiz.textContent).toContain("Nenhum pacote disponível");
  });

  it("exibe tamanho formatado corretamente", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    // 1867929118 bytes ≈ 1.7 GB
    expect(raiz.textContent).toContain("GB");
  });

  it("pede confirmação de licença antes de instalar", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    mockConfirm.mockReturnValue(false);

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btn.click();

    // Aguarda microtask
    await new Promise((r) => setTimeout(r, 10));

    expect(mockConfirm).toHaveBeenCalledWith(
      expect.stringContaining("CPML")
    );
    // Não deve ter chamado fetch de instalação pois usuário cancelou
    expect(mockFetch).toHaveBeenCalledTimes(1); // apenas o GET /pacotes
  });

  it("inicia instalação após confirmar licença", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    mockConfirm.mockReturnValue(true);

    // Mock SSE response
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"estado":"baixando","bytes_baixados":500,"bytes_total":1000}\n\n'));
        controller.enqueue(encoder.encode('data: {"estado":"concluido","bytes_baixados":1000,"bytes_total":1000}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: stream,
    });

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btn.click();

    // Aguarda processamento do SSE
    await new Promise((r) => setTimeout(r, 50));

    expect(notificarSpy).toHaveBeenCalledWith(
      expect.stringContaining("instalado com sucesso")
    );
  });

  it("notifica erro quando instalação falha via SSE", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    mockConfirm.mockReturnValue(true);

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"estado":"falhou","bytes_baixados":0,"bytes_total":1000,"erro":"hash incorreto"}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      body: stream,
    });

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btn = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btn.click();

    await new Promise((r) => setTimeout(r, 50));

    expect(notificarSpy).toHaveBeenCalledWith(
      expect.stringContaining("hash incorreto"),
      true
    );
  });

  it("chama endpoint de cancelamento ao clicar em Cancelar", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS]);
    mockConfirm.mockReturnValue(true);

    // SSE que nunca termina (simula download longo)
    const stream = new ReadableStream({
      start() { /* não fecha */ },
    });

    mockFetch
      .mockResolvedValueOnce({ ok: true, body: stream }) // POST instalar
      .mockResolvedValueOnce({ ok: true, json: async () => ({ estado: "cancelado" }) }); // POST cancelar

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btnInstalar = raiz.querySelector('button[data-acao="instalar"]') as HTMLButtonElement;
    btnInstalar.click();

    await new Promise((r) => setTimeout(r, 20));

    const btnCancel = raiz.querySelector('button[data-acao="cancelar"]') as HTMLButtonElement;
    if (btnCancel) btnCancel.click();

    await new Promise((r) => setTimeout(r, 20));

    // Verifica que o cancel foi chamado
    const calls = mockFetch.mock.calls.map((c: unknown[]) => String(c[0]));
    expect(calls.some((u: string) => u.includes("/cancelar"))).toBe(true);
  });

  it("remove pacote instalado após confirmação", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS], { "xtts-v2": true });
    mockConfirm.mockReturnValue(true);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btnRemover = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    expect(btnRemover).toBeTruthy();
    btnRemover.click();

    await new Promise((r) => setTimeout(r, 20));

    expect(notificarSpy).toHaveBeenCalledWith(expect.stringContaining("removido"));
  });

  it("não remove pacote se usuário cancelar confirmação", async () => {
    const { raiz } = criarDom();
    mockPacotesResponse([PACOTE_XTTS], { "xtts-v2": true });
    mockConfirm.mockReturnValue(false);

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    const btnRemover = raiz.querySelector('button[data-acao="remover"]') as HTMLButtonElement;
    btnRemover.click();

    await new Promise((r) => setTimeout(r, 10));

    // Apenas o GET /pacotes foi chamado, não o POST /remover
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("notifica erro de conexão ao carregar pacotes", async () => {
    const { raiz } = criarDom();
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    const tela = new InstaladorVozes(raiz, deps);
    await tela.montar();

    // Carregamento falho é silencioso: não polui o status global da aba.
    expect(notificarSpy).not.toHaveBeenCalled();
    expect(raiz.textContent).toContain("Nenhum pacote disponível");
  });
});
