import { describe, expect, it, vi } from "vitest";
import { criarMemoriaSaude, sondarCerebro } from "../src/fala/saude-cerebro";

describe("sondarCerebro", () => {
  it("sem OpenJarvis, o núcleo no ar conta como conectado (cerebro=proprio)", async () => {
    const nucleo = { saude: vi.fn(async () => true) };
    expect(await sondarCerebro(null, nucleo)).toEqual({ ok: true, falaOk: true });
  });

  it("sem OpenJarvis e com o núcleo fora desde o início, fica sem conexão", async () => {
    const nucleo = { saude: vi.fn(async () => false) };
    expect(await sondarCerebro(null, nucleo)).toEqual({ ok: false, falaOk: false });
  });

  it("usa a /saude rápida do núcleo, nunca o /status lento", async () => {
    const nucleo = { saude: vi.fn(async () => true), status: vi.fn(async () => null) };
    await sondarCerebro(null, nucleo);
    expect(nucleo.saude).toHaveBeenCalledTimes(1);
    expect(nucleo.status).not.toHaveBeenCalled();
  });

  it("uma falha isolada depois de estar no ar não derruba; a segunda seguida derruba", async () => {
    const respostas = [true, false, true, false, false];
    const nucleo = { saude: vi.fn(async () => respostas.shift()!) };
    const memoria = criarMemoriaSaude();
    expect((await sondarCerebro(null, nucleo, memoria)).ok).toBe(true);
    expect((await sondarCerebro(null, nucleo, memoria)).ok).toBe(true); // 1ª falha: tolera
    expect((await sondarCerebro(null, nucleo, memoria)).ok).toBe(true); // voltou: zera a contagem
    expect((await sondarCerebro(null, nucleo, memoria)).ok).toBe(true); // 1ª falha de novo
    expect(await sondarCerebro(null, nucleo, memoria)).toEqual({ ok: false, falaOk: false }); // 2ª seguida
  });

  it("com OpenJarvis ativo, segue a saúde e a fala dele", async () => {
    const oj = { saude: vi.fn(async () => true), fala: vi.fn(async () => false) };
    const nucleo = { saude: vi.fn(async () => false) };
    expect(await sondarCerebro(oj, nucleo)).toEqual({ ok: true, falaOk: false });
    expect(nucleo.saude).not.toHaveBeenCalled();
  });
});
