import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync, mkdtempSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { invoke } from "@tauri-apps/api/core";
import { validarHabilidades, lerHabilidades, gravarHabilidades, temHabilidadesLigadas, HABILIDADES_PADRAO } from "../src/config/habilidades";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const casos = JSON.parse(readFileSync("tests/fixtures/habilidades/contrato.json", "utf8")) as { nome: string; valido: boolean; valor: unknown; erro?: string }[];

describe("contrato compartilhado de habilidades", () => {
  for (const caso of casos) it(caso.nome, () => {
    if (caso.valido) expect(() => validarHabilidades(caso.valor)).not.toThrow();
    else if (caso.erro) expect(() => validarHabilidades(caso.valor)).toThrow(caso.erro);
    else expect(() => validarHabilidades(caso.valor)).toThrow();
  });
});

describe("habilidades que o agente deve consultar", () => {
  const receita = { id: "rotina", nome: "Rotina", quando: ["bom dia"], instrucoes: "Consultar agenda.", ligada: true, situacao: "treinada" as const, criada_em: "2026-10-17T12:00:00Z", validada_em: null };
  it("conta receita ligada e fábrica personalizada ligada, nunca desligadas", () => {
    expect(temHabilidadesLigadas(HABILIDADES_PADRAO)).toBe(false);
    expect(temHabilidadesLigadas({ ...HABILIDADES_PADRAO, habilidades: [receita] })).toBe(true);
    expect(temHabilidadesLigadas({ ...HABILIDADES_PADRAO, habilidades: [{ ...receita, ligada: false }] })).toBe(false);
    expect(temHabilidadesLigadas({ ...HABILIDADES_PADRAO, fabrica: { conversa: { instrucoes: "Responda curto." } } })).toBe(true);
    expect(temHabilidadesLigadas({ ...HABILIDADES_PADRAO, desligadas: ["conversa"], fabrica: { conversa: { instrucoes: "Responda curto." } } })).toBe(false);
  });
});

describe("persistência de habilidades", () => {
  beforeEach(() => { vi.mocked(invoke).mockReset(); });
  it("lê arquivo realmente ausente e não compartilha o retorno entre leituras", async () => {
    const pasta = mkdtempSync(join(tmpdir(), "vard-habilidades-"));
    const arquivo = join(pasta, "habilidades.json");
    // Só a fronteira IPC é substituída: cada chamada tenta ler um arquivo real.
    vi.mocked(invoke).mockImplementation(async (comando) => {
      if (comando !== "ler_habilidades") throw new Error(`Comando inesperado: ${comando}`);
      try { return JSON.parse(readFileSync(arquivo, "utf8")); }
      catch (erro) {
        if ((erro as NodeJS.ErrnoException).code === "ENOENT") return null;
        throw erro;
      }
    });
    try {
      expect(existsSync(arquivo)).toBe(false);
      const cfg = await lerHabilidades();
      cfg.desligadas.push("computador");
      cfg.habilidades.push({ id: "mutacao" } as never);
      expect(await lerHabilidades()).toEqual({ versao: 1, habilidades: [], desligadas: [] });
      expect(existsSync(arquivo)).toBe(false);
    } finally { rmSync(pasta, { recursive: true, force: true }); }
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
