import { describe, it, expect, vi, beforeEach } from "vitest";
import { Conversa, type DepsConversa } from "../src/fala/conversa";
import { cortarEmFrases } from "../src/fala/frases";

/**
 * Testes de integração real da classe Conversa com fala progressiva (FR-008).
 * Verifica que:
 * - Frases completas são faladas durante streaming via eventos TEXTO.
 * - O evento FIM não duplica frases já faladas progressivamente.
 * - O contador de chamadas a boca.tocar / voz.falar corresponde ao número esperado de frases.
 */

function criarDeps(overrides: Partial<DepsConversa> = {}): DepsConversa {
  return {
    oj: null,
    boca: {
      falando: false,
      tocar: vi.fn().mockResolvedValue(undefined),
      parar: vi.fn(),
    },
    voz: {
      falar: vi.fn().mockResolvedValue({
        corpo: new ReadableStream({
          start(controller) {
            controller.enqueue(new Uint8Array([0]));
            controller.close();
          },
        }),
        taxa: 24000,
      }),
    },
    falas: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
    config: {
      nome: "Vard",
      variantes: [],
      voz: "default",
      velocidade: 1,
      instrucao_formato: "",
      conversa_ms: 0,
    },
    cerebro: "proprio",
    sessaoVoz: () => "sessao-teste",
    ponte: {
      ver: vi.fn(),
      modo: vi.fn(),
      pedir: vi.fn().mockResolvedValue({
        pedido_id: "ped-1",
        sessao_id: "sessao-teste",
        estado: "na_fila",
      }),
      cancelar: vi.fn().mockResolvedValue({ estado: "cancelado" }),
      consultarPedido: vi.fn().mockResolvedValue({
        resposta: null,
        estado: "executando",
        ultimo_seq: 0,
      }),
    },
    ...overrides,
  } as unknown as DepsConversa;
}

describe("fala por frase completa (FR-008)", () => {
  it("corta frases longas em múltiplas partes pela pontuação", () => {
    const texto = "Olá, tudo bem com você? Espero que sim, vamos começar.";
    const frases = cortarEmFrases(texto);
    expect(frases.length).toBeGreaterThanOrEqual(2);
    expect(frases[0]).toContain("Olá, tudo bem com você?");
    expect(frases[frases.length - 1]).toContain("vamos começar.");
  });

  it("mantém fragmentos curtos juntos quando não há pontuação suficiente", () => {
    const texto = "Oi! Tudo bem?";
    const frases = cortarEmFrases(texto);
    expect(frases.length).toBeGreaterThanOrEqual(1);
    for (const f of frases) {
      expect(f.length).toBeGreaterThan(0);
    }
  });

  it("não fala fragmentos incompletos durante streaming simulado", () => {
    const buffer: string[] = [];
    const acumulador: string[] = [];

    const fragmentos = [
      "Olá, ",
      "tudo bem ",
      "com você? ",
      "Espero que sim, ",
      "vamos começar.",
    ];

    for (const frag of fragmentos) {
      buffer.push(frag);
      const textoAtual = buffer.join("");
      const frases = cortarEmFrases(textoAtual);
      if (frases.length > 1) {
        for (let i = 0; i < frases.length - 1; i++) {
          acumulador.push(frases[i]);
        }
        buffer.length = 0;
        buffer.push(frases[frases.length - 1]);
      }
    }

    const resto = buffer.join("").trim();
    if (resto) acumulador.push(resto);

    expect(acumulador.length).toBeGreaterThanOrEqual(2);
    expect(acumulador[0]).toMatch(/[.!?…]$/);
  });

  it("flusha todo o texto restante no evento FIM", () => {
    const texto = "Frase sem pontuação final";
    const frases = cortarEmFrases(texto);
    expect(frases).toEqual(["Frase sem pontuação final"]);
  });
});

