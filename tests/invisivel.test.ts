import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Invisibilidade } from "../src/ui/invisivel";

describe("Invisibilidade", () => {
  let vis: boolean[]; let i: Invisibilidade;
  beforeEach(() => { vi.useFakeTimers(); vis = []; i = new Invisibilidade((v) => vis.push(v), 1500); });
  afterEach(() => vi.useRealTimers());

  it("modo_desligado_sempre_visivel", () => {
    i.definirModo(false); i.definirEstado("repouso"); i.definirCanal(false);
    expect(i.visivel()).toBe(true); expect(vis).toEqual([]); // nada a aplicar: já era visível
  });
  it("ligar_o_modo_esconde_apos_o_atraso", () => {
    i.definirModo(true); expect(vis).toEqual([]);
    vi.advanceTimersByTime(1500); expect(vis).toEqual([false]); expect(i.visivel()).toBe(false);
  });
  it("conversa_revela_e_o_fim_esconde", () => {
    i.definirModo(true); vi.advanceTimersByTime(1500);
    i.definirEstado("ouvindo"); expect(vis).toEqual([false, true]);
    i.definirEstado("pensando"); i.definirEstado("falando"); expect(vis).toEqual([false, true]);
    i.definirEstado("repouso"); vi.advanceTimersByTime(1499); expect(i.visivel()).toBe(true);
    vi.advanceTimersByTime(1); expect(vis).toEqual([false, true, false]);
  });
  it("canal_segura_depois_do_repouso", () => {
    i.definirModo(true); vi.advanceTimersByTime(1500);
    i.definirEstado("ouvindo"); i.definirCanal(true); i.definirEstado("repouso");
    vi.advanceTimersByTime(5000); expect(i.visivel()).toBe(true);
    i.definirCanal(false); vi.advanceTimersByTime(1500); expect(i.visivel()).toBe(false);
  });
  it("motivo_que_volta_cancela_o_atraso", () => {
    i.definirModo(true); vi.advanceTimersByTime(1500);
    i.definirEstado("ouvindo"); i.definirEstado("repouso"); vi.advanceTimersByTime(1000);
    i.definirEstado("ouvindo"); vi.advanceTimersByTime(2000); expect(i.visivel()).toBe(true);
  });
  it("revelar_a_mao_segura_ate_revelar_de_novo", () => {
    i.definirModo(true); vi.advanceTimersByTime(1500);
    i.alternarRevelacao(); expect(i.visivel()).toBe(true);
    i.definirEstado("ouvindo"); i.definirEstado("repouso"); vi.advanceTimersByTime(5000); expect(i.visivel()).toBe(true);
    i.alternarRevelacao(); expect(i.visivel()).toBe(false); // esconder à mão é imediato
  });
  it("desligar_o_modo_mostra_na_hora_e_apaga_o_revelado", () => {
    i.definirModo(true); vi.advanceTimersByTime(1500); i.alternarRevelacao(); i.definirModo(false);
    expect(i.visivel()).toBe(true);
    i.definirModo(true); vi.advanceTimersByTime(1500); expect(i.visivel()).toBe(false);
  });
});
