import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { invoke } from "@tauri-apps/api/core";
import { validarHabilidades, lerHabilidades, gravarHabilidades, HABILIDADES_PADRAO } from "../src/config/habilidades";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const casos = JSON.parse(readFileSync("tests/fixtures/habilidades/contrato.json", "utf8")) as { nome: string; valido: boolean; valor: unknown }[];

describe("contrato compartilhado de habilidades", () => {
  for (const caso of casos) it(caso.nome, () => {
    if (caso.valido) expect(() => validarHabilidades(caso.valor)).not.toThrow();
    else expect(() => validarHabilidades(caso.valor)).toThrow();
  });
});

describe("persistência de habilidades", () => {
  beforeEach(() => vi.mocked(invoke).mockReset());
  it("arquivo ausente devolve padrão independente", async () => {
    vi.mocked(invoke).mockResolvedValue(null);
    const cfg = await lerHabilidades();
    cfg.desligadas.push("computador");
    expect(HABILIDADES_PADRAO.desligadas).toEqual([]);
    expect(await lerHabilidades()).toEqual(HABILIDADES_PADRAO);
  });
  it("valida leitura e gravação antes do invoke", async () => {
    vi.mocked(invoke).mockResolvedValue({ versao: 2 });
    await expect(lerHabilidades()).rejects.toThrow();
    vi.mocked(invoke).mockClear();
    await expect(gravarHabilidades({ ...HABILIDADES_PADRAO, versao: 2 } as never)).rejects.toThrow();
    expect(invoke).not.toHaveBeenCalled();
    await gravarHabilidades(structuredClone(HABILIDADES_PADRAO));
    expect(invoke).toHaveBeenCalledWith("gravar_habilidades", { valor: HABILIDADES_PADRAO });
  });
});
