import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte } from "../src/conectores/ponte/cliente";

const BASE = "http://127.0.0.1:4700";

describe("Ponte.andamento", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("le_a_lista_de_tarefas_rodando", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      total: 2,
      tarefas: [
        { n: 1, ferramenta: "codex", quem: "Codex", estado: "rodando", resumo: "cria um teste", segundos: 40 },
        { n: 2, ferramenta: "claude", quem: "Claude", estado: "esperando", resumo: "issues do Linear", segundos: 130 },
      ],
    }), { status: 200 })));
    const r = await new Ponte(BASE).andamento();
    expect(r?.total).toBe(2);
    expect(r?.tarefas).toEqual([
      { n: 1, ferramenta: "codex", quem: "Codex", estado: "rodando", resumo: "cria um teste", segundos: 40 },
      { n: 2, ferramenta: "claude", quem: "Claude", estado: "esperando", resumo: "issues do Linear", segundos: 130 },
    ]);
  });

  it("sem_tarefas_devolve_lista_vazia", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ total: 0, tarefas: [] }), { status: 200 })));
    expect(await new Ponte(BASE).andamento()).toEqual({ total: 0, tarefas: [] });
  });

  it("ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    expect(await new Ponte(BASE).andamento()).toBeNull();
    expect(await new Ponte("").andamento()).toBeNull(); // ponte_url vazio nem tenta a rede
  });

  it("http_ruim_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 503 })));
    expect(await new Ponte(BASE).andamento()).toBeNull();
  });
});
