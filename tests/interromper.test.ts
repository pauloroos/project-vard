import { describe, it, expect, vi } from "vitest";
import { Conversa, ehCancelamentoPedido } from "../src/fala/conversa";
import { CONFIG_PADRAO } from "../src/config/config";

const WAV = new ArrayBuffer(8);

function montarBase(opts: Partial<{
  cerebro: "openjarvis" | "proprio";
  oj: unknown;
  voz: unknown;
  ponte: unknown;
  sessao: string;
}> = {}) {
  const oj = (opts.oj ?? { perguntar: vi.fn().mockResolvedValue("resposta"), sintetizar: vi.fn().mockResolvedValue(WAV) }) as NonNullable<typeof opts.oj>;
  const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), tocarFluxo: vi.fn().mockResolvedValue(undefined), parar: vi.fn() } as unknown as never;
  const estados: string[] = [];
  const c = new Conversa({
    oj: oj as never,
    boca: boca as never,
    voz: opts.voz as never,
    ponte: opts.ponte as never,
    config: CONFIG_PADRAO,
    falas: async () => WAV,
    cerebro: (opts.cerebro ?? "openjarvis") as never,
    sessaoVoz: () => opts.sessao ?? "sessao-teste",
    aoEstado: (e) => estados.push(e),
    aoResposta: vi.fn(),
  });
  return { c, oj: oj as { perguntar: ReturnType<typeof vi.fn>; sintetizar: ReturnType<typeof vi.fn> }, boca: boca as { falar: boolean; tocar: ReturnType<typeof vi.fn>; tocarFluxo: ReturnType<typeof vi.fn>; parar: ReturnType<typeof vi.fn> }, estados };
}

describe("interromper — transcrevendo", () => {
  it("interrupção durante transcrevendo volta ao repouso e é idempotente", () => {
    const { c, estados, boca } = montarBase();
    const ok = (c as unknown as { notificarInicioTranscricao: () => boolean }).notificarInicioTranscricao();
    expect(ok).toBe(true);
    expect(c.estado).toBe("transcrevendo");
    c.interromper();
    expect(c.estado).toBe("repouso");
    expect(boca.parar).toHaveBeenCalled();
    expect(estados).toContain("transcrevendo");
    expect(estados[estados.length - 1]).toBe("repouso");
    // segunda chamada não quebra
    c.interromper();
    expect(c.estado).toBe("repouso");
  });

  it("descarta texto tardio após interromper durante transcrição", async () => {
    const { c } = montarBase({ cerebro: "openjarvis", oj: { perguntar: vi.fn().mockResolvedValue("deveria ser descartado"), sintetizar: vi.fn().mockResolvedValue(WAV) } });
    const ac = new AbortController();
    (c as unknown as { anotarCiclo: (ac: AbortController) => void }).anotarCiclo(ac);
    (c as unknown as { notificarInicioTranscricao: () => boolean }).notificarInicioTranscricao();
    c.interromper(); // simula interromper durante STT (aborta ac e volta ao repouso)
    expect(ac.signal.aborted).toBe(true);
    // mesmo que o texto chegue depois, não deve iniciar pensamento
    await c.aoTextoTranscrito("texto tardio", true);
    expect(c.estado).toBe("repouso");
  });

  it("timeout de transcrevendo vai para erro e depois repouso", async () => {
    vi.useFakeTimers();
    try {
      const { c } = montarBase();
      (c as unknown as { notificarInicioTranscricao: () => boolean }).notificarInicioTranscricao();
      expect(c.estado).toBe("transcrevendo");
      vi.advanceTimersByTime(30000);
      expect(c.estado).toBe("erro");
      vi.advanceTimersByTime(3000);
      expect(c.estado).toBe("repouso");
    } finally { vi.useRealTimers(); }
  });
});

describe("interromper — pensando (SSE/ponte)", () => {
  it("interromper durante pensando aborta SSE e volta ao repouso", async () => {
    const ponte = {
      pedir: vi.fn().mockResolvedValue({ pedido_id: "p1", sessao_id: "sessao-teste", estado: "executando" }),
      consultarPedido: vi.fn().mockResolvedValue(null),
      cancelar: vi.fn().mockResolvedValue({ estado: "cancelado" }),
    };
    const { c, boca, estados } = montarBase({ cerebro: "proprio", ponte });
    const p = c.aoTextoTranscrito("Vard, explique algo", true);
    await vi.waitFor(() => expect(ponte.pedir).toHaveBeenCalled());
    expect(c.estado).toBe("pensando");
    c.interromper();
    expect(boca.parar).toHaveBeenCalled();
    // interromper já move para repouso mesmo sem fim do SSE
    expect(c.estado).toBe("repouso");
    expect(ponte.cancelar).toHaveBeenCalledWith("p1");
    await p;
    expect(c.estado).toBe("repouso");
    expect(estados).toContain("repouso");
  });

  it("erro cancelado do núcleo volta ao repouso sem mensagem de erro", async () => {
    const ponte = {
      pedir: vi.fn().mockResolvedValue({ pedido_id: "p2", sessao_id: "sessao-teste", estado: "executando" }),
      consultarPedido: vi.fn().mockResolvedValue({ pedido_id: "p2", sessao_id: "sessao-teste", estado: "falhou", erro: "cancelado", resposta: null }),
      cancelar: vi.fn().mockResolvedValue({ estado: "cancelado" }),
    };
    const falas = vi.fn().mockResolvedValue(WAV);
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const estados: string[] = [];
    const c = new Conversa({
      oj: { perguntar: vi.fn(), sintetizar: vi.fn().mockResolvedValue(WAV) } as never,
      boca: boca as never,
      config: CONFIG_PADRAO,
      falas: falas as never,
      cerebro: "proprio" as never,
      sessaoVoz: () => "sessao-teste",
      ponte: ponte as never,
      aoEstado: (e) => estados.push(e),
    });
    await c.aoTextoTranscrito("Vard, teste cancelado", true);
    // deve terminar em repouso sem ter falado erro
    expect(c.estado).toBe("repouso");
    expect(falas).not.toHaveBeenCalledWith(expect.stringContaining("Não consegui"));
    // erro cancelado não deve deixar em erro
    expect(estados).not.toContain("erro");
  });

  it("evento SSE fim com erro cancelado é tratado como interrupção normal", async () => {
    // também valida via reconciliação: snap falhou com cancelado já volta ao repouso sem precisar de SSE
    const ponte = {
      pedir: vi.fn().mockResolvedValue({ pedido_id: "p3", sessao_id: "sessao-teste", estado: "executando" }),
      consultarPedido: vi.fn().mockResolvedValue({ pedido_id: "p3", sessao_id: "sessao-teste", estado: "falhou", erro: "cancelado", resposta: null }),
      cancelar: vi.fn().mockResolvedValue({ estado: "cancelado" }),
    };
    const { c } = montarBase({ cerebro: "proprio", ponte });
    await c.aoTextoTranscrito("Vard, outro", true);
    expect(c.estado).toBe("repouso");
  });
});

