import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../src/config/segredos", () => ({
  cofreExiste: vi.fn(),
  cofreLer: vi.fn(),
}));

import { cofreExiste, cofreLer } from "../src/config/segredos";
import {
  parseRef,
  credencialExiste,
  verificarPaineis,
  criarFonteDeVozComCofre,
  resolverCredencialMcp,
} from "../src/conectores/paineis-resolver";
import type { PaineisConfig, Mcp } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { FonteDeVoz } from "../src/conectores/voz/fonte";
import { ErroVoz } from "../src/conectores/voz/cliente";

const mockCofreExiste = vi.mocked(cofreExiste);
const mockCofreLer = vi.mocked(cofreLer);

describe("paineis-resolver (T3)", () => {
  beforeEach(() => {
    mockCofreExiste.mockReset();
    mockCofreLer.mockReset();
  });

  describe("parseRef", () => {
    it("aceita refs válidas", () => {
      expect(parseRef("provedor:suad")).toEqual({ tipo: "provedor", id: "suad" });
      expect(parseRef("voz:kokoro-local")).toEqual({ tipo: "voz", id: "kokoro-local" });
      expect(parseRef("mcp:filesystem")).toEqual({ tipo: "mcp", id: "filesystem" });
    });

    it("recusa tipo desconhecido", () => {
      expect(parseRef("agente:claude")).toBeNull();
      expect(parseRef(":id")).toBeNull();
    });

    it("recusa id vazio ou ref malformada", () => {
      expect(parseRef("provedor:")).toBeNull();
      expect(parseRef("provedor")).toBeNull();
      expect(parseRef("")).toBeNull();
    });
  });

  describe("credencialExiste", () => {
    it("retorna true quando cofre confirma", async () => {
      mockCofreExiste.mockResolvedValue(true);
      expect(await credencialExiste("provedor:suad")).toBe(true);
      expect(mockCofreExiste).toHaveBeenCalledWith("provedor", "suad");
    });

    it("retorna false quando cofre diz não", async () => {
      mockCofreExiste.mockResolvedValue(false);
      expect(await credencialExiste("provedor:suad")).toBe(false);
    });

    it("retorna false para ref inválida sem chamar cofre", async () => {
      expect(await credencialExiste("invalida")).toBe(false);
      expect(mockCofreExiste).not.toHaveBeenCalled();
    });

    it("retorna false quando cofre falha", async () => {
      mockCofreExiste.mockRejectedValue(new Error("cofre indisponível"));
      expect(await credencialExiste("provedor:x")).toBe(false);
    });
  });

  describe("verificarPaineis", () => {
    it("ok quando todas as creds existem", async () => {
      mockCofreExiste.mockResolvedValue(true);
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m", credencial_ref: "provedor:s" }],
        mcps: [{ id: "m", nome: "M", habilitado: true, command: "c", credencial_ref: "mcp:m" }],
      };
      const r = await verificarPaineis(cfg);
      expect(r.ok).toBe(true);
      expect(r.faltantes).toEqual([]);
    });

    it("lista faltantes quando credenciais ausentes", async () => {
      mockCofreExiste.mockResolvedValue(false);
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m", credencial_ref: "provedor:s" }],
        mcps: [{ id: "m", nome: "M", habilitado: true, command: "c", credencial_ref: "mcp:m" }],
      };
      const r = await verificarPaineis(cfg);
      expect(r.ok).toBe(false);
      expect(r.faltantes).toEqual(["provedor:s", "mcp:m"]);
    });

    it("ignora entradas sem credencial_ref", async () => {
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        provedores: [{ id: "s", nome: "S", tipo: "t", url_base: "u", modelo: "m" }],
      };
      const r = await verificarPaineis(cfg);
      expect(r.ok).toBe(true);
      expect(mockCofreExiste).not.toHaveBeenCalled();
    });
  });

  describe("criarFonteDeVozComCofre", () => {
    const factoryMock = (chave: string): FonteDeVoz => ({
      nome: `mock:${chave}`,
      saude: async () => true,
      falar: async () => ({ corpo: new ReadableStream(), taxa: 24000 }),
      falarWav: async () => new ArrayBuffer(0),
    });

    it("falha claro quando credencial ausente", async () => {
      mockCofreLer.mockResolvedValue(null);
      const fonte = await criarFonteDeVozComCofre("elevenlabs", "voz:el", factoryMock);
      expect(fonte.nome).toContain("sem-credencial");
      await expect(fonte.falar("teste", 1)).rejects.toThrow(ErroVoz);
      await expect(fonte.falar("teste", 1)).rejects.toThrow(/credencial ausente/);
    });

    it("falha claro quando nenhuma ref informada", async () => {
      const fonte = await criarFonteDeVozComCofre("gemini", undefined, factoryMock);
      expect(fonte.nome).toContain("sem-credencial");
      await expect(fonte.falarWav("teste", 1)).rejects.toThrow(/credencial ausente/);
    });

    it("passa valor real do cofre para factory quando credencial existe", async () => {
      mockCofreLer.mockResolvedValue("chave-real-elevenlabs");
      const fonte = await criarFonteDeVozComCofre("elevenlabs", "voz:el", factoryMock);
      expect(fonte.nome).toBe("mock:chave-real-elevenlabs");
      expect(await fonte.saude()).toBe(true);
      expect(mockCofreLer).toHaveBeenCalledWith("voz", "el");
    });

    it("falha claro quando cofre_ler lança exceção", async () => {
      mockCofreLer.mockRejectedValue(new Error("cofre indisponível"));
      const fonte = await criarFonteDeVozComCofre("elevenlabs", "voz:el", factoryMock);
      expect(fonte.nome).toContain("sem-credencial");
    });
  });

  describe("resolverCredencialMcp", () => {
    it("retorna null quando mcp sem credencial_ref", async () => {
      const mcp: Mcp = { id: "fs", nome: "FS", habilitado: true, command: "node" };
      expect(await resolverCredencialMcp(mcp)).toBeNull();
      expect(mockCofreLer).not.toHaveBeenCalled();
    });

    it("retorna null quando credencial ausente", async () => {
      mockCofreLer.mockResolvedValue(null);
      const mcp: Mcp = { id: "api", nome: "API", habilitado: true, url: "https://x", credencial_ref: "mcp:api" };
      expect(await resolverCredencialMcp(mcp)).toBeNull();
    });

    it("retorna token real lido do cofre quando credencial existe", async () => {
      mockCofreLer.mockResolvedValue("bearer-token-real");
      const mcp: Mcp = { id: "api", nome: "API", habilitado: true, url: "https://x", credencial_ref: "mcp:api" };
      expect(await resolverCredencialMcp(mcp)).toBe("bearer-token-real");
      expect(mockCofreLer).toHaveBeenCalledWith("mcp", "api");
    });

    it("retorna null quando cofre_ler lança exceção", async () => {
      mockCofreLer.mockRejectedValue(new Error("cofre indisponível"));
      const mcp: Mcp = { id: "api", nome: "API", habilitado: true, url: "https://x", credencial_ref: "mcp:api" };
      expect(await resolverCredencialMcp(mcp)).toBeNull();
    });
  });
});