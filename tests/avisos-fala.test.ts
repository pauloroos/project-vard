import { describe, it, expect, vi } from "vitest";
import { AvisoPorVez, deveFalarAviso } from "../src/avisos/fala";

describe("AvisoPorVez", () => {
  it("segundo aviso enquanto o primeiro fala é descartado", async () => {
    const vez = new AvisoPorVez();
    let soltar: (() => void) | null = null;
    const pronto = new Promise<void>((r) => { soltar = r; });
    const um = vi.fn(async () => { await pronto; return "um"; });
    const dois = vi.fn(async () => "dois");
    const p1 = vez.executar(um);
    expect(await vez.executar(dois)).toBeNull(); // um por vez: o resto cai
    expect(dois).not.toHaveBeenCalled();
    soltar!();
    expect(await p1).toBe("um");
    expect(await vez.executar(dois)).toBe("dois"); // terminou: o próximo entra
  });

  it("tarefa que falha libera a vaga", async () => {
    const vez = new AvisoPorVez();
    await expect(vez.executar(async () => { throw new Error("sem voz"); })).rejects.toThrow("sem voz");
    expect(await vez.executar(async () => "ok")).toBe("ok");
  });
});

describe("deveFalarAviso (evita fala dupla com chamarQuandoPronto)", () => {
  const cfgBase = { falar_avisos: true, nao_falar: false };

  it("retorna true quando falar_avisos ligado e estado final", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "tarefa", estado: "terminou" }, false, false)).toBe(true);
  });

  it("retorna false quando falar_avisos desligado", () => {
    expect(deveFalarAviso({ ...cfgBase, falar_avisos: false }, { tipo: "tarefa", estado: "terminou" }, false, false)).toBe(false);
  });

  it("retorna false quando nao_falar ligado", () => {
    expect(deveFalarAviso({ ...cfgBase, nao_falar: true }, { tipo: "tarefa", estado: "terminou" }, false, false)).toBe(false);
  });

  it("retorna false quando ocupado (boca falando)", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "tarefa", estado: "terminou" }, true, false)).toBe(false);
  });

  it("retorna false para estado intermediário em_andamento", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "tarefa", estado: "em_andamento" }, false, false)).toBe(false);
  });

  it("retorna false para estado intermediário iniciada", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "tarefa", estado: "iniciada" }, false, false)).toBe(false);
  });

  it("reunião só fala quando estado é ata_pronta", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "reuniao", estado: "ata_pronta" }, false, false)).toBe(true);
    expect(deveFalarAviso(cfgBase, { tipo: "reuniao", estado: "em_andamento" }, false, false)).toBe(false);
  });

  it("tarefa durante reunião ativa retorna false", () => {
    expect(deveFalarAviso(cfgBase, { tipo: "tarefa", estado: "terminou" }, false, true)).toBe(false);
  });
});
