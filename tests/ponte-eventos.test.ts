/** @vitest-environment jsdom */
import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte } from "../src/conectores/ponte/cliente";

// EventSource falso: guarda os ouvintes por nome de evento para o teste disparar.
class FonteFalsa {
  static ultima: FonteFalsa | null = null;
  ouvintes = new Map<string, ((ev: MessageEvent) => void)[]>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  constructor(public url: string) { FonteFalsa.ultima = this; }
  addEventListener(tipo: string, fn: (ev: MessageEvent) => void) {
    this.ouvintes.set(tipo, [...(this.ouvintes.get(tipo) ?? []), fn]);
  }
  disparar(tipo: string, dados: unknown) {
    for (const fn of this.ouvintes.get(tipo) ?? []) fn(new MessageEvent(tipo, { data: JSON.stringify(dados) }));
  }
  close() {}
}

describe("Ponte.eventos", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it("repassa_eventos_pedido_do_cerebro_proprio", () => {
    vi.stubGlobal("EventSource", FonteFalsa);
    const recebidos: [string, unknown][] = [];
    const parar = new Ponte("http://127.0.0.1:4700").eventos((tipo, dados) => recebidos.push([tipo, dados]));
    const ev = { tipo: "pedido", pedido_id: "p-1", sessao_id: "s-1", seq: 3, evento_tipo: "fim", dados: { resposta: "ok" } };
    FonteFalsa.ultima!.disparar("pedido", ev);
    parar();
    expect(recebidos).toContainEqual(["pedido", ev]);
  });
});
