import { describe, it, expect, vi, afterEach } from "vitest";
import { AbaModelos, agruparModelos, type DepsAbaModelos } from "../src/ui/aba-modelos";
import { OpenJarvis } from "../src/conectores/openjarvis/cliente";

// DOM mínimo: o suficiente para a aba (os testes rodam em node, sem navegador).
class No {
  textContent = ""; className = ""; checked = false; value = ""; name = ""; type = "";
  filhos: unknown[] = []; ouvintes: Record<string, (() => void)[]> = {}; achados = new Map<string, No>();
  set innerHTML(_: string) { this.filhos = []; }
  append(...n: unknown[]) { this.filhos.push(...n); }
  addEventListener(t: string, f: () => void) { (this.ouvintes[t] ??= []).push(f); }
  querySelector(s: string) { if (!this.achados.has(s)) this.achados.set(s, new No()); return this.achados.get(s)!; }
}
vi.stubGlobal("document", { createElement: () => new No(), createTextNode: (t: string) => ({ texto: t }) });

function montar(ids: string[] | Error, status: Awaited<ReturnType<DepsAbaModelos["statusPonte"]>>, modelo = "") {
  const raiz = new No();
  const oj = { modelos: async () => { if (ids instanceof Error) throw ids; return ids; } } as unknown as OpenJarvis;
  const aba = new AbaModelos(raiz as unknown as HTMLElement, modelo, { criarOj: () => oj, statusPonte: async () => status });
  return { aba, raiz, lista: raiz.querySelector("#mod-lista"), reserva: raiz.querySelector("#mod-reserva") };
}
/** Os rótulos (labels) da lista, entrando nos fieldsets: um label tem o rádio em filhos[0] e o texto em filhos[1]. */
const labels = (lista: No): No[] => lista.filhos.flatMap((f) => ((f as No).filhos[0] instanceof No && ((f as No).filhos[0] as No).type === "radio" ? [f as No] : labels(f as No)));
const rotulos = (lista: No) => labels(lista).map((l) => (l.filhos[1] as { texto: string }).texto.trim());
const titulos = (lista: No) => lista.filhos.filter((f) => (f as No).className === "grupo").map((f) => ((f as No).filhos[0] as No).textContent);

describe("AbaModelos", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lista_vazia_oferece_so_o_automatico", async () => {
    const t = montar([], null);
    await t.aba.carregar();
    expect(rotulos(t.lista)).toEqual(["Automático (o primeiro: nenhum)"]);
  });
  it("conector_fora_mostra_o_erro_e_nao_quebra", async () => {
    const t = montar(new Error("HTTP 500"), null);
    await t.aba.carregar();
    expect(t.lista.textContent).toContain("não respondeu");
    expect(t.reserva.textContent).toContain("sem informação de reserva");
  });
  it("modelo_salvo_que_sumiu_aparece_marcado_como_ausente", async () => {
    const t = montar(["a", "b"], null, "c");
    await t.aba.carregar();
    const r = rotulos(t.lista);
    expect(r).toHaveLength(4);
    expect(r[3]).toContain("não está mais no OpenJarvis");
    expect(labels(t.lista)[3].filhos[0]).toMatchObject({ value: "c", checked: true });
    expect(t.aba.escolhido).toBe("c");
  });
  it("escolher_um_modelo_atualiza_escolhido", async () => {
    const t = montar(["a", "b"], null);
    await t.aba.carregar();
    const r = labels(t.lista)[2].filhos[0] as No;
    r.checked = true; r.ouvintes.change[0]();
    expect(t.aba.escolhido).toBe("b");
  });
  it("com_modelos_do_lmstudio_a_lista_vem_em_dois_grupos", async () => {
    const t = montar(["a", "b", "c"], { ok: true, modo: "ligado", modelos_lmstudio: ["b"] });
    await t.aba.carregar();
    expect(titulos(t.lista)).toEqual(["LM Studio (local)", "OmniRouter (nuvem)"]);
    expect(rotulos(t.lista)).toEqual(["Automático (o primeiro: a)", "b", "a", "c"]);
  });
  it("sem_a_ponte_um_grupo_so", async () => {
    const t = montar(["a"], null);
    await t.aba.carregar();
    expect(titulos(t.lista)).toEqual(["Todos"]);
  });
  it("reserva_presente_e_ausente", async () => {
    const com = montar(["a"], { ok: true, modo: "ligado", reserva: "combo/t1" });
    await com.aba.carregar();
    expect(com.reserva.textContent).toBe("Se o principal falhar, o OpenJarvis usa combo/t1.");
    const sem = montar(["a"], { ok: true, modo: "ligado" });
    await sem.aba.carregar();
    expect(sem.reserva.textContent).toBe("A ponte não informa um modelo de reserva.");
  });
  it("modelos_com_data_nao_array_devolve_lista_vazia", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ data: "x" }), { status: 200 })));
    expect(await new OpenJarvis("http://127.0.0.1:8000").modelos()).toEqual([]);
    vi.unstubAllGlobals();
    vi.stubGlobal("document", { createElement: () => new No(), createTextNode: (t: string) => ({ texto: t }) });
  });
  it("definirModelo_durante_a_espera_nao_deixa_cache_obsoleto", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    let liberar!: () => void;
    const portao = new Promise<void>((r) => { liberar = r; });
    const corpos: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/v1/models")) { await portao; return new Response(JSON.stringify({ data: [{ id: "a" }, { id: "b" }] }), { status: 200 }); }
      corpos.push(JSON.parse(String(init?.body)).model);
      return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200 });
    }));
    const oj = new OpenJarvis("http://127.0.0.1:8000", "a");
    const p = oj.perguntar([{ role: "user", content: "oi" }]);
    oj.definirModelo("b");
    liberar();
    await p;
    await oj.perguntar([{ role: "user", content: "oi" }]);
    expect(corpos).toEqual(["b", "b"]);
    vi.unstubAllGlobals();
    vi.stubGlobal("document", { createElement: () => new No(), createTextNode: (t: string) => ({ texto: t }) });
  });
});

describe("agruparModelos", () => {
  it("separa_local_e_nuvem", () => {
    expect(agruparModelos(["a", "b", "c"], ["b"])).toEqual([{ titulo: "LM Studio (local)", ids: ["b"] }, { titulo: "OmniRouter (nuvem)", ids: ["a", "c"] }]);
  });
  it("sem_lista_da_ponte_e_um_grupo_todos", () => {
    expect(agruparModelos(["a"], null)).toEqual([{ titulo: "Todos", ids: ["a"] }]);
  });
  it("so_local_omite_o_grupo_vazio", () => {
    expect(agruparModelos(["a"], ["a"])).toEqual([{ titulo: "LM Studio (local)", ids: ["a"] }]);
  });
});
