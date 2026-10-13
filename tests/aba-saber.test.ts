import { describe, it, expect, vi } from "vitest";
import { AbaSaber, ETIQUETA_INSTALACAO, categoriasSaber, type DepsAbaSaber } from "../src/ui/aba-saber";
import type { StatusPonte } from "../src/conectores/ponte/cliente";

// DOM mínimo: o suficiente para a aba (os testes rodam em node, sem navegador).
class No {
  textContent = ""; className = ""; id = "";
  filhos: unknown[] = [];
  set innerHTML(_: string) { this.filhos = []; }
  append(...n: unknown[]) { this.filhos.push(...n); }
}
vi.stubGlobal("document", { createElement: () => new No() });

function porId(no: No, id: string): No | null {
  if (no.id === id) return no;
  for (const f of no.filhos) if (f instanceof No) { const a = porId(f, id); if (a) return a; }
  return null;
}

function montar(nome: string, status: StatusPonte | null) {
  const raiz = new No();
  const deps: DepsAbaSaber = { statusPonte: vi.fn(async () => status), nome: () => nome };
  const aba = new AbaSaber(raiz as unknown as HTMLElement, deps);
  return { aba, raiz, deps };
}

const status = { ok: true, modo: "ligado" };

describe("categoriasSaber", () => {
  it("usa_o_nome_configurado_com_primeira_maiuscula", () => {
    expect(categoriasSaber("aurora", true)[0].frases).toEqual(["Aurora, que horas são?", "Aurora, me explica ..."]);
  });
  it("as_sete_categorias_na_ordem_com_duas_ou_tres_frases", () => {
    const c = categoriasSaber("vard", true);
    expect(c.map((x) => x.titulo)).toEqual(["Conversa", "Computador", "Oficina", "Consultas", "Memória", "Reunião", "Sistema"]);
    for (const x of c) expect(x.frases.length).toBeGreaterThanOrEqual(2);
    expect(c.every((x) => x.frases.every((f) => f.startsWith("Vard,")))).toBe(true);
  });
  it("conversa_nunca_ganha_etiqueta", () => {
    expect(categoriasSaber("vard", true)[0].etiqueta).toBeNull();
    expect(categoriasSaber("vard", false)[0].etiqueta).toBeNull();
  });
  it("ponte_fora_as_que_dependem_ganham_a_etiqueta_de_instalacao", () => {
    expect(categoriasSaber("vard", false).map((x) => x.etiqueta)).toEqual([
      null, ETIQUETA_INSTALACAO, ETIQUETA_INSTALACAO, ETIQUETA_INSTALACAO, ETIQUETA_INSTALACAO, ETIQUETA_INSTALACAO, ETIQUETA_INSTALACAO,
    ]);
  });
  it("ponte_no_ar_ninguem_ganha_etiqueta", () => {
    expect(categoriasSaber("vard", true).every((x) => x.etiqueta === null)).toBe(true);
  });
});

describe("AbaSaber", () => {
  it("render_sete_blocos_com_titulo_frases_e_etiqueta_quando_a_ponte_esta_fora", async () => {
    const t = montar("aurora", null);
    t.aba.montar();
    await t.aba.ativar();
    expect(t.deps.statusPonte).toHaveBeenCalled();
    const caixa = porId(t.raiz, "saber-categorias")!;
    expect(caixa.filhos).toHaveLength(7);
    const conversa = caixa.filhos[0] as No;
    const cabecalhoConversa = conversa.filhos[0] as No;
    expect(cabecalhoConversa.filhos.map((f) => (f as No).textContent)).toEqual(["Conversa"]); // sem etiqueta
    const computador = caixa.filhos[1] as No;
    const cabecalho = computador.filhos[0] as No;
    expect(cabecalho.filhos.map((f) => (f as No).textContent)).toEqual(["Computador", ETIQUETA_INSTALACAO]);
    const itens = (computador.filhos[1] as No).filhos.map((f) => (f as No).textContent);
    expect(itens).toEqual(["Aurora, abre o YouTube", "Aurora, o que está na minha tela?", "Aurora, organiza as janelas"]);
  });
  it("ponte_no_ar_sai_sem_etiquetas", async () => {
    const t = montar("vard", status);
    t.aba.montar();
    await t.aba.ativar();
    const caixa = porId(t.raiz, "saber-categorias")!;
    for (const bloco of caixa.filhos) expect(((bloco as No).filhos[0] as No).filhos).toHaveLength(1);
  });
  it("resposta_tardia_depois_de_fechar_a_aba_nao_repinta", async () => {
    let liberar!: (s: StatusPonte | null) => void;
    const portao = new Promise<StatusPonte | null>((r) => { liberar = r; });
    const raiz = new No();
    const aba = new AbaSaber(raiz as unknown as HTMLElement, { statusPonte: () => portao, nome: () => "vard" });
    aba.montar();
    const esperando = aba.ativar();
    aba.desativar();
    liberar(status);
    await esperando;
    const caixa = porId(raiz, "saber-categorias")!;
    expect(((caixa.filhos[1] as No).filhos[0] as No).filhos).toHaveLength(2); // segue com o desenho anterior (etiqueta)
  });
});
