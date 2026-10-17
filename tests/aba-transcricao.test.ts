/**
 * @vitest-environment jsdom
 */
/**
 * Aba Transcrição: modelos do faster-whisper em cards (baixar com progresso, usar, excluir) e dispositivo.
 * O serviço de voz é um fetch falso; nada sai da máquina.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue(null) }));
import { CONFIG_PADRAO, normalizarConfig, type Config } from "../src/config/config";
import { AbaTranscricao } from "../src/ui/aba-transcricao";

interface Modelo {
  id: string; nome: string; repo: string; tamanho_mb: number; idioma: string; velocidade: number; precisao: number;
  descricao: string; baixado: boolean; ativo: boolean;
  progresso: { estado: string; bytes: number; total: number; porcentagem: number; erro: string | null };
}

const parado = { estado: "parado", bytes: 0, total: 1, porcentagem: 0, erro: null };
const concluido = { estado: "concluido", bytes: 1, total: 1, porcentagem: 100, erro: null };
const modelo = (id: string, extra: Partial<Modelo> = {}): Modelo => ({
  id, nome: id.toUpperCase(), repo: `org-ficticia/${id}`, tamanho_mb: 500, idioma: "multilingue", velocidade: 4, precisao: 3,
  descricao: `Descrição de ${id}.`, baixado: false, ativo: false, progresso: parado, ...extra,
});

let estado: { modelos: Modelo[]; ativo: string; dispositivo: string; device: string; pronta: boolean; carregando: boolean; erro: string | null } | null;
let respostas: Record<string, { status: number; corpo: unknown }>;
const pedidos: { url: string; metodo: string; corpo: unknown }[] = [];

const fetchFalso = vi.fn(async (url: string, init: RequestInit = {}) => {
  const metodo = init.method ?? "GET";
  const corpo = init.body ? JSON.parse(String(init.body)) : undefined;
  pedidos.push({ url, metodo, corpo });
  const caminho = url.replace("http://127.0.0.1:4710", "");
  const fixa = respostas[`${metodo} ${caminho}`];
  if (fixa) return new Response(JSON.stringify(fixa.corpo), { status: fixa.status });
  if (metodo === "GET" && caminho === "/v1/stt/modelos") {
    if (!estado) throw new TypeError("Failed to fetch");
    return new Response(JSON.stringify(estado), { status: 200 });
  }
  return new Response(JSON.stringify({ ok: true }), { status: 200 });
});

function criar(extra: Partial<Config> = {}) {
  const raiz = document.createElement("div");
  document.body.append(raiz);
  const cfg: Config = { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos }, voz_url: "http://127.0.0.1:4710", ...extra };
  const salvar = vi.fn(async (_p: Partial<Config>) => {});
  const dizer = vi.fn();
  const aba = new AbaTranscricao(raiz, { vozUrl: () => cfg.voz_url, config: cfg, salvar, dizer, fetch: fetchFalso as unknown as typeof fetch, intervaloMs: 1000 });
  aba.montar();
  return { raiz, aba, cfg, salvar, dizer };
}

const card = (raiz: HTMLElement, id: string) => raiz.querySelector<HTMLElement>(`.card[data-id="${id}"]`)!;
const botoes = (el: HTMLElement) => [...el.querySelectorAll("button")].map((b) => b.textContent);
const botao = (el: HTMLElement, rotulo: string) => [...el.querySelectorAll("button")].find((b) => b.textContent === rotulo)!;
const esperar = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  document.body.innerHTML = "";
  pedidos.length = 0;
  respostas = {};
  fetchFalso.mockClear();
  estado = {
    modelos: [
      modelo("base", { baixado: true, ativo: true, progresso: concluido, tamanho_mb: 145 }),
      modelo("small", { baixado: true, progresso: concluido }),
      modelo("large-v3-turbo", { tamanho_mb: 1620, velocidade: 3, precisao: 5 }),
      modelo("distil-large-v3", { idioma: "ingles" }),
    ],
    ativo: "base", dispositivo: "cuda", device: "cuda", pronta: true, carregando: false, erro: null,
  };
});
afterEach(() => { vi.useRealTimers(); });

describe("AbaTranscricao: cards", () => {
  it("mostra um card por modelo com tamanho, idioma, velocidade e precisão", async () => {
    const t = criar();
    await t.aba.atualizar();
    const turbo = card(t.raiz, "large-v3-turbo");
    expect(turbo.querySelector("h3")!.textContent).toBe("LARGE-V3-TURBO");
    expect(turbo.textContent).toContain("1,6 GB");
    expect(turbo.textContent).toContain("Multilíngue");
    expect(turbo.textContent).toContain("Velocidade ●●●○○");
    expect(turbo.textContent).toContain("Precisão ●●●●●");
    expect(card(t.raiz, "distil-large-v3").textContent).toContain("Só inglês");
    expect(card(t.raiz, "base").textContent).toContain("145 MB");
  });

  it("estado decide os botões: em uso sem ações, baixado com Usar/Excluir, ausente com Baixar", async () => {
    const t = criar();
    await t.aba.atualizar();
    expect(card(t.raiz, "base").textContent).toContain("Em uso");
    expect(botoes(card(t.raiz, "base"))).toEqual([]);
    expect(card(t.raiz, "small").textContent).toContain("Baixado");
    expect(botoes(card(t.raiz, "small"))).toEqual(["Usar", "Excluir"]);
    expect(botoes(card(t.raiz, "large-v3-turbo"))).toEqual(["Baixar"]);
  });

  it("baixar pede ao serviço e mostra o progresso no card", async () => {
    const t = criar();
    await t.aba.atualizar();
    estado!.modelos[2] = { ...estado!.modelos[2], progresso: { estado: "baixando", bytes: 640, total: 1620, porcentagem: 40, erro: null } };
    botao(card(t.raiz, "large-v3-turbo"), "Baixar").click();
    await esperar(); await esperar();
    expect(pedidos.some((p) => p.metodo === "POST" && p.url.endsWith("/v1/stt/modelos/large-v3-turbo/baixar"))).toBe(true);
    const c = card(t.raiz, "large-v3-turbo");
    expect(c.textContent).toContain("Baixando 40%");
    expect(c.querySelector<HTMLProgressElement>("progress")!.value).toBe(40);
    expect(botoes(c)).toEqual([]);
  });

  it("acompanha o download sozinho enquanto a aba está aberta e avisa ao terminar", async () => {
    vi.useFakeTimers();
    estado!.modelos[2] = { ...estado!.modelos[2], progresso: { estado: "baixando", bytes: 0, total: 1, porcentagem: 10, erro: null } };
    const t = criar();
    t.aba.ativar();
    await vi.advanceTimersByTimeAsync(0);
    const antes = fetchFalso.mock.calls.length;
    estado!.modelos[2] = { ...estado!.modelos[2], baixado: true, progresso: concluido };
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchFalso.mock.calls.length).toBeGreaterThan(antes);
    expect(botoes(card(t.raiz, "large-v3-turbo"))).toEqual(["Usar", "Excluir"]);
    expect(t.dizer).toHaveBeenCalledWith(expect.stringContaining("LARGE-V3-TURBO baixado"));
    // Sem download nem troca em andamento, para de consultar; fechar a aba também para.
    const depois = fetchFalso.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchFalso.mock.calls.length).toBe(depois);
    t.aba.desativar();
  });

  it("falha no download aparece no card com Tentar de novo", async () => {
    estado!.modelos[2] = { ...estado!.modelos[2], progresso: { estado: "falhou", bytes: 0, total: 1, porcentagem: 0, erro: "sem rede" } };
    const t = criar();
    await t.aba.atualizar();
    const c = card(t.raiz, "large-v3-turbo");
    expect(c.textContent).toContain("Falhou");
    expect(c.textContent).toContain("sem rede");
    expect(botoes(c)).toEqual(["Tentar de novo"]);
  });
});

describe("AbaTranscricao: usar, excluir e dispositivo", () => {
  it("Usar troca o ativo no serviço e grava stt_modelo e stt_dispositivo", async () => {
    const t = criar({ stt_dispositivo: "cuda" });
    await t.aba.atualizar();
    botao(card(t.raiz, "small"), "Usar").click();
    await esperar(); await esperar();
    const pedido = pedidos.find((p) => p.metodo === "POST" && p.url.endsWith("/v1/stt/ativar"))!;
    expect(pedido.corpo).toEqual({ modelo: "small", dispositivo: "cuda" });
    expect(t.salvar).toHaveBeenCalledWith({ stt_modelo: "small", stt_dispositivo: "cuda" });
    expect(t.cfg.stt_modelo).toBe("small");
  });

  it("Usar recusado pelo serviço não grava e avisa", async () => {
    respostas["POST /v1/stt/ativar"] = { status: 409, corpo: { erro: "modelo_nao_baixado" } };
    const t = criar();
    await t.aba.atualizar();
    botao(card(t.raiz, "small"), "Usar").click();
    await esperar(); await esperar();
    expect(t.salvar).not.toHaveBeenCalled();
    expect(t.dizer).toHaveBeenCalledWith(expect.stringContaining("baixe"), true);
  });

  it("Excluir pede confirmação em modal antes de apagar", async () => {
    const t = criar();
    await t.aba.atualizar();
    botao(card(t.raiz, "small"), "Excluir").click();
    const modal = document.querySelector<HTMLElement>(".modal")!;
    expect(modal.textContent).toContain("SMALL");
    expect(pedidos.some((p) => p.url.endsWith("/apagar"))).toBe(false);
    botao(modal, "Excluir").click();
    await esperar(); await esperar();
    expect(pedidos.some((p) => p.metodo === "POST" && p.url.endsWith("/v1/stt/modelos/small/apagar"))).toBe(true);
    expect(document.querySelector(".modal")).toBeNull();
  });

  it("o dispositivo começa pelo salvo; vazio, segue o que o serviço usa", async () => {
    const salvo = criar({ stt_dispositivo: "cpu" });
    await salvo.aba.atualizar();
    expect(salvo.raiz.querySelector<HTMLSelectElement>("#trn-dispositivo")!.value).toBe("cpu");
    document.body.innerHTML = "";
    const vazio = criar();
    await vazio.aba.atualizar();
    expect(vazio.raiz.querySelector<HTMLSelectElement>("#trn-dispositivo")!.value).toBe("cuda");
  });

  it("trocar o dispositivo recarrega no serviço e grava stt_dispositivo", async () => {
    const t = criar();
    await t.aba.atualizar();
    const sel = t.raiz.querySelector<HTMLSelectElement>("#trn-dispositivo")!;
    expect([...sel.options].map((o) => o.value)).toEqual(["auto", "cuda", "cpu"]);
    sel.value = "cpu";
    sel.dispatchEvent(new Event("change"));
    await esperar(); await esperar();
    const pedido = pedidos.find((p) => p.metodo === "POST" && p.url.endsWith("/v1/stt/ativar"))!;
    expect(pedido.corpo).toEqual({ dispositivo: "cpu" });
    expect(t.salvar).toHaveBeenCalledWith({ stt_dispositivo: "cpu" });
  });

  it("mostra o modelo em uso, a troca em andamento e a falha da última troca", async () => {
    const t = criar();
    await t.aba.atualizar();
    const status = () => t.raiz.querySelector<HTMLElement>("#trn-status")!.textContent!;
    expect(status()).toContain("Em uso: BASE");
    expect(status()).toContain("GPU");
    estado = { ...estado!, carregando: true, pronta: false };
    await t.aba.atualizar();
    expect(status()).toContain("Carregando");
    estado = { ...estado!, carregando: false, pronta: true, erro: "CUDA indisponível" };
    await t.aba.atualizar();
    expect(status()).toContain("CUDA indisponível");
  });

  it("serviço de voz fora do ar mostra o aviso sem cards", async () => {
    estado = null;
    const t = criar();
    await t.aba.atualizar();
    expect(t.raiz.querySelector(".card")).toBeNull();
    expect(t.raiz.textContent).toContain("serviço de voz");
  });

  it("sem endereço do serviço de voz não consulta nada", async () => {
    const t = criar({ voz_url: "" });
    await t.aba.atualizar();
    expect(fetchFalso).not.toHaveBeenCalled();
    expect(t.raiz.textContent).toContain("serviço de voz");
  });
});

describe("Config: campos da transcrição", () => {
  it("padrão vazio: o serviço segue as variáveis", () => {
    expect(CONFIG_PADRAO.stt_modelo).toBe("");
    expect(CONFIG_PADRAO.stt_dispositivo).toBe("");
  });

  it("guarda valores válidos e descarta dispositivo desconhecido", () => {
    const ok = normalizarConfig({ stt_modelo: "small", stt_dispositivo: "cpu" });
    expect([ok.stt_modelo, ok.stt_dispositivo]).toEqual(["small", "cpu"]);
    const ruim = normalizarConfig({ stt_modelo: 3, stt_dispositivo: "tpu" });
    expect([ruim.stt_modelo, ruim.stt_dispositivo]).toEqual(["", ""]);
  });
});
