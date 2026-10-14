import { describe, it, expect } from "vitest";
import {
  migrarAtalhosWin,
  ATALHOS_ANTIGOS,
  ATALHOS_NOVOS,
  normalizarAtalho,
  type AcaoAtalho,
} from "../src/config/atalhos";

describe("atalhos-win (T16)", () => {
  describe("migracao_converte_padroes_antigos_para_win", () => {
    it("migra todos os padrões antigos da 0.5 para novos da 0.6", () => {
      const entrada = { ...ATALHOS_ANTIGOS };
      const saida = migrarAtalhosWin(entrada);
      for (const acao of Object.keys(ATALHOS_NOVOS) as AcaoAtalho[]) {
        expect(normalizarAtalho(saida[acao])).toBe(normalizarAtalho(ATALHOS_NOVOS[acao]));
      }
    });

    it("migra apenas valores que são exatamente o padrão antigo", () => {
      const entrada = {
        ...ATALHOS_ANTIGOS,
        falar: "Ctrl+Alt+Space", // exato → migra
        parar: "Ctrl+Alt+Q",     // diferente → preserva
      };
      const saida = migrarAtalhosWin(entrada);
      expect(normalizarAtalho(saida.falar)).toBe(normalizarAtalho(ATALHOS_NOVOS.falar));
      expect(saida.parar).toBe("Ctrl+Alt+Q");
    });
  });

  describe("migracao_preserva_personalizados", () => {
    it("não mexe em atalhos personalizados pelo usuário", () => {
      const personalizado = {
        ...ATALHOS_ANTIGOS,
        config: "Ctrl+Shift+P",
        sala: "Win+Alt+F10",
      };
      const saida = migrarAtalhosWin(personalizado);
      expect(saida.config).toBe("Ctrl+Shift+P");
      expect(saida.sala).toBe("Win+Alt+F10");
    });
  });

  describe("migracao_nao_mexe_se_ja_e_win", () => {
    it("preserva atalhos que já usam Super/Win", () => {
      const jaWin = {
        ...ATALHOS_ANTIGOS,
        escuta: "Super+Alt+E",
        naofalar: "Super+Shift+N",
      };
      const saida = migrarAtalhosWin(jaWin);
      expect(saida.escuta).toBe("Super+Alt+E");
      expect(saida.naofalar).toBe("Super+Shift+N");
    });
  });

  describe("atalhos_invalidos_recusados_pela_validacao_existente", () => {
    it("normalizarAtalho recusa combinação sem modificador obrigatório", () => {
      expect(normalizarAtalho("A")).toBeNull();
      expect(normalizarAtalho("Shift+A")).toBeNull();
    });

    it("normalizarAtalho aceita Win+Alt e Win+Shift", () => {
      // ORDEM canônica em atalhos.ts: Ctrl, Alt, Shift, Super
      expect(normalizarAtalho("Super+Alt+L")).toBe("Alt+Super+L");
      expect(normalizarAtalho("Super+Shift+K")).toBe("Shift+Super+K");
    });
  });
});