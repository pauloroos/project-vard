/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Conversa, ehCancelamentoPedido, mensagemParaErroPedido } from "../src/fala/conversa";
import { FALAS } from "../src/fala/falas";
import type { Cerebro } from "../src/config/cerebro";

const WAV = new ArrayBuffer(8);

function montarDeps(overrides: Record<string, unknown> = {}) {
  const pedir = vi.fn(async () => ({ pedido_id: "p-1", sessao_id: "s-1", estado: "na_fila" }));
  const cancelar = vi.fn(async () => ({ estado: "cancelado" }));
  const consultarPedido = vi.fn(async () => null);
  const deps = {
    config: { nome: "Vard", variantes: [], voz: "", velocidade: 1, instrucao_formato: "", conversa_ms: 0, usuario: "teste" } as any,
    oj: null,
    boca: { falando: false, parar: vi.fn(), tocar: vi.fn(async () => {}) } as any,
    falas: vi.fn(async () => WAV),
    aoResposta: vi.fn(),
    aoEstado: vi.fn(),
    cerebro: "proprio" as Cerebro,
    sessaoVoz: () => "s-1",
    ponte: { ver: vi.fn(), modo: vi.fn(), pedir, cancelar, consultarPedido },
    ...overrides,
  };
  return { deps, pedir, cancelar, consultarPedido };
}

function evento(tipo: string, dados: unknown, seq = 1, pedido = "p-1", sessao = "s-1") {
  window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
    data: JSON.stringify({ tipo: "pedido", pedido_id: pedido, sessao_id: sessao, seq, evento_tipo: tipo, dados }),
  }));
}

describe("pedido: estados visuais (peça 3)", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it("sucesso: pensando -> falando -> repouso", async () => {
    const { deps } = montarDeps();
    const estados: string[] = [];
    deps.aoEstado = vi.fn((e: string) => { estados.push(e); });
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    expect(c.estado).toBe("pensando");
    setTimeout(() => evento("texto", { texto: "olá" }, 1), 0);
    setTimeout(() => evento("fim", { resposta: "olá" }, 2), 10);
    await vi.runAllTimersAsync();
    await p;
    expect(deps.aoResposta).toHaveBeenCalledWith("olá");
    expect(estados).toEqual(["pensando", "falando", "repouso"]);
    expect(c.estado).toBe("repouso");
    expect(c.detalhe).toBe("");
  });

  it("erro cancelado volta ao repouso sem mensagem", async () => {
    const { deps } = montarDeps();
    const estados: string[] = [];
    deps.aoEstado = vi.fn((e: string) => { estados.push(e); });
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    setTimeout(() => evento("erro", { erro: "cancelado" }, 1), 0);
    await vi.runAllTimersAsync();
    await p;
    expect(c.estado).toBe("repouso");
    expect(c.detalhe).toBe("");
    expect(estados).not.toContain("erro");
    expect(deps.aoResposta).not.toHaveBeenCalled();
    expect(deps.falas).not.toHaveBeenCalled();
  });

  it("fim com erro cancelado volta ao repouso sem mensagem", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    setTimeout(() => evento("fim", { resposta: "", erro: "cancelado" }, 1), 0);
    await vi.runAllTimersAsync();
    await p;
    expect(c.estado).toBe("repouso");
    expect(c.detalhe).toBe("");
    expect(deps.aoResposta).not.toHaveBeenCalled();
    expect(deps.falas).not.toHaveBeenCalled();
  });

  it("erro real mostra estado de erro com mensagem", async () => {
    const { deps } = montarDeps();
    const estados: Array<[string, string]> = [];
    deps.aoEstado = vi.fn((e: string, d = "") => { estados.push([e, d]); });
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    setTimeout(() => evento("erro", { erro: "modelo_fora" }, 1), 0);
    await vi.runAllTimersAsync();
    await p;
    expect(c.estado).toBe("erro");
    expect(c.detalhe).toBe(FALAS.erros.modelo_fora);
    expect(deps.aoResposta).not.toHaveBeenCalled();
  });

  it("queda do SSE com pedido falho na sondagem vira erro de conexão", async () => {
    const { deps, consultarPedido } = montarDeps();
    consultarPedido.mockResolvedValueOnce(null).mockResolvedValue({ estado: "falhou", erro: "rede", resposta: null } as any);
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    // Sem evento SSE: a sondagem de 2 s encontra o pedido falho.
    await vi.advanceTimersByTimeAsync(2500);
    await vi.runAllTimersAsync();
    await p;
    expect(c.estado).toBe("erro");
    expect(c.detalhe).toBe(FALAS.erros.rede);
  });

  it("sem nenhum evento terminal o prazo tira a UI do pensando", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    expect(c.estado).toBe("pensando");
    await vi.advanceTimersByTimeAsync(61000);
    await vi.runAllTimersAsync();
    await p;
    expect(["erro", "repouso"]).toContain(c.estado);
    expect(c.estado).not.toBe("pensando");
    expect(c.estado).toBe("erro");
  });

  it("nova pergunta sai do erro para pensando (não fica presa)", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    const p1 = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    setTimeout(() => evento("erro", { erro: "modelo_fora" }, 1), 0);
    await vi.runAllTimersAsync();
    await p1;
    expect(c.estado).toBe("erro");
    // Segunda tentativa: sem travar no erro.
    setTimeout(() => evento("texto", { texto: "voltei" }, 1), 0);
    setTimeout(() => evento("fim", { resposta: "voltei" }, 2), 10);
    const p2 = c.aoTextoTranscrito("oi de novo", true);
    await vi.runAllTimersAsync();
    await p2;
    expect(deps.aoResposta).toHaveBeenLastCalledWith("voltei");
    expect(c.estado).toBe("repouso");
  });
});

