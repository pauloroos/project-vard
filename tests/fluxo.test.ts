import { describe, it, expect, vi, afterEach } from "vitest";
import { comPrazoEntrePedacos } from "../src/conectores/voz/fluxo";
import { ErroVoz } from "../src/conectores/voz/cliente";

afterEach(() => vi.useRealTimers());

describe("comPrazoEntrePedacos", () => {
  it("repassa_os_pedacos_e_fecha", async () => {
    const fonte = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new Uint8Array([1, 2])); c.enqueue(new Uint8Array([3])); c.close(); } });
    const l = comPrazoEntrePedacos(fonte, 1000).getReader();
    expect((await l.read()).value).toEqual(new Uint8Array([1, 2]));
    expect((await l.read()).value).toEqual(new Uint8Array([3]));
    expect((await l.read()).done).toBe(true);
  });
  it("pedaco_que_nao_chega_erra_e_cancela_a_fonte", async () => {
    vi.useFakeTimers();
    const cancelar = vi.fn();
    const fonte = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new Uint8Array([1])); }, pull: () => new Promise(() => {}), cancel: cancelar });
    const l = comPrazoEntrePedacos(fonte, 8000).getReader();
    expect((await l.read()).value).toEqual(new Uint8Array([1]));
    const lido = l.read().catch((e) => e);
    await vi.advanceTimersByTimeAsync(8000);
    const e = await lido;
    expect(e).toBeInstanceOf(ErroVoz);
    expect((e as ErroVoz).message).toBe("a voz passou do prazo");
    expect(cancelar).toHaveBeenCalled();
  });
});
