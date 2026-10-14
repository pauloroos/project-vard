import { describe, it, expect, vi } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue(null),
}));
import { AbaAvisos, horaCurta } from "../src/ui/aba-avisos";
import type { Aviso, ResultadoTarefa } from "../src/conectores/ponte/cliente";

// DOM mínimo: o suficiente para a aba (os testes rodam em node, sem navegador).
class No {
  textContent = ""; className = ""; hidden = false; type = ""; id = "";
  filhos: unknown[] = []; ouvintes: Record<string, (() => void)[]> = {};
  set innerHTML(_: string) { this.filhos = []; }
  append(...n: unknown[]) { this.filhos.push(...n); }
  addEventListener(t: string, f: () => void) { (this.ouvintes[t] ??= []).push(f); }
  querySelector() { return new No(); }
}
vi.stubGlobal("document", { createElement: () => new No(), createTextNode: (t: string) => ({ texto: t }) });

const aviso = (id: number, extra: Partial<Aviso> = {}): Aviso => ({ id, hora: "10:32:05", tipo: "tarefa", resumo: "fez algo", n: id, lido: false, ...extra });

function porId(no: No, id: string): No | null {
  if (no.id === id) return no;
  for (const f of no.filhos) if (f instanceof No) { const a = porId(f, id); if (a) return a; }
  return null;
}

function montar(lista: Aviso[] | null, resultado: ResultadoTarefa | null = null) {
  const raiz = new No();
  let aoEvento: ((tipo: string, dados: unknown) => void) | null = null;
  let encerrou = false;
  const deps = {
    avisos: vi.fn(async () => (lista === null ? null : { avisos: lista, nao_lidos: lista.filter((a) => !a.lido).length })),
    marcarLidos: vi.fn(async () => ({ ok: true, nao_lidos: 0 })),
    resultadoTarefa: vi.fn(async () => resultado),
    eventos: vi.fn((cb: (tipo: string, dados: unknown) => void) => { aoEvento = cb; return () => { encerrou = true; }; }),
  };
  const aba = new AbaAvisos(raiz as unknown as HTMLElement, deps);
  return { aba, raiz, deps, evento: (tipo: string, dados: unknown) => aoEvento?.(tipo, dados), encerrou: () => encerrou };
}

describe("AbaAvisos", () => {
  it("render_a_lista_com_texto_e_destaca_o_nao_lido", async () => {
    const t = montar([aviso(1), aviso(2, { lido: true, tipo: "reuniao", resumo: "Sala 2", n: undefined })]);
    await t.aba.montar();
    await t.aba.carregar();
    const lista = porId(t.raiz, "avi-lista")!;
    expect(lista.filhos).toHaveLength(2);
    const l1 = lista.filhos[0] as No;
    expect(l1.className).toBe("aviso-linha novo");
    expect(l1.filhos.map((f) => (f as No).textContent)).toEqual(["10:32", "Tarefa 1", "fez algo", "ver resultado"]);
    const l2 = lista.filhos[1] as No;
    expect(l2.className).toBe("aviso-linha");
    expect(l2.filhos.map((f) => (f as No).textContent)).toEqual(["10:32", "Reunião", "Sala 2"]);
    expect((porId(t.raiz, "avi-msg") as No).textContent).toBe("");
  });

  it("lista_vazia_mostra_nenhum_aviso", async () => {
    const t = montar([]);
    await t.aba.montar();
    await t.aba.carregar();
    expect((porId(t.raiz, "avi-msg") as No).textContent).toBe("Nenhum aviso");
    expect((porId(t.raiz, "avi-lista") as No).filhos).toHaveLength(0);
  });

  it("ponte_fora_mostra_o_aviso_e_nao_quebra", async () => {
    const t = montar(null);
    await t.aba.montar();
    await t.aba.carregar();
    expect((porId(t.raiz, "avi-msg") as No).textContent).toBe("Ponte fora do ar");
  });

  it("ver_resultado_mostra_o_texto_no_bloco_somente_com_textContent", async () => {
    const t = montar([aviso(3)], { n: 3, estado: "pronto", resumo: "fez algo", texto: "Terminou tudo.\nSegunda linha." });
    await t.aba.montar();
    await t.aba.carregar();
    const botao = (porId(t.raiz, "avi-lista")!.filhos[0] as No).filhos[3] as No;
    botao.ouvintes.click[0]();
    await new Promise((r) => setTimeout(r, 0));
    expect(t.deps.resultadoTarefa).toHaveBeenCalledWith(3);
    const bloco = porId(t.raiz, "avi-resultado")!;
    expect(bloco.hidden).toBe(false);
    expect(bloco.textContent).toBe("Terminou tudo.\nSegunda linha.");
  });

  it("ver_resultado_com_ponte_fora_mostra_mensagem", async () => {
    const t = montar([aviso(3)], null);
    await t.aba.montar();
    await t.aba.carregar();
    const botao = ((porId(t.raiz, "avi-lista") as No).filhos[0] as No).filhos[3] as No;
    botao.ouvintes.click[0]();
    await new Promise((r) => setTimeout(r, 0));
    expect((porId(t.raiz, "avi-resultado") as No).textContent).toBe("A ponte não respondeu.");
  });

  it("marcar_tudo_chama_a_ponte_e_atualiza_os_lidos", async () => {
    const t = montar([aviso(1), aviso(2)]);
    await t.aba.montar();
    await t.aba.carregar();
    ((t.raiz.filhos[0]) as No).ouvintes.click[0](); // o botão "Marcar tudo como lido"
    await new Promise((r) => setTimeout(r, 0));
    expect(t.deps.marcarLidos).toHaveBeenCalled();
    const lista = porId(t.raiz, "avi-lista")!;
    expect((lista.filhos[0] as No).className).toBe("aviso-linha");
    expect((lista.filhos[1] as No).className).toBe("aviso-linha");
  });

  it("ativar_assina_os_eventos_e_desativar_encerra", async () => {
    const t = montar([]);
    await t.aba.montar();
    t.aba.ativar();
    t.evento("oficina", { id: 9, hora: "11:00:00", n: 9, resumo: "novo" });
    const lista = porId(t.raiz, "avi-lista")!;
    expect(lista.filhos).toHaveLength(1);
    expect((lista.filhos[0] as No).className).toBe("aviso-linha novo");
    t.evento("ping", { qualquer: true }); // não é aviso: ignora
    expect(lista.filhos).toHaveLength(1);
    t.aba.desativar();
    expect(t.encerrou()).toBe(true);
  });
});

describe("horaCurta", () => {
  it("corta_os_segundos_e_aceita_hora_curta", () => {
    expect(horaCurta("10:32:05")).toBe("10:32");
    expect(horaCurta("09:00")).toBe("09:00");
    expect(horaCurta("tarde")).toBe("tarde");
  });
});
