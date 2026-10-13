import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Revelador } from "../src/ui/revelador";

describe("Revelador (compacto)", () => {
  let vis: boolean[];
  let r: Revelador;
  beforeEach(() => { vi.useFakeTimers(); vis = []; r = new Revelador(2000, (v) => vis.push(v)); });
  afterEach(() => { vi.useRealTimers(); });

  it("aparece_e_some_2s_depois", () => {
    r.entrou(); expect(vis).toEqual([true]);
    r.saiu(); vi.advanceTimersByTime(1999); expect(vis).toEqual([true]);
    vi.advanceTimersByTime(1); expect(vis).toEqual([true, false]);
  });
  it("volta_antes_cancela", () => {
    r.entrou(); r.saiu(); vi.advanceTimersByTime(1500); r.entrou(); vi.advanceTimersByTime(5000);
    expect(vis).toEqual([true, true]);
  });
});
