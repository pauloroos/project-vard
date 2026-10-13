import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { Adiador } from "../src/ui/dock";

describe("Adiador", () => {
  let n: number; let a: Adiador;
  beforeEach(() => { vi.useFakeTimers(); n = 0; a = new Adiador(200, () => { n++; }); });
  afterEach(() => vi.useRealTimers());
  it("varios_pedidos_viram_uma_acao_200ms_depois_do_ultimo", () => {
    a.pedir(); vi.advanceTimersByTime(150); a.pedir(); vi.advanceTimersByTime(150); a.pedir();
    expect(n).toBe(0);
    vi.advanceTimersByTime(200); expect(n).toBe(1);
  });
  it("cancelar_descarta", () => { a.pedir(); a.cancelar(); vi.advanceTimersByTime(1000); expect(n).toBe(0); });
});
