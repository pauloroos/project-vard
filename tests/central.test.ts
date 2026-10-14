import { describe, it, expect, vi, beforeEach } from "vitest";
import { CentralAvisos, LIMITE_AVISOS, rotuloDoAviso, type PonteAvisos } from "../src/avisos/central";
import type { Aviso } from "../src/conectores/ponte/cliente";

const aviso = (id: number, extra: Partial<Aviso> = {}): Aviso => ({ id, hora: "10:00", tipo: "tarefa", resumo: "fez", n: id, lido: false, ...extra });

function ponteFake(lista: Aviso[] | null, naoLidos: number, lidos: { ok: boolean; nao_lidos: number } | null = { ok: true, nao_lidos: 0 }) {
  return {
    avisos: vi.fn(async () => (lista === null ? null : { avisos: lista, nao_lidos: naoLidos })),
    marcarLidos: vi.fn(async () => lidos),
  } as unknown as Pick<PonteAvisos, "avisos" | "marcarLidos"> & { avisos: ReturnType<typeof vi.fn>; marcarLidos: ReturnType<typeof vi.fn> };
}

describe("CentralAvisos", () => {
  let mudou: number;
  beforeEach(() => { mudou = 0; });

  it("carregar_guarda_a_lista_e_o_total_e_avisa", async () => {
    const p = ponteFake([aviso(1), aviso(2, { lido: true })], 1);
    const c = new CentralAvisos(p);
    c.aoMudar = () => { mudou++; };
    expect(await c.carregar()).toBe(true);
    expect(c.avisos).toHaveLength(2);
    expect(c.naoLidos).toBe(1);
    expect(mudou).toBe(1);
  });

  it("carregar_com_ponte_fora_devolve_false_e_nao_mexe_na_lista", async () => {
    const p = ponteFake(null, 0);
    const c = new CentralAvisos(p);
    expect(await c.carregar()).toBe(false);
    expect(c.avisos).toEqual([]);
    expect(mudou).toBe(0);
  });

  it("evento_novo_entra_com_tipo_mapeado_e_conta_nao_lido", async () => {
    const c = new CentralAvisos(ponteFake([], 0));
    c.aoMudar = () => { mudou++; };
    c.aplicarEvento("oficina", { id: 5, hora: "11:20:00", n: 5, resumo: "terminou", estado: "terminou" });
    expect(c.avisos).toHaveLength(1);
    expect(c.avisos[0]).toMatchObject({ id: 5, tipo: "tarefa", n: 5, resumo: "terminou", lido: false });
    expect(c.naoLidos).toBe(1);
    expect(mudou).toBe(1);
  });

  it("evento_sem_id_e_ignorado", async () => {
    const c = new CentralAvisos(ponteFake([], 0));
    c.aplicarEvento("reuniao", { hora: "11:20:00" });
    expect(c.avisos).toEqual([]);
  });

  it("evento_duplicado_nao_entra_duas_vezes_e_retorna_false", async () => {
    const c = new CentralAvisos(ponteFake([], 0));
    expect(c.aplicarEvento("reuniao", { id: 7, hora: "12:00" })).toBe(true);
    expect(c.aplicarEvento("reuniao", { id: 7, hora: "12:00" })).toBe(false);
    expect(c.avisos).toHaveLength(1);
    expect(c.naoLidos).toBe(1);
  });

  it("evento_em_andamento_retorna_false_e_nao_adiciona", () => {
    const c = new CentralAvisos(ponteFake([], 0));
    const resultado = c.aplicarEvento("oficina", { id: 99, estado: "em_andamento", resumo: "rodando" });
    expect(resultado).toBe(false);
    expect(c.avisos).toHaveLength(0);
    expect(c.naoLidos).toBe(0);
  });

  it("evento_iniciada_retorna_false_e_nao_adiciona", () => {
    const c = new CentralAvisos(ponteFake([], 0));
    const resultado = c.aplicarEvento("oficina", { id: 100, estado: "iniciada", resumo: "começou" });
    expect(resultado).toBe(false);
    expect(c.avisos).toHaveLength(0);
  });

  it("aviso_novo_com_estado_final_retorna_true", () => {
    const c = new CentralAvisos(ponteFake([], 0));
    expect(c.aplicarEvento("oficina", { id: 101, estado: "terminou", resumo: "pronto" })).toBe(true);
    expect(c.avisos).toHaveLength(1);
    expect(c.naoLidos).toBe(1);
  });

  it("aviso_falhou_retorna_true", () => {
    const c = new CentralAvisos(ponteFake([], 0));
    expect(c.aplicarEvento("oficina", { id: 102, estado: "falhou", resumo: "erro" })).toBe(true);
    expect(c.avisos).toHaveLength(1);
  });

  it("aviso_esperando_retorna_true", () => {
    const c = new CentralAvisos(ponteFake([], 0));
    expect(c.aplicarEvento("oficina", { id: 103, estado: "esperando", resumo: "aguardando" })).toBe(true);
    expect(c.avisos).toHaveLength(1);
  });

  it("lista_passa_do_limite_guarda_so_os_ultimos", async () => {
    const c = new CentralAvisos(ponteFake([], 0));
    for (let i = 1; i <= LIMITE_AVISOS + 5; i++) c.aplicarEvento("oficina", { id: i, estado: "terminou" });
    expect(c.avisos).toHaveLength(LIMITE_AVISOS);
    expect(c.avisos[0].id).toBe(6);
    expect(c.avisos[c.avisos.length - 1].id).toBe(LIMITE_AVISOS + 5);
  });

  it("marcar_lidos_sem_ids_marca_tudo", async () => {
    const p = ponteFake([], 0);
    const c = new CentralAvisos(p);
    c.avisos = [aviso(1), aviso(2, { lido: true })];
    c.naoLidos = 1;
    c.aoMudar = () => { mudou++; };
    expect(await c.marcarLidos()).toBe(true);
    expect(p.marcarLidos).toHaveBeenCalledWith(undefined);
    expect(c.avisos.every((a) => a.lido)).toBe(true);
    expect(c.naoLidos).toBe(0);
    expect(mudou).toBe(1);
  });

  it("marcar_lidos_com_ids_so_marca_os_dados", async () => {
    const p = ponteFake([], 0);
    const c = new CentralAvisos(p);
    c.avisos = [aviso(1), aviso(2)];
    c.naoLidos = 2;
    await c.marcarLidos([1]);
    expect(p.marcarLidos).toHaveBeenCalledWith([1]);
    expect(c.avisos[0].lido).toBe(true);
    expect(c.avisos[1].lido).toBe(false);
  });

  it("marcar_lidos_com_ponte_fora_nao_mexe_em_nada", async () => {
    const c = new CentralAvisos(ponteFake([], 0, null));
    c.avisos = [aviso(1)];
    c.naoLidos = 1;
    expect(await c.marcarLidos()).toBe(false);
    expect(c.avisos[0].lido).toBe(false);
    expect(c.naoLidos).toBe(1);
  });
});

describe("rotuloDoAviso", () => {
  it("tarefa_com_e_sem_n", () => {
    expect(rotuloDoAviso(aviso(1, { n: 5 }))).toBe("Tarefa 5");
    expect(rotuloDoAviso(aviso(1, { n: undefined }))).toBe("Tarefa");
  });
  it("reuniao_e_outros", () => {
    expect(rotuloDoAviso(aviso(1, { tipo: "reuniao" }))).toBe("Reunião");
    expect(rotuloDoAviso(aviso(1, { tipo: "xyz" }))).toBe("xyz");
  });
});
