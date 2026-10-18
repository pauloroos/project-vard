import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte } from "../src/conectores/ponte/cliente";

const BASE = "http://127.0.0.1:4700";

describe("Ponte.ver", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("manda sessao_id no formulário quando recebe; sem ele, não manda o campo", async () => {
    const corpos: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
      corpos.push(init?.body as FormData);
      return new Response(JSON.stringify({ resposta: "Um editor." }), { status: 200 });
    }));
    expect(await new Ponte(BASE).ver("QUJD", "o que vê?", "sessao-voz-ficticia")).toBe("Um editor.");
    await new Ponte(BASE).ver("QUJD", "o que vê?");
    expect(corpos[0].get("sessao_id")).toBe("sessao-voz-ficticia");
    expect(corpos[1].has("sessao_id")).toBe(false);
  });
});

describe("Ponte.saude", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("consulta a /saude e devolve true quando o núcleo responde ok", async () => {
    const f = vi.fn(async (_url: string) => new Response(JSON.stringify({ ok: true, versao: "0.9.7", pid: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    expect(await new Ponte(BASE).saude()).toBe(true);
    expect(String(f.mock.calls[0][0])).toBe(`${BASE}/saude`);
  });

  it("rede fora, HTTP ruim ou corpo sem ok devolvem false", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    expect(await new Ponte(BASE).saude()).toBe(false);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 503 })));
    expect(await new Ponte(BASE).saude()).toBe(false);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ok: false }), { status: 200 })));
    expect(await new Ponte(BASE).saude()).toBe(false);
  });

  it("ponte_url vazio nem tenta a rede", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    expect(await new Ponte("").saude()).toBe(false);
    expect(f).not.toHaveBeenCalled();
  });

  it("desiste em 3 s quando o núcleo não responde", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_u: string, init?: RequestInit) => new Promise<Response>((_r, rejeitar) => {
      init?.signal?.addEventListener("abort", () => rejeitar(new DOMException("abortado", "AbortError")));
    })));
    const pendente = new Ponte(BASE).saude();
    await vi.advanceTimersByTimeAsync(3000);
    expect(await pendente).toBe(false);
  });
});
