/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Conversa } from "../src/fala/conversa";

const F1 = "Primeira frase da resposta.";
const F2 = "Segunda frase da resposta.";
const F3 = "Terceira frase da resposta.";

const esperar = async (cond: () => boolean, limite = 200) => {
  for (let i = 0; i < limite && !cond(); i++) await new Promise((r) => setTimeout(r, 0));
  expect(cond()).toBe(true);
};

function montar(automatico: boolean) {
  const nomes = new Map<ReadableStream<Uint8Array>, string>();
  const cancelados: string[] = [];
  const falar = (texto: string) => {
    const corpo = new ReadableStream<Uint8Array>({
      cancel: () => {
        cancelados.push(texto);
      },
    });
    nomes.set(corpo, texto);
    return { corpo, taxa: 24000 };
  };
  const tocados: string[] = [];
  const fimDoToque: Array<() => void> = [];
  const boca = {
    falando: false,
    tocar: vi.fn(async (_w: ArrayBuffer) => {
      tocados.push("reserva");
    }),
    tocarFluxo: vi.fn((corpo: ReadableStream<Uint8Array>) => {
      tocados.push(nomes.get(corpo) ?? "?");
      if (automatico) return Promise.resolve();
      return new Promise<void>((r) => {
        fimDoToque.push(r);
      });
    }),
    parar: vi.fn(() => {
      for (const r of fimDoToque.splice(0)) r();
    }),
  };
  const voz = { falar: vi.fn(async (t: string) => falar(t)) };
  const estados: string[] = [];
  const aoResposta = vi.fn();
  const pedir = vi.fn(async () => ({ pedido_id: "p-1", sessao_id: "s-1", estado: "na_fila" }));
  const cancelar = vi.fn(async () => ({ estado: "cancelado" }));
  const consultarPedido = vi.fn(async () => null);
  const c = new Conversa({
    oj: { perguntar: vi.fn(), sintetizar: vi.fn(async () => new ArrayBuffer(8)) },
    boca,
    voz,
    config: { nome: "Vard", variantes: [], voz: "", velocidade: 1, instrucao_formato: "", conversa_ms: 0 } as never,
    falas: async () => new ArrayBuffer(8),
    aoEstado: (e: string) => estados.push(e),
    aoResposta,
    cerebro: "proprio",
    sessaoVoz: () => "s-1",
    ponte: { ver: vi.fn(), modo: vi.fn(), pedir, cancelar, consultarPedido } as never,
  } as never);
  const enviar = (seq: number, evento_tipo: string, dados: Record<string, unknown>) => {
    window.dispatchEvent(
      new MessageEvent("vard-evento-pedido", {
        data: JSON.stringify({ tipo: "pedido", pedido_id: "p-1", sessao_id: "s-1", seq, evento_tipo, dados }),
      }),
    );
  };
  return { c, boca, voz, tocados, fimDoToque, cancelados, estados, aoResposta, pedir, cancelar, enviar };
}

