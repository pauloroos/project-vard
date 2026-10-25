/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Conversa } from "../src/fala/conversa";
import type { Cerebro } from "../src/config/cerebro";
import { FALAS } from "../src/fala/falas";

function montarDeps(overrides: Record<string, unknown> = {}) {
  let contador = 0;
  const pedir = vi.fn(async () => {
    contador += 1;
    return { pedido_id: `p-${contador}`, sessao_id: "s-1", estado: "na_fila" };
  });
  const cancelar = vi.fn(async () => ({ estado: "cancelado" }));
  const consultarPedido = vi.fn(async () => null);
  const perguntar = vi.fn(async () => "resposta openjarvis");
  const estados: Array<{ estado: string; detalhe: string }> = [];
  const deps = {
    config: { nome: "Vard", variantes: [], voz: "", velocidade: 1, instrucao_formato: "", conversa_ms: 0, usuario: "teste" } as any,
    oj: { perguntar, sintetizar: vi.fn(async () => new Uint8Array(8).buffer) } as any,
    boca: { falando: false, parar: vi.fn(), tocar: vi.fn(async () => {}), tocarFluxo: undefined } as any,
    falas: vi.fn(async (_t: string) => new Uint8Array(8).buffer),
    aoResposta: vi.fn(),
    aoEstado: vi.fn((e: string, d: string) => { estados.push({ estado: e, detalhe: d }); }),
    cerebro: "proprio" as Cerebro,
    sessaoVoz: () => "s-1",
    depoisDaCaptura: vi.fn(),
    ponte: {
      ver: vi.fn(),
      modo: vi.fn(),
      pedir,
      cancelar,
      consultarPedido,
    },
    ...overrides,
  };
  return { deps, pedir, cancelar, consultarPedido, perguntar, estados };
}

describe("FR-002: Reconsultar pedido e prazo de 90 s sem progresso", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("reconsulta_estado_ao_reconectar_sse", async () => {
    const { deps, consultarPedido } = montarDeps();
    consultarPedido.mockResolvedValueOnce({ estado: "executando", ultimo_seq: 0 } as any);
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(10);

    // Servidor concluiu durante a perda de conexão SSE
    consultarPedido.mockResolvedValue({ estado: "concluido", resposta: "resposta reconectada", ultimo_seq: 2 } as any);

    // Reconexão do SSE dispara evento
    window.dispatchEvent(new Event("vard-sse-reconectou"));
    await vi.advanceTimersByTimeAsync(10);
    await promessa;

    expect(deps.aoResposta).toHaveBeenCalledWith("resposta reconectada");
  });

  it("reconsulta_periodicamente_enquanto_houver_pedido_ativo", async () => {
    const { deps, consultarPedido } = montarDeps();
    consultarPedido.mockResolvedValueOnce({ estado: "executando", ultimo_seq: 0 } as any);
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(10);

    // Servidor conclui em segundo plano sem evento SSE chegar
    consultarPedido.mockResolvedValue({ estado: "concluido", resposta: "resposta periodica", ultimo_seq: 1 } as any);

    // Avança o tempo para o polling periódico rodar
    await vi.advanceTimersByTimeAsync(5000);
    await promessa;

    expect(deps.aoResposta).toHaveBeenCalledWith("resposta periodica");
  });

  it("prazo_90s_sem_progresso_cancela_no_servidor_libera_captura_e_mostra_erro", async () => {
    const { deps, consultarPedido, cancelar, estados } = montarDeps();
    consultarPedido.mockResolvedValue({ estado: "executando", ultimo_seq: 0 } as any);
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(10);

    // Passam 90 segundos sem progresso algum
    await vi.advanceTimersByTimeAsync(90000);
    await promessa;

    // Deve ter cancelado o pedido no servidor
    expect(cancelar).toHaveBeenCalledWith("p-1");
    // Deve ter liberado a captura
    expect(deps.depoisDaCaptura).toHaveBeenCalled();
    // Deve ter mostrado erro na interface com fala de modelo_demorou
    expect(estados.some((e) => e.estado === "erro" && e.detalhe === FALAS.erros.modelo_demorou)).toBe(true);
  });

  it("progresso_sse_reseta_prazo_de_90s", async () => {
    const { deps, consultarPedido, cancelar } = montarDeps();
    consultarPedido.mockResolvedValue({ estado: "executando", ultimo_seq: 0 } as any);
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(10);

    // 80 segundos se passam
    await vi.advanceTimersByTimeAsync(80000);
    expect(cancelar).not.toHaveBeenCalled();

    // Evento SSE chega representando progresso aos 80s
    window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
      data: JSON.stringify({
        tipo: "pedido",
        pedido_id: "p-1",
        sessao_id: "s-1",
        seq: 1,
        evento_tipo: "texto",
        dados: { texto: "progresso parcial " },
      }),
    }));

    // Mais 80 segundos se passam (total 160s, mas apenas 80s desde o progresso)
    await vi.advanceTimersByTimeAsync(80000);
    expect(cancelar).not.toHaveBeenCalled();

    // Evento final chega aos 160s
    window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
      data: JSON.stringify({
        tipo: "pedido",
        pedido_id: "p-1",
        sessao_id: "s-1",
        seq: 2,
        evento_tipo: "fim",
        dados: {},
      }),
    }));

    await vi.advanceTimersByTimeAsync(10);
    await promessa;

    expect(deps.aoResposta).toHaveBeenCalledWith("progresso parcial");
    expect(cancelar).not.toHaveBeenCalled();
  });

  it("progresso_na_consulta_periodica_reseta_prazo_de_90s", async () => {
    const { deps, consultarPedido, cancelar } = montarDeps();
    consultarPedido.mockResolvedValue({ estado: "executando", ultimo_seq: 0 } as any);
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.advanceTimersByTimeAsync(10);

    // Aos 80s, a consulta periódica detecta avanço de ultimo_seq
    await vi.advanceTimersByTimeAsync(80000);
    consultarPedido.mockResolvedValue({ estado: "executando", ultimo_seq: 1, resposta: "parcial" } as any);
    await vi.advanceTimersByTimeAsync(5000); // polling roda e vê seq=1

    // Mais 80s se passam sem timeout
    await vi.advanceTimersByTimeAsync(80000);
    expect(cancelar).not.toHaveBeenCalled();

    // Conclusão aos 170s
    consultarPedido.mockResolvedValue({ estado: "concluido", ultimo_seq: 2, resposta: "parcial final" } as any);
    await vi.advanceTimersByTimeAsync(5000);
    await promessa;

    expect(deps.aoResposta).toHaveBeenCalledWith("parcial final");
    expect(cancelar).not.toHaveBeenCalled();
  });
});
