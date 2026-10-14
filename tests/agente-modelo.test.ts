import { describe, it, expect } from "vitest";
import { escolherModelo, validarModeloAgente } from "../src/conectores/agente-modelo";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";

function cfgComAgente(
  agente: "claude" | "codex" | "opencode" | "agy",
  padrao: string,
  modelos: string[],
): PaineisConfig {
  return {
    ...PAINEIS_PADRAO,
    agentes: {
      ...PAINEIS_PADRAO.agentes,
      [agente]: { padrao, modelos },
    },
  };
}

describe("agente-modelo (T9)", () => {
  describe("escolherModelo", () => {
    it("pedido explícito válido retorna modelo", () => {
      const cfg = cfgComAgente("claude", "sonnet", ["sonnet", "opus"]);
      const r = escolherModelo("claude", cfg, "opus");
      expect(r.modelo).toBe("opus");
      expect(r.aviso).toBeUndefined();
    });

    it("pedido explícito inválido lança erro", () => {
      const cfg = cfgComAgente("claude", "sonnet", ["sonnet", "opus"]);
      expect(() => escolherModelo("claude", cfg, "haiku")).toThrow(/não está na lista/);
    });

    it("sem pedido usa padrão", () => {
      const cfg = cfgComAgente("codex", "gpt-4o", ["gpt-4o", "o1"]);
      const r = escolherModelo("codex", cfg);
      expect(r.modelo).toBe("gpt-4o");
      expect(r.aviso).toBeUndefined();
    });

    it("sem pedido, padrão vazio, lista com um → usa único", () => {
      const cfg = cfgComAgente("opencode", "", ["mimo-v2"]);
      const r = escolherModelo("opencode", cfg);
      expect(r.modelo).toBe("mimo-v2");
      expect(r.aviso).toBeUndefined();
    });

    it("sem pedido, padrão vazio, lista vazia → erro", () => {
      const cfg = cfgComAgente("agy", "", []);
      expect(() => escolherModelo("agy", cfg)).toThrow(/nenhum modelo configurado/);
    });

    it("sem pedido, padrão vazio, lista com vários → sugere primeiro", () => {
      const cfg = cfgComAgente("claude", "", ["sonnet", "opus", "haiku"]);
      const r = escolherModelo("claude", cfg);
      expect(r.modelo).toBe("sonnet");
      expect(r.aviso).toContain("sugestão");
    });
  });

  describe("validarModeloAgente", () => {
    it("modelo na lista retorna true", () => {
      const cfg = cfgComAgente("claude", "sonnet", ["sonnet", "opus"]);
      expect(validarModeloAgente("claude", "opus", cfg)).toBe(true);
    });

    it("modelo padrão retorna true", () => {
      const cfg = cfgComAgente("claude", "sonnet", []);
      expect(validarModeloAgente("claude", "sonnet", cfg)).toBe(true);
    });

    it("modelo desconhecido retorna false", () => {
      const cfg = cfgComAgente("claude", "sonnet", ["sonnet"]);
      expect(validarModeloAgente("claude", "haiku", cfg)).toBe(false);
    });

    it("agente desconhecido retorna false", () => {
      const cfg = cfgComAgente("claude", "sonnet", ["sonnet"]);
      expect(validarModeloAgente("desconhecido" as any, "sonnet", cfg)).toBe(false);
    });
  });
});