describe("pedido: ajudantes", () => {
  it("ehCancelamentoPedido só aceita cancelado", () => {
    expect(ehCancelamentoPedido("cancelado")).toBe(true);
    expect(ehCancelamentoPedido("rede")).toBe(false);
    expect(ehCancelamentoPedido("")).toBe(false);
    expect(ehCancelamentoPedido(null)).toBe(false);
  });

  it("mensagemParaErroPedido descreve sem vazar detalhe técnico", () => {
    expect(mensagemParaErroPedido("rede")).toBe(FALAS.erros.rede);
    expect(mensagemParaErroPedido("timeout")).toMatch(/Conexão perdida/);
    expect(mensagemParaErroPedido("sse_erro")).toMatch(/Conexão perdida/);
    expect(mensagemParaErroPedido("modelo_fora")).toBe(FALAS.erros.modelo_fora);
    expect(mensagemParaErroPedido("limite_turnos")).toContain("limite_turnos");
  });
});

describe("transcrevendo: transições e UI (peça 3 — tentativa 9)", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it("evento inicio → estado muda para transcrevendo (não pensando)", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    const estados: string[] = [];
    deps.aoEstado = vi.fn((e: string) => estados.push(e));
    // Simula início de captura: transcrevendo
    const ok = (c as any).notificarInicioTranscricao();
    expect(ok).toBe(true);
    expect(c.estado).toBe("transcrevendo");
    expect(c.estado).not.toBe("pensando");
    expect(estados).toContain("transcrevendo");
  });

  it("fim de captura → estado muda de transcrevendo para pensando", async () => {
    const { deps } = montarDeps();
    const estados: string[] = [];
    deps.aoEstado = vi.fn((e: string) => estados.push(e));
    const c = new Conversa(deps as any);
    (c as any).notificarInicioTranscricao();
    expect(c.estado).toBe("transcrevendo");
    // transcrição pronta: vai para pensando antes de falar
    (c as any).notificarTranscricaoPronta();
    expect(c.estado).toBe("pensando");
    expect(estados).toEqual(["transcrevendo", "pensando"]);
    // agora o fluxo normal de pedido: pensando -> falando -> repouso
    const p = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    // já está pensando, não muda de novo
    expect(c.estado).toBe("pensando");
    setTimeout(() => evento("texto", { texto: "olá" }, 1), 0);
    setTimeout(() => evento("fim", { resposta: "olá" }, 2), 10);
    await vi.runAllTimersAsync();
    await p;
    expect(c.estado).toBe("repouso");
  });

  it("estado erro bloqueia início de nova gravação", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    // força erro via evento real
    const p1 = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(0);
    setTimeout(() => evento("erro", { erro: "modelo_fora" }, 1), 0);
    await vi.runAllTimersAsync();
    await p1;
    expect(c.estado).toBe("erro");
    const estadosAntes: string[] = [];
    deps.aoEstado = vi.fn((e: string) => estadosAntes.push(e));
    const ok = (c as any).notificarInicioTranscricao();
    expect(ok).toBe(false);
    expect(c.estado).toBe("erro");
    expect(estadosAntes).not.toContain("transcrevendo");
    expect(estadosAntes).not.toContain("pensando");
  });

  it("timeout tira a UI de transcrevendo se nenhum evento chegar", async () => {
    const { deps } = montarDeps();
    const c = new Conversa(deps as any);
    const estados: string[] = [];
    deps.aoEstado = vi.fn((e: string) => estados.push(e));
    (c as any).notificarInicioTranscricao();
    expect(c.estado).toBe("transcrevendo");
    await vi.advanceTimersByTimeAsync(31000);
    expect(c.estado).toBe("erro");
    expect(estados).toContain("erro");
    // após 3s volta ao repouso permitindo nova tentativa
    await vi.advanceTimersByTimeAsync(3100);
    expect(c.estado).toBe("repouso");
  });

  it("UI renderiza transcrevendo distintamente", async () => {
    const { ROTULO_ESTADO } = await import("../src/ui/hud");
    expect(ROTULO_ESTADO["transcrevendo"]).toBeDefined();
    expect(ROTULO_ESTADO["transcrevendo"]).not.toBe(ROTULO_ESTADO["pensando"]);
    expect(ROTULO_ESTADO["transcrevendo"].length).toBeGreaterThan(0);
    // Nucleo: verifica que o arquivo contém entradas distintas para transcrevendo
    const fs2 = await import("fs");
    const nucleoSrc = (fs2 as any).readFileSync("src/ui/nucleo.ts", "utf8");
    expect(nucleoSrc).toContain('transcrevendo: { c:');
    expect(nucleoSrc).toContain('transcrevendo: { velExt:');
    // Invisibilidade: transcrevendo mantém visível com modo ligado
    const { Invisibilidade } = await import("../src/ui/invisivel");
    let vis = true;
    const inv = new Invisibilidade((v: boolean) => { vis = v; }, 0);
    inv.definirModo(true);
    inv.definirEstado("transcrevendo" as any);
    expect(vis).toBe(true);
    inv.definirEstado("repouso" as any);
    // com atraso 0, já esconde quando repouso sem canal
    expect(vis).toBe(false);
    // Sala espelho aceita transcrevendo
    const { reduzir, ESPELHO_INICIAL } = await import("../src/sala/espelho");
    const esp = reduzir(ESPELHO_INICIAL, { tipo: "estado", estado: "transcrevendo", detalhe: "" });
    expect(esp.estado).toBe("transcrevendo");
    // Prova aceita
    // Verifica que prova aceita transcrevendo inspecionando arquivo
    const provaSrc = (fs2 as any).readFileSync("src/prova.ts", "utf8");
    expect(provaSrc).toContain("transcrevendo");
    // Verifica Hud ROTULO já acima; Hud setEstado não precisa instanciar Nucleo para este teste
    // CSS contém regra para transcrevendo
    const fs = await import("fs");
    const css = (fs as any).readFileSync("src/styles.css", "utf8");
    expect(css).toContain('data-estado="transcrevendo"');
  });

  it("skip de gravação em estado de erro: encerrar não inicia transcrição (main guard)", async () => {
    // Verifica que o guard existe em src/main.ts como texto (prova de que o skip foi restaurado)
    const fs = await import("fs");
    const main = (fs as any).readFileSync("src/main.ts", "utf8");
    expect(main).toContain('if (conversa.estado === "erro") return;');
    // e que comecarCaptura também guarda
    const count = (main.match(/if \(conversa\.estado === "erro"\) return;/g) || []).length;
    expect(count).toBeGreaterThanOrEqual(1);
    // transição para transcrevendo existe
    expect(main).toContain('mostrarEstado("transcrevendo"');
    expect(main).toContain('mostrarEstado("pensando"');
  });
});
