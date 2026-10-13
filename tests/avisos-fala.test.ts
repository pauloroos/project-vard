import { describe, it, expect, vi } from "vitest";
import { AvisoPorVez } from "../src/avisos/fala";

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
