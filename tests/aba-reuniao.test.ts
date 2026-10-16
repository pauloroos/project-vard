import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { AbaReuniao, acoesDaReuniao, formatarDataHora, formatarDuracao } from "../src/ui/aba-reuniao";
import type { ReuniaoDaLista, ResultadoReuniao, StatusReuniao } from "../src/conectores/ponte/cliente";

// DOM mínimo: o suficiente para a aba (os testes rodam em node, sem navegador).
class No {
  textContent = ""; className = ""; hidden = false; type = ""; id = ""; disabled = false;
  filhos: unknown[] = []; ouvintes: Record<string, (() => void)[]> = {};
  set innerHTML(_: string) { this.filhos = []; }
  append(...n: unknown[]) { this.filhos.push(...n); }
  addEventListener(t: string, f: () => void) { (this.ouvintes[t] ??= []).push(f); }
}
beforeEach(() => vi.stubGlobal("document", { createElement: () => new No() }));
afterEach(() => vi.unstubAllGlobals());

function porId(no: No, id: string): No | null {
  if (no.id === id) return no;
  for (const f of no.filhos) if (f instanceof No) { const a = porId(f, id); if (a) return a; }
  return null;
}

/** Encontra o container de botões da ponte (div.acoes dentro da raiz, não dentro do pacote). */
function caixaDeBotoes(raiz: No): No {
  // A caixa de botões da ponte é a div.acoes que NÃO está dentro de #reu-pacote
  for (const f of raiz.filhos) {
    if (f instanceof No && f.className === "acoes") return f;
  }
  throw new Error("caixa de botões não encontrada");
}

function montar(st: StatusReuniao | null, lista: ReuniaoDaLista[] | null = null, r: ResultadoReuniao | null = { ok: true, frase: "ok" }) {
  const raiz = new No();
  const deps = {
    reuniaoStatus: vi.fn(async () => st),
    iniciarReuniao: vi.fn(async () => r),
    encerrarReuniao: vi.fn(async () => r),
    listaReuniao: vi.fn(async () => lista),
    gerarAta: vi.fn(async () => r),
  };
  return { aba: new AbaReuniao(raiz as unknown as HTMLElement, deps), raiz, deps };
}

const reuniao = (extra: Partial<ReuniaoDaLista> = {}): ReuniaoDaLista =>
  ({ pasta: "2026-10-13_1500", inicio: "2026-10-13T15:00:00", fim: "2026-10-13T16:05:00", duracao_s: 3900, ata: false, relatorio: false, ...extra });

describe("acoesDaReuniao", () => {
  it("iniciar_so_sem_reuniao_e_encerrar_so_com", () => {
    expect(acoesDaReuniao(false)).toEqual({ iniciar: true, encerrar: false, ata: true, relatorio: true });
    expect(acoesDaReuniao(true)).toEqual({ iniciar: false, encerrar: true, ata: true, relatorio: true });
  });
  it("ponte_fora_nada", () => { expect(acoesDaReuniao(null)).toEqual({ iniciar: false, encerrar: false, ata: false, relatorio: false }); });
});

describe("formatarDuracao", () => {
  it("formata_horas_minutos_e_segundos", () => {
    expect(formatarDuracao(3900)).toBe("1 h 05 min");
    expect(formatarDuracao(3600)).toBe("1 h 00 min");
    expect(formatarDuracao(300)).toBe("5 min");
    expect(formatarDuracao(45)).toBe("45 s");
    expect(formatarDuracao(0)).toBe("0 s");
    expect(formatarDuracao(-3)).toBe("0 s");
    expect(formatarDuracao(NaN)).toBe("0 s");
  });
});

describe("formatarDataHora", () => {
  it("formata_iso_e_devolve_texto_ruim_como_esta", () => {
    expect(formatarDataHora("2026-10-13T15:00:00")).toBe("13/10/2026 15:00");
    expect(formatarDataHora("2026-01-02T03:04:05")).toBe("02/01/2026 03:04");
    expect(formatarDataHora("amanhã")).toBe("amanhã");
    expect(formatarDataHora("")).toBe("");
  });
});