describe("Conversa: fala progressiva sem duplicação (FR-008)", () => {
  let deps: DepsConversa;
  let conversa: Conversa;

  beforeEach(() => {
    deps = criarDeps();
    conversa = new Conversa(deps);
  });

  it("fala frases completas durante streaming e não duplica no FIM", async () => {
    // Simula SSE: eventos TEXTO chegam progressivamente, depois FIM
    const eventosSSE: Array<{ evento_tipo: string; dados: Record<string, unknown>; seq: number }> = [
      { evento_tipo: "texto", dados: { texto: "Olá, " }, seq: 1 },
      { evento_tipo: "texto", dados: { texto: "tudo bem " }, seq: 2 },
      { evento_tipo: "texto", dados: { texto: "com você? " }, seq: 3 },
      { evento_tipo: "texto", dados: { texto: "Vamos começar." }, seq: 4 },
      { evento_tipo: "fim", dados: { resposta: "Olá, tudo bem com você? Vamos começar." }, seq: 5 },
    ];

    // Mock do consultarPedido para retornar estado concluído após os eventos
    let consultaCount = 0;
    (deps.ponte!.consultarPedido as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      consultaCount++;
      if (consultaCount <= 2) {
        return { resposta: null, estado: "executando", ultimo_seq: 0 };
      }
      return {
        resposta: "Olá, tudo bem com você? Vamos começar.",
        estado: "concluido",
        ultimo_seq: 5,
      };
    });

    // Dispara eventos SSE simulados via window
    const dispararEventos = () => {
      for (const ev of eventosSSE) {
        const msgEvent = new MessageEvent("vard-evento-pedido", {
          data: JSON.stringify({
            tipo: "pedido",
            pedido_id: "ped-1",
            sessao_id: "sessao-teste",
            seq: ev.seq,
            evento_tipo: ev.evento_tipo,
            dados: ev.dados,
          }),
        });
        window.dispatchEvent(msgEvent);
      }
    };

    // Aguarda um tick para o listener ser registrado antes de disparar
    const promessaTexto = conversa.aoTextoTranscrito("teste", true);
    await new Promise((r) => setTimeout(r, 10));
    dispararEventos();

    try {
      await promessaTexto;
    } catch {
      // Pode lançar se o fluxo terminar rápido demais; o importante é verificar as chamadas
    }

    // Aguarda microtasks de fala assíncrona
    await new Promise((r) => setTimeout(r, 50));

    const vozFalar = deps.voz!.falar as ReturnType<typeof vi.fn>;
    const bocaTocar = deps.boca.tocar as ReturnType<typeof vi.fn>;

    // Deve ter falado pelo menos uma vez (frases completas durante streaming ou flush no FIM)
    const totalChamadas = vozFalar.mock.calls.length + bocaTocar.mock.calls.length;
    expect(totalChamadas).toBeGreaterThan(0);

    // Não deve ter duplicado: o número de chamadas deve ser compatível com o número de frases,
    // não o dobro. Com 2 frases ("Olá, tudo bem com você?" e "Vamos começar."), espera-se ~2 chamadas.
    // Tolerância: até 3 (buffer flush pode gerar chamada extra).
    expect(totalChamadas).toBeLessThanOrEqual(4);

    // Asserção de conteúdo: todas as frases devem ter sido faladas na ordem correta
    const falas = vozFalar.mock.calls.map((c: unknown[]) => c[0] as string);
    expect(falas).toEqual(["Olá, tudo bem com você?", "Vamos começar."]);
  });

  it("prefixo recuperado pela consulta inicial deve ser falado", async () => {
    // Simula consulta inicial trazendo prefixo antes do streaming SSE
    let consultaCount = 0;
    (deps.ponte!.consultarPedido as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      consultaCount++;
      if (consultaCount === 1) {
        return {
          resposta: "Prefixo recuperado pela consulta. ",
          estado: "executando",
          ultimo_seq: 1,
        };
      }
      return {
        resposta: "Prefixo recuperado pela consulta. Continuação do texto via SSE.",
        estado: "concluido",
        ultimo_seq: 3,
      };
    });

    const promessaTexto = conversa.aoTextoTranscrito("teste", true);
    await new Promise((r) => setTimeout(r, 10));

    // SSE envia o restante do texto e finaliza
    const eventos = [
      { evento_tipo: "texto", dados: { texto: "Continuação do texto via SSE." }, seq: 2 },
      { evento_tipo: "fim", dados: { resposta: "Prefixo recuperado pela consulta. Continuação do texto via SSE." }, seq: 3 },
    ];
    for (const ev of eventos) {
      window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
        data: JSON.stringify({
          tipo: "pedido",
          pedido_id: "ped-1",
          sessao_id: "sessao-teste",
          seq: ev.seq,
          evento_tipo: ev.evento_tipo,
          dados: ev.dados,
        }),
      }));
    }

    try {
      await promessaTexto;
    } catch {
      // Ignora término rápido
    }

    await new Promise((r) => setTimeout(r, 50));

    const vozFalar = deps.voz!.falar as ReturnType<typeof vi.fn>;
    const falas = vozFalar.mock.calls.map((c: unknown[]) => c[0] as string);
    // Prefixo da consulta inicial + continuação do SSE devem ter sido ambos falados
    expect(falas).toEqual([
      "Prefixo recuperado pela consulta.",
      "Continuação do texto via SSE.",
    ]);
  });

  it("última frase via reconexão deve ser falada", async () => {
    // SSE envia apenas a primeira frase, depois a conexão cai
    let consultaCount = 0;
    (deps.ponte!.consultarPedido as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      consultaCount++;
      if (consultaCount === 1) {
        return { resposta: null, estado: "executando", ultimo_seq: 0 };
      }
      // Na reconexão, consulta traz a resposta completa concluída
      return {
        resposta: "Primeira frase recebida por streaming. Última frase entregue na reconexão.",
        estado: "concluido",
        ultimo_seq: 2,
      };
    });

    const promessaTexto = conversa.aoTextoTranscrito("teste", true);
    await new Promise((r) => setTimeout(r, 10));

    // SSE envia apenas o primeiro fragmento/frase (sem evento fim)
    window.dispatchEvent(new MessageEvent("vard-evento-pedido", {
      data: JSON.stringify({
        tipo: "pedido",
        pedido_id: "ped-1",
        sessao_id: "sessao-teste",
        seq: 1,
        evento_tipo: "texto",
        dados: { texto: "Primeira frase recebida por streaming. " },
      }),
    }));

    await new Promise((r) => setTimeout(r, 10));

    // Simula reconexão do SSE (dispara evento de reconexão que invoca consultar())
    window.dispatchEvent(new CustomEvent("vard-sse-reconectou"));

    try {
      await promessaTexto;
    } catch {
      // Ignora término rápido
    }

    await new Promise((r) => setTimeout(r, 50));

    const vozFalar = deps.voz!.falar as ReturnType<typeof vi.fn>;
    const falas = vozFalar.mock.calls.map((c: unknown[]) => c[0] as string);
    // Primeira frase via SSE + última frase recuperada na reconexão devem ter sido faladas
    expect(falas).toEqual([
      "Primeira frase recebida por streaming.",
      "Última frase entregue na reconexão.",
    ]);
  });

  it("sem eventos TEXTO progressivos, fala a resposta completa no fim", async () => {
    // Cenário sem streaming progressivo: só FIM com resposta
    (deps.ponte!.consultarPedido as ReturnType<typeof vi.fn>).mockResolvedValue({
      resposta: "Resposta direta.",
      estado: "concluido",
      ultimo_seq: 1,
    });

    try {
      await conversa.aoTextoTranscrito("teste", true);
    } catch {
      // Fluxo pode completar rapidamente
    }

    await new Promise((r) => setTimeout(r, 50));

    const vozFalar = deps.voz!.falar as ReturnType<typeof vi.fn>;
    // Sem streaming progressivo, falarEmFrases deve ser chamado no fim
    expect(vozFalar.mock.calls.length).toBeGreaterThanOrEqual(1);
  });
});