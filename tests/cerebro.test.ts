/** @vitest-environment jsdom */
import { describe, it, expect, vi } from "vitest";
import { Ponte, type EstadoPedido, type EventoPedidoSSE } from "../src/conectores/ponte/cliente";

// Fakes de fetch para isolar a ponte TS sem rede real
function mockFetch(responses: Record<string, unknown>) {
  return vi.fn(async (url: string | Request | URL, _init?: RequestInit) => {
    const u = typeof url === "string" ? url : url.toString();
    for (const [pattern, body] of Object.entries(responses)) {
      if (u.includes(pattern)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return new Response(JSON.stringify({ erro: "not_found" }), { status: 404 });
  });
}

describe("Ponte.pedir", () => {
  it("POST /pedidos devolve estado inicial com pedido_id e sessao_id", async () => {
    const esperado: EstadoPedido = {
      pedido_id: "p-1",
      sessao_id: "s-1",
      estado: "na_fila",
    };
    globalThis.fetch = mockFetch({ "/pedidos": esperado }) as any;
    const ponte = new Ponte("http://127.0.0.1:4700");
    const resultado = await ponte.pedir("oi", "s-1");
    expect(resultado.pedido_id).toBe("p-1");
    expect(resultado.estado).toBe("na_fila");
  });

  it("falha de rede lança ErroPonte('rede')", async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error("ECONNREFUSED"); }) as any;
    const ponte = new Ponte("http://127.0.0.1:4700");
    await expect(ponte.pedir("oi", "s-1")).rejects.toThrow("rede");
  });
});

describe("Ponte.cancelar", () => {
  it("POST /pedidos/{id}/cancelar devolve estado cancelado", async () => {
    const esperado: EstadoPedido = {
      pedido_id: "p-2",
      sessao_id: "s-2",
      estado: "cancelado",
    };
    globalThis.fetch = mockFetch({ "/cancelar": esperado }) as any;
    const ponte = new Ponte("http://127.0.0.1:4700");
    const resultado = await ponte.cancelar("p-2");
    expect(resultado.estado).toBe("cancelado");
  });
});

describe("Ponte.consultarPedido", () => {
  it("GET /pedidos/{id} devolve estado ou null se ausente", async () => {
    const esperado: EstadoPedido = {
      pedido_id: "p-3",
      sessao_id: "s-3",
      estado: "concluido",
      resposta: "ok",
    };
    globalThis.fetch = mockFetch({ "/pedidos/p-3": esperado }) as any;
    const ponte = new Ponte("http://127.0.0.1:4700");
    const resultado = await ponte.consultarPedido("p-3");
    expect(resultado?.estado).toBe("concluido");
    expect(resultado?.resposta).toBe("ok");
  });

  it("devolve null quando o servidor retorna 404", async () => {
    globalThis.fetch = vi.fn(async () => new Response("", { status: 404 })) as any;
    const ponte = new Ponte("http://127.0.0.1:4700");
    const resultado = await ponte.consultarPedido("inexistente");
    expect(resultado).toBeNull();
  });
});

describe("EventoPedidoSSE", () => {
  it("formato SSE do tipo 'pedido' carrega campos obrigatórios", () => {
    // Validação estrutural do contrato SSE (sem rede): o formato deve conter
    // pedido_id, sessao_id, seq, evento_tipo e dados.
    const ev: EventoPedidoSSE = {
      tipo: "pedido",
      pedido_id: "p-4",
      sessao_id: "s-4",
      seq: 3,
      evento_tipo: "texto",
      dados: { texto: "resposta parcial" },
    };
    expect(ev.tipo).toBe("pedido");
    expect(ev.evento_tipo).toBe("texto");
    expect(ev.seq).toBe(3);
  });
});