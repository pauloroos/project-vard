import { describe, expect, it, vi } from "vitest";
import { sondarCerebro } from "../src/fala/saude-cerebro";

describe("sondarCerebro", () => {
  it("sem OpenJarvis, o núcleo no ar conta como conectado (cerebro=proprio)", async () => {
    const ponte = { status: vi.fn(async () => ({ ok: false, modo: "parado" })) };
    expect(await sondarCerebro(null, ponte)).toEqual({ ok: true, falaOk: true });
  });

  it("sem OpenJarvis e com o núcleo fora, fica sem conexão", async () => {
    const ponte = { status: vi.fn(async () => null) };
    expect(await sondarCerebro(null, ponte)).toEqual({ ok: false, falaOk: false });
  });

  it("com OpenJarvis ativo, segue a saúde e a fala dele", async () => {
    const oj = { saude: vi.fn(async () => true), fala: vi.fn(async () => false) };
    const ponte = { status: vi.fn(async () => null) };
    expect(await sondarCerebro(oj, ponte)).toEqual({ ok: true, falaOk: false });
    expect(ponte.status).not.toHaveBeenCalled();
  });
});
