import { describe, it, expect, vi } from "vitest";
import { ErroVoz, Voz } from "../src/conectores/voz/cliente";

type Init = RequestInit;

/** Corpo em fluxo que entrega os pedaços dados e fecha (ou fica aberto, se `aberto`). */
function fluxo(pedacos: Uint8Array[], aberto = false) {
  const cancelado = vi.fn();
  const corpo = new ReadableStream<Uint8Array>({
    start(c) { for (const p of pedacos) c.enqueue(p); if (!aberto) c.close(); },
    cancel: cancelado,
  });
  return { corpo, cancelado };
}

function pcm(): Response {
  return new Response(fluxo([new Uint8Array([1, 2, 3]), new Uint8Array([4, 5, 6, 7])]).corpo, {
    status: 200, headers: { "Content-Type": "audio/pcm", "X-Taxa": "22050" },
  });
}

/** fetch que nunca responde, mas respeita o abort. */
const pendurado = (_u: string, init: Init) => new Promise<Response>((_, rejeitar) => {
  init.signal?.addEventListener("abort", () => rejeitar(new DOMException("abortado", "AbortError")));
});

async function lerTudo(corpo: ReadableStream<Uint8Array>): Promise<number[]> {
  const saida: number[] = [];
  const r = corpo.getReader();
  for (;;) { const { done, value } = await r.read(); if (done) return saida; saida.push(...value); }
}

