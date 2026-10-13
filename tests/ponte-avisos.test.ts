import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte, normalizarAviso } from "../src/conectores/ponte/cliente";

const BASE = "http://127.0.0.1:4700";

describe("Ponte.avisos", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("le_a_lista_e_o_total", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      avisos: [{ id: 1, hora: "10:32:05", tipo: "tarefa", resumo: "Fez o relatório", n: 7, estado: "pronto", lido: false }],
      nao_lidos: 1,
    }), { status: 200 })));
    const r = await new Ponte(BASE).avisos();
    expect(r?.nao_lidos).toBe(1);
    expect(r?.avisos).toEqual([{ id: 1, hora: "10:32:05", tipo: "tarefa", resumo: "Fez o relatório", n: 7, estado: "pronto", lido: false }]);
  });

  it("ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    expect(await new Ponte(BASE).avisos()).toBeNull();
    expect(await new Ponte("").avisos()).toBeNull(); // ponte_url vazio nem tenta a rede
  });
});

describe("Ponte.marcarLidos", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("envia_os_ids_ou_o_corpo_vazio_para_tudo", async () => {
    const corpos: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      corpos.push(String(init?.body));
      return new Response(JSON.stringify({ ok: true, nao_lidos: 0 }), { status: 200 });
    }));
    const p = new Ponte(BASE);
    expect(await p.marcarLidos([3, 4])).toEqual({ ok: true, nao_lidos: 0 });
    expect(await p.marcarLidos()).toEqual({ ok: true, nao_lidos: 0 });
    expect(corpos).toEqual(['{"ids":[3,4]}', "{}"]);
  });

  it("ponte_fora_devolve_null", async () => {
    expect(await new Ponte("").marcarLidos()).toBeNull();
  });
});

describe("Ponte.resultadoTarefa", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("devolve_o_resultado", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ n: 2, estado: "pronto", resumo: "s", texto: "Terminou tudo." }), { status: 200 })));
    expect(await new Ponte(BASE).resultadoTarefa(2)).toEqual({ n: 2, estado: "pronto", resumo: "s", texto: "Terminou tudo." });
  });

  it("404_e_ponte_fora_devolvem_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 404 })));
    expect(await new Ponte(BASE).resultadoTarefa(9)).toBeNull();
    expect(await new Ponte("").resultadoTarefa(9)).toBeNull();
  });
});

describe("normalizarAviso", () => {
  it("exige_id_e_preenche_o_resto_com_padrao", () => {
    expect(normalizarAviso({ id: 1 })).toEqual({ id: 1, hora: "", tipo: "", resumo: "", lido: false });
    expect(normalizarAviso({ hora: "10:00" })).toBeNull();
    expect(normalizarAviso("x")).toBeNull();
  });
});
