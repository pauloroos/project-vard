import { describe, it, expect, vi } from "vitest";
import { EmAndamento, LIMITE_DICA, linhaDaTarefa, textoDaDica, textoDosSegundos, type PonteAndamento } from "../src/avisos/andamento";
import type { TarefaAndamento } from "../src/conectores/ponte/cliente";

const tarefa = (n: number, extra: Partial<TarefaAndamento> = {}): TarefaAndamento => ({
  n, ferramenta: "codex", quem: "Codex", estado: "rodando", resumo: "cria um teste", segundos: 40, ...extra,
});

function ponteFake(lista: TarefaAndamento[] | null) {
  return {
    andamento: vi.fn(async () => (lista === null ? null : { total: lista.length, tarefas: lista })),
  } as unknown as Pick<PonteAndamento, "andamento"> & { andamento: ReturnType<typeof vi.fn> };
}

describe("EmAndamento", () => {
  it("carregar_guarda_a_lista_e_avisa", async () => {
    const p = ponteFake([tarefa(1), tarefa(2)]);
    const e = new EmAndamento(p);
    let mudou = 0;
    e.aoMudar = () => { mudou++; };
    expect(await e.carregar()).toBe(true);
    expect(e.total).toBe(2);
    expect(mudou).toBe(1);
  });

  it("carregar_com_ponte_fora_devolve_false_e_nao_mexe_na_lista", async () => {
    const e = new EmAndamento(ponteFake(null));
    e.tarefas = [tarefa(1)];
    expect(await e.carregar()).toBe(false);
    expect(e.total).toBe(1);
  });

  it("evento_da_oficina_recarrega_a_lista", async () => {
    const p = ponteFake([tarefa(1)]);
    const e = new EmAndamento(p);
    await e.carregar();
    p.andamento.mockResolvedValueOnce({ total: 0, tarefas: [] }); // terminou: some da ponte
    expect(await e.aplicarEvento("oficina")).toBe(true);
    expect(e.total).toBe(0);
  });

  it("evento_de_outro_tipo_nao_recarrega", async () => {
    const p = ponteFake([tarefa(1)]);
    const e = new EmAndamento(p);
    await e.carregar();
    expect(await e.aplicarEvento("reuniao")).toBe(false);
    expect(p.andamento).toHaveBeenCalledTimes(1);
  });
});

describe("textoDosSegundos", () => {
  it("menos_de_60_fica_em_segundos", () => {
    expect(textoDosSegundos(0)).toBe("0 s");
    expect(textoDosSegundos(40)).toBe("40 s");
    expect(textoDosSegundos(59)).toBe("59 s");
  });
  it("60_ou_mais_vira_minutos", () => {
    expect(textoDosSegundos(60)).toBe("1 min");
    expect(textoDosSegundos(120)).toBe("2 min");
  });
});

describe("linhaDaTarefa", () => {
  it("quem_resumo_e_tempo", () => {
    expect(linhaDaTarefa(tarefa(1, { quem: "Claude", resumo: "issues do Linear", segundos: 40 }))).toBe("Claude: issues do Linear, 40 s");
  });
  it("sem_quem_usa_a_ferramenta", () => {
    expect(linhaDaTarefa(tarefa(1, { quem: "", ferramenta: "codex" }))).toBe("codex: cria um teste, 40 s");
  });
});

describe("textoDaDica", () => {
  it("uma_linha_por_tarefa", () => {
    expect(textoDaDica([])).toBe("");
    expect(textoDaDica([tarefa(1)])).toBe("Codex: cria um teste, 40 s");
    expect(textoDaDica([tarefa(1), tarefa(2)])).toBe("Codex: cria um teste, 40 s\nCodex: cria um teste, 40 s");
  });
  it("passa_do_limite_vira_mais_n", () => {
    const lista = Array.from({ length: LIMITE_DICA + 2 }, (_, i) => tarefa(i + 1));
    const linhas = textoDaDica(lista).split("\n");
    expect(linhas).toHaveLength(LIMITE_DICA + 1);
    expect(linhas[LIMITE_DICA]).toBe("+2");
  });
});