describe("Voz", () => {
  it("200 em PCM: devolve o fluxo inteiro e a taxa do cabeçalho", async () => {
    const f = vi.fn(async (_u: string, _i: Init) => pcm());
    const voz = new Voz("http://127.0.0.1:4710/", { fetch: f });
    const { corpo, taxa } = await voz.falar("Oi.", 1.05);
    expect(taxa).toBe(22050);
    expect(await lerTudo(corpo)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:4710/falar");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Accept).toBe("audio/pcm");
    expect(JSON.parse(String(init.body))).toEqual({ texto: "Oi.", velocidade: 1.05 });
  });

  it("sem X-Taxa legível usa 24 kHz", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response(fluxo([new Uint8Array([0, 0])]).corpo, { status: 200 }) });
    expect((await voz.falar("Oi.", 1)).taxa).toBe(24000);
  });

  it("503 rejeita sem ser erro de conexão", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response(JSON.stringify({ erro: "aquecendo" }), { status: 503 }) });
    const erro = await voz.falar("Oi.", 1).catch((e) => e);
    expect(erro).toBeInstanceOf(ErroVoz);
    expect(erro.conexao).toBe(false);
  });

  it("serviço fora do ar rejeita como erro de conexão", async () => {
    const voz = new Voz("http://x", { fetch: async () => { throw new TypeError("Failed to fetch"); } });
    await expect(voz.falar("Oi.", 1)).rejects.toMatchObject({ conexao: true });
  });

  it("passa do prazo sem resposta: rejeita", async () => {
    const voz = new Voz("http://x", { fetch: pendurado, prazoMs: 30 });
    await expect(voz.falar("Oi.", 1)).rejects.toMatchObject({ conexao: true, message: "a voz passou do prazo" });
  });

  it("cabeçalho chega mas o primeiro áudio não: rejeita no prazo e encerra o pedido", async () => {
    const { corpo, cancelado } = fluxo([], true);
    let sinalDoPedido: AbortSignal | undefined;
    const voz = new Voz("http://x", { prazoMs: 30, fetch: async (_u, i) => { sinalDoPedido = i.signal ?? undefined; return new Response(corpo, { status: 200 }); } });
    await expect(voz.falar("Oi.", 1)).rejects.toMatchObject({ conexao: true });
    expect(sinalDoPedido?.aborted).toBe(true);
    expect(cancelado).toHaveBeenCalled();
  });

  it("prazoMs por pedido vale no lugar do padrão (falas fixas: 2 s em vez de 8 s)", async () => {
    const voz = new Voz("http://x", { fetch: pendurado, prazoMs: 5000 });
    const t0 = Date.now();
    await expect(voz.falar("Oi.", 1, undefined, 30)).rejects.toMatchObject({ conexao: true, message: "a voz passou do prazo" });
    expect(Date.now() - t0).toBeLessThan(2000);
    await expect(voz.falarWav("Oi.", 1, 30)).rejects.toMatchObject({ conexao: true });
  });

  it("silêncio entre dois pedaços passa do prazo: o corpo falha como erro de conexão", async () => {
    const { corpo } = fluxo([new Uint8Array([1, 2])], true); // 1º pedaço chega, o resto nunca
    const voz = new Voz("http://x", { prazoMs: 30, fetch: async () => new Response(corpo, { status: 200 }) });
    const r = await voz.falar("Oi.", 1);
    const leitor = r.corpo.getReader();
    expect((await leitor.read()).value).toEqual(new Uint8Array([1, 2]));
    await expect(leitor.read()).rejects.toMatchObject({ conexao: true, message: "a voz passou do prazo" });
  });

  it("corpo vazio rejeita", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response(fluxo([]).corpo, { status: 200 }) });
    await expect(voz.falar("Oi.", 1)).rejects.toMatchObject({ message: "voz sem áudio" });
  });

  it("abort de fora cancela o pedido em andamento", async () => {
    const voz = new Voz("http://x", { fetch: pendurado, prazoMs: 5000 });
    const ac = new AbortController();
    const p = voz.falar("Oi.", 1, ac.signal);
    ac.abort();
    await expect(p).rejects.toBeInstanceOf(ErroVoz);
  });

  it("cancelar o corpo encerra o pedido no serviço", async () => {
    const { corpo, cancelado } = fluxo([new Uint8Array([1, 2])], true);
    let sinalDoPedido: AbortSignal | undefined;
    const voz = new Voz("http://x", { fetch: async (_u, i) => { sinalDoPedido = i.signal ?? undefined; return new Response(corpo, { status: 200 }); } });
    const r = await voz.falar("Oi.", 1);
    await r.corpo.cancel();
    expect(sinalDoPedido?.aborted).toBe(true);
    expect(cancelado).toHaveBeenCalled();
  });

  it("falarWav monta um WAV com o PCM recebido", async () => {
    const voz = new Voz("http://x", { fetch: async () => pcm() });
    const wav = await voz.falarWav("Oi.", 1);
    expect(wav.byteLength).toBe(44 + 6); // 7 bytes de PCM: o ímpar sai
    expect(new DataView(wav).getUint32(24, true)).toBe(22050);
  });

  it("saude: pronta e nome da voz", async () => {
    const resposta = (j: object) => async () => new Response(JSON.stringify(j), { status: 200 });
    const voz = new Voz("http://x", { fetch: resposta({ pronta: true, voz: "Voz Teste", device: "cuda", aquecida: true }) });
    expect(await voz.saude()).toBe(true);
    expect(voz.nome).toBe("Voz Teste");
    expect(await new Voz("http://x", { fetch: resposta({ pronta: false, voz: "Voz Teste" }) }).saude()).toBe(false);
    expect(await new Voz("http://x", { fetch: async () => { throw new TypeError("Failed to fetch"); } }).saude()).toBe(false);
  });

  it("voz pedida vai no corpo e vira o nome antes do saude", async () => {
    const f = vi.fn(async (_u: string, _i: Init) => pcm());
    const voz = new Voz("http://x", { fetch: f, voz: "Ana Florence" });
    expect(voz.nome).toBe("Ana Florence");
    await voz.falar("Oi.", 1);
    expect(JSON.parse(String(f.mock.calls[0][1].body))).toEqual({ texto: "Oi.", velocidade: 1, voz: "Ana Florence" });
  });

  it("sem voz pedida o corpo não tem a chave", async () => {
    const f = vi.fn(async (_u: string, _i: Init) => pcm());
    await new Voz("http://x", { fetch: f }).falar("Oi.", 1);
    expect("voz" in JSON.parse(String(f.mock.calls[0][1].body))).toBe(false);
  });

  it("voz pedida não é trocada pelo saude", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response(JSON.stringify({ pronta: true, voz: "Suad" }), { status: 200 }), voz: "Ana" });
    await voz.saude();
    expect(voz.nome).toBe("Ana");
  });

  it("vozes 200 devolve lista e atual", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response(JSON.stringify({ vozes: ["A", "B"], atual: "A" }), { status: 200 }) });
    expect(await voz.vozes()).toEqual({ vozes: ["A", "B"], atual: "A" });
  });

  it("vozes 404 devolve vazio", async () => {
    const voz = new Voz("http://x", { fetch: async () => new Response("{}", { status: 404 }) });
    expect(await voz.vozes()).toEqual({ vozes: [], atual: "" });
  });
});