beforeEach(() => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fala frase por frase em streaming (cerebro proprio)", () => {
  it("chunks fracionados viram frases na ordem sem esperar o fim", async () => {
    const m = montar(true);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await esperar(() => m.pedir.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    // Primeira frase chega fatiada em dois pedaços.
    m.enviar(1, "texto", { texto: "Primeira fra" });
    await new Promise((r) => setTimeout(r, 0));
    expect(m.tocados).toEqual([]);
    m.enviar(2, "texto", { texto: "se da resposta. " });
    await esperar(() => m.tocados.length === 1);
    expect(m.tocados).toEqual([F1]); // falou antes do fim chegar
    expect(m.voz.falar.mock.calls[0][0]).toBe(F1);
    // Resto chega fatiado e depois o fim.
    m.enviar(3, "texto", { texto: "Segunda frase da resposta. Terceira frase" });
    m.enviar(4, "texto", { texto: " da resposta." });
    m.enviar(5, "fim", {});
    await p;
    expect(m.tocados).toEqual([F1, F2, F3]);
    expect(m.voz.falar.mock.calls.map((x) => x[0])).toEqual([F1, F2, F3]);
    expect(m.estados).toEqual(["pensando", "falando", "repouso"]);
    expect(m.aoResposta).toHaveBeenCalledWith([F1, F2, F3].join(" "));
  });

  it("interrupcao limpa a fila e para a reproducao", async () => {
    const m = montar(false);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await esperar(() => m.pedir.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    m.enviar(1, "texto", { texto: `${F1} ${F2} ` });
    await esperar(() => m.tocados.length === 1);
    expect(m.voz.falar.mock.calls.length).toBeGreaterThanOrEqual(1);
    m.c.interromper();
    expect(m.boca.parar).toHaveBeenCalled();
    await p;
    await new Promise((r) => setTimeout(r, 0));
    // Só a primeira tocou; a segunda (já pedida) foi descartada e a terceira nem pedida.
    expect(m.tocados).toEqual([F1]);
    expect(m.cancelados).toContain(F2);
    expect(m.voz.falar.mock.calls.length).toBeLessThanOrEqual(2);
    expect(m.c.estado).toBe("repouso");
    // Texto que chega depois da interrupção é descartado.
    m.enviar(9, "texto", { texto: "texto tardio que nao deve falar. " });
    m.enviar(10, "fim", {});
    await new Promise((r) => setTimeout(r, 0));
    expect(m.tocados).toEqual([F1]);
  });

  it("fim antes da fila terminar segura o idle ate drenar", async () => {
    const m = montar(false);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await esperar(() => m.pedir.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    m.enviar(1, "texto", { texto: `${F1} ` });
    await esperar(() => m.tocados.length === 1);
    expect(m.c.estado).toBe("falando");
    // O resto e o fim chegam enquanto a primeira ainda toca.
    m.enviar(2, "texto", { texto: `${F2} ${F3} ` });
    m.enviar(3, "fim", {});
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(m.c.estado).toBe("falando"); // fim chegou, mas a fila não drenou
    expect(m.tocados).toEqual([F1]);
    m.fimDoToque.shift()!();
    await esperar(() => m.tocados.length === 2);
    expect(m.c.estado).toBe("falando");
    expect(m.tocados).toEqual([F1, F2]);
    m.fimDoToque.shift()!();
    await esperar(() => m.tocados.length === 3);
    m.fimDoToque.shift()!();
    await p;
    expect(m.tocados).toEqual([F1, F2, F3]);
    expect(m.c.estado).toBe("repouso");
    expect(m.estados[m.estados.length - 1]).toBe("repouso");
  });

  it("sem pontuacao por 500ms faz flush do buffer", async () => {
    const m = montar(true);
    const texto = "texto longo sem pontuacao chegando aos poucos para completar";
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await esperar(() => m.pedir.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    m.enviar(1, "texto", { texto });
    await new Promise((r) => setTimeout(r, 650));
    expect(m.tocados).toEqual([texto]); // flush por timeout, antes do fim
    expect(m.voz.falar.mock.calls[0][0]).toBe(texto);
    m.enviar(2, "fim", {});
    await p;
    expect(m.aoResposta).toHaveBeenCalledWith(texto);
  });

  it("frase muito curta espera o resto em vez de falar sozinha", async () => {
    const m = montar(true);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await esperar(() => m.pedir.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    m.enviar(1, "texto", { texto: "Oi. " });
    await new Promise((r) => setTimeout(r, 100));
    expect(m.voz.falar).not.toHaveBeenCalled(); // curta não sai sozinha
    expect(m.tocados).toEqual([]);
    m.enviar(2, "texto", { texto: "Tudo bem por aqui hoje com voce? " });
    await esperar(() => m.tocados.length === 1);
    // Saiu junta com a seguinte, antes do fim.
    expect(m.voz.falar.mock.calls.length).toBe(1);
    expect(m.voz.falar.mock.calls[0][0]).toBe("Oi. Tudo bem por aqui hoje com voce?");
    m.enviar(3, "fim", {});
    await p;
    expect(m.tocados).toEqual(["Oi. Tudo bem por aqui hoje com voce?"]);
  });
});