describe("AbaReuniao", () => {
  it("render_o_estado_e_a_ultima_reuniao_com_textContent", async () => {
    const t = montar({ ativa: false }, [reuniao({ ata: true, relatorio: false })]);
    await t.aba.montar();
    await t.aba.carregar();
    expect((porId(t.raiz, "reu-estado") as No).textContent).toBe("Nenhuma reunião em andamento.");
    const ultima = porId(t.raiz, "reu-ultima")!;
    expect(ultima.filhos.map((f) => (f as No).textContent)).toEqual([
      "Última reunião",
      "Data/hora: 13/10/2026 15:00",
      "Duração: 1 h 05 min",
      "Ata: pronta",
      "Relatório: não gerado",
    ]);
  });

  it("reuniao_ativa_muda_o_estado_e_os_botoes", async () => {
    const t = montar({ ativa: true, pasta: "2026-10-13_1500" });
    await t.aba.montar();
    await t.aba.carregar();
    expect((porId(t.raiz, "reu-estado") as No).textContent).toBe("Reunião em andamento (2026-10-13_1500).");
    const botoes = caixaDeBotoes(t.raiz).filhos as No[];
    expect(botoes.map((b) => [b.textContent, b.disabled])).toEqual([
      ["Iniciar", true], ["Encerrar", false], ["Gerar ata", false], ["Gerar relatório", false],
    ]);
    expect(((porId(t.raiz, "reu-ultima") as No).filhos[1] as No).textContent).toBe("Nenhuma reunião registrada.");
  });

  it("ponte_fora_desliga_tudo_e_avisa", async () => {
    const t = montar(null);
    await t.aba.montar();
    await t.aba.carregar();
    expect((porId(t.raiz, "reu-estado") as No).textContent).toBe("Ponte fora do ar ou desligada.");
    const botoes = caixaDeBotoes(t.raiz).filhos as No[];
    expect(botoes.every((b) => b.disabled)).toBe(true);
  });

  it("iniciar_mostra_a_frase_e_recarrega", async () => {
    const t = montar({ ativa: false });
    await t.aba.montar();
    await t.aba.carregar();
    const botoes = caixaDeBotoes(t.raiz).filhos as No[];
    botoes[0].ouvintes.click[0]();
    await new Promise((r) => setTimeout(r, 0));
    expect(t.deps.iniciarReuniao).toHaveBeenCalled();
    expect((porId(t.raiz, "reu-msg") as No).textContent).toBe("ok");
    expect(t.deps.reuniaoStatus).toHaveBeenCalledTimes(2); // carga inicial + depois da ação
  });

  it("gerar_ata_e_relatorio_chamam_a_ponte_com_tipo_e_qual", async () => {
    const t = montar({ ativa: false });
    await t.aba.montar();
    await t.aba.carregar();
    const botoes = caixaDeBotoes(t.raiz).filhos as No[];
    botoes[2].ouvintes.click[0]();
    botoes[3].ouvintes.click[0]();
    await new Promise((r) => setTimeout(r, 0));
    expect(t.deps.gerarAta.mock.calls).toEqual([["ata", "ultima"], ["relatorio", "ultima"]]);
  });

  it("resposta_nula_mostra_que_a_ponte_nao_respondeu", async () => {
    const t = montar({ ativa: false }, null, null);
    await t.aba.montar();
    await t.aba.carregar();
    const botoes = caixaDeBotoes(t.raiz).filhos as No[];
    botoes[0].ouvintes.click[0]();
    await new Promise((r) => setTimeout(r, 0));
    expect((porId(t.raiz, "reu-msg") as No).textContent).toBe("A ponte não respondeu.");
  });

  it("ativar_pergunta_na_hora_e_cinco_segundos_desde_que_aberta", async () => {
    const tick = vi.fn();
    const parar = vi.spyOn(globalThis, "clearInterval");
    vi.stubGlobal("window", { setInterval: vi.fn((_f: () => void, ms: number) => { tick(ms); return 7; }) });
    const t = montar({ ativa: false });
    await t.aba.montar();
    t.aba.ativar();
    await new Promise((r) => setTimeout(r, 0));
    expect(tick).toHaveBeenCalledWith(5000);
    expect(t.deps.reuniaoStatus).toHaveBeenCalledTimes(1);
    t.aba.desativar();
    expect(parar).toHaveBeenCalledWith(7);
    parar.mockRestore();
  });
});