/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Conversa } from "../src/fala/conversa";
import type { Cerebro } from "../src/config/cerebro";

// Fakes mínimos para isolar a lógica de roteamento por cérebro
function montarDeps(overrides: Record<string, unknown> = {}) {
  let contador = 0;
  const pedir = vi.fn(async () => {
    contador += 1;
    return { pedido_id: `p-${contador}`, sessao_id: "s-1", estado: "na_fila" };
  });
  const cancelar = vi.fn(async () => ({ estado: "cancelado" }));
  const consultarPedido = vi.fn(async () => null);
  const perguntar = vi.fn(async () => "resposta openjarvis");
  const deps = {
    config: { nome: "Vard", variantes: [], voz: "", velocidade: 1, instrucao_formato: "", conversa_ms: 0, usuario: "teste" } as any,
    oj: { perguntar, sintetizar: vi.fn(async () => new Uint8Array(8).buffer) } as any,
    boca: { falando: false, parar: vi.fn(), tocar: vi.fn(async () => {}), tocarFluxo: undefined } as any,
    falas: vi.fn(async (_t: string) => new Uint8Array(8).buffer),
    aoResposta: vi.fn(),
    cerebro: "openjarvis" as Cerebro,
    sessaoVoz: () => "s-1",
    ponte: {
      ver: vi.fn(),
      modo: vi.fn(),
      pedir,
      cancelar,
      consultarPedido,
    },
    ...overrides,
  };
  return { deps, pedir, cancelar, consultarPedido, perguntar };
}

describe("Conversa.cerebro", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("com_openjarvis_usa_oj_perguntar_e_nao_chama_ponte_pedir", async () => {
    const { deps, perguntar, pedir } = montarDeps({ cerebro: "openjarvis" });
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    await vi.runAllTimersAsync();
    await promessa;
    expect(perguntar).toHaveBeenCalled();
    expect(pedir).not.toHaveBeenCalled();
  });

  it("com_proprio_chama_ponte_pedir_e_aguarda_evento_texto", async () => {
    const { deps, pedir, perguntar } = montarDeps({ cerebro: "proprio" });
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    // Dispara evento SSE fake após a admissão do pedido
    setTimeout(() => {
      window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
        data: JSON.stringify({
          tipo: "pedido",
          pedido_id: "p-1",
          sessao_id: "s-1",
          seq: 1,
          evento_tipo: "texto",
          dados: { texto: "resposta propria" },
        }),
      }));
      setTimeout(() => {
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
      }, 0);
    }, 0);
    await vi.runAllTimersAsync();
    await promessa;
    expect(pedir).toHaveBeenCalledWith("oi vard", "s-1");
    expect(perguntar).not.toHaveBeenCalled();
    expect(deps.aoResposta).toHaveBeenCalledWith("resposta propria");
  });

  it("ignora_eventos_de_outra_sessao", async () => {
    const { deps } = montarDeps({ cerebro: "proprio" });
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    setTimeout(() => {
      // Evento de sessão diferente não deve resolver a promessa
      window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
        data: JSON.stringify({
          tipo: "pedido",
          pedido_id: "p-1",
          sessao_id: "s-OUTRA",
          seq: 1,
          evento_tipo: "texto",
          dados: { texto: "texto errado" },
        }),
      }));
      // Evento correto chega depois
      setTimeout(() => {
        window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
          data: JSON.stringify({
            tipo: "pedido",
            pedido_id: "p-1",
            sessao_id: "s-1",
            seq: 1,
            evento_tipo: "texto",
            dados: { texto: "certo" },
          }),
        }));
        setTimeout(() => {
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
        }, 0);
      }, 0);
    }, 0);
    await vi.runAllTimersAsync();
    await promessa;
    expect(deps.aoResposta).toHaveBeenCalledWith("certo");
  });

  it("cancela_pedido_quando_fala_eh_cortada", async () => {
    const { deps, cancelar } = montarDeps({ cerebro: "proprio" });
    const c = new Conversa(deps as any);
    const promessa = c.aoTextoTranscrito("oi vard", true);
    // Aguarda o primeiro pedir ser chamado para saber o ID do primeiro pedido
    await vi.advanceTimersByTimeAsync(0);
    const primeiroId = "p-1";
    // Simula corte da fala antes do fim: dispara outro pedido que aborta o anterior
    setTimeout(() => {
      void c.aoTextoTranscrito("pare vard", true);
    }, 0);
    // Resolve o SEGUNDO pedido (p-2) para não deixar promise pendente; o primeiro (p-1) deve ser cancelado
    setTimeout(() => {
      window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
        data: JSON.stringify({
          tipo: "pedido",
          pedido_id: "p-2",
          sessao_id: "s-1",
          seq: 1,
          evento_tipo: "fim",
          dados: {},
        }),
      }));
    }, 0);
    await vi.runAllTimersAsync();
    await promessa.catch(() => {}); // primeira pode rejeitar pelo abort
    expect(cancelar).toHaveBeenCalledWith(primeiroId);
  });
});