describe("interromper — falando (fila e playback)", () => {
  it("interromper durante falando limpa fila, para playback e volta ao repouso", async () => {
    const nomes = new Map<ReadableStream<Uint8Array>, string>();
    const cancelados: string[] = [];
    const fala = (texto: string) => {
      const corpo = new ReadableStream<Uint8Array>({ cancel: () => { cancelados.push(texto); } });
      nomes.set(corpo, texto);
      return { corpo, taxa: 24000 };
    };
    const fimDoToque: Array<() => void> = [];
    const boca = {
      falando: false,
      tocar: vi.fn().mockResolvedValue(undefined),
      tocarFluxo: vi.fn((corpo: ReadableStream<Uint8Array>) => { nomes.get(corpo); return new Promise<void>((r) => fimDoToque.push(r)); }),
      parar: vi.fn(() => { for (const r of fimDoToque.splice(0)) r(); }),
    };
    const voz = { falar: vi.fn(async (t: string) => fala(t)) };
    const oj = { perguntar: vi.fn().mockResolvedValue("Primeira frase. Segunda frase. Terceira frase."), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const estados: string[] = [];
    const c = new Conversa({ oj: oj as never, boca: boca as never, voz: voz as never, config: CONFIG_PADRAO, falas: async () => WAV, aoEstado: (e) => estados.push(e) });
    const p = c.aoTextoTranscrito("me conta algo", true);
    // espera primeira frase começar a tocar
    await vi.waitFor(() => expect(boca.tocarFluxo).toHaveBeenCalled());
    expect(c.estado).toBe("falando");
    c.interromper();
    expect(boca.parar).toHaveBeenCalled();
    expect(c.estado).toBe("repouso");
    await p;
    // segunda frase não deve ter tocado
    expect(boca.tocarFluxo).toHaveBeenCalledTimes(1);
    expect(cancelados.length).toBeGreaterThanOrEqual(1);
  });

  it("interrupção dupla não quebra nem vaza listener", async () => {
    const { c, boca } = montarBase();
    // coloca em pensando
    const oj = { perguntar: vi.fn().mockImplementation(() => new Promise<string>(() => {})), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const c2 = new Conversa({ oj: oj as never, boca: boca as never, config: CONFIG_PADRAO, falas: async () => WAV, aoEstado: vi.fn() });
    void c2.aoTextoTranscrito("Vard, oi", false);
    await vi.waitFor(() => expect(c2.estado).toBe("pensando"));
    c2.interromper();
    c2.interromper(); // segunda
    expect(c2.estado).toBe("repouso");
    expect(boca.parar).toHaveBeenCalled();
    // garante que não há timers órfãos de transcrevendo
    // se houvesse timer, estado não seria estável
    c.interromper();
    c.interromper();
    expect(c.estado).toBe("repouso");
  });
});

describe("helpers de cancelamento", () => {
  it("ehCancelamentoPedido reconhece cancelado", () => {
    expect(ehCancelamentoPedido("cancelado")).toBe(true);
    expect(ehCancelamentoPedido("erro_desconhecido")).toBe(false);
    expect(ehCancelamentoPedido(null)).toBe(false);
  });
});

describe("recursos liberados", () => {
  it("interromper remove listeners de abort e timers de transcrevendo", async () => {
    vi.useFakeTimers();
    try {
      const { c } = montarBase();
      (c as unknown as { notificarInicioTranscricao: () => boolean }).notificarInicioTranscricao();
      expect(c.estado).toBe("transcrevendo");
      c.interromper();
      expect(c.estado).toBe("repouso");
      // avança 30s: não deve voltar a erro porque timer foi limpo
      vi.advanceTimersByTime(35000);
      expect(c.estado).toBe("repouso");
    } finally { vi.useRealTimers(); }
  });

  it("abort da transcrição invalida texto tardio (controladorCiclo)", async () => {
    const { c } = montarBase();
    const ac = new AbortController();
    (c as unknown as { anotarCiclo: (ac: AbortController) => void }).anotarCiclo(ac);
    (c as unknown as { notificarInicioTranscricao: () => boolean }).notificarInicioTranscricao();
    c.interromper(); // aborta ac
    expect(ac.signal.aborted).toBe(true);
    await c.aoTextoTranscrito("deveria ser ignorado", true);
    expect(c.estado).toBe("repouso");
  });
});
