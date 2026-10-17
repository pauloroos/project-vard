import { describe, it, expect } from "vitest";
import { PERFIS_PRONTOS, validarPerfisProntos } from "../src/ui/perfis-prontos";

describe("perfis-prontos (0.9.4)", () => {
  it("tem entre 6 e 8 perfis", () => {
    expect(PERFIS_PRONTOS.length).toBeGreaterThanOrEqual(6);
    expect(PERFIS_PRONTOS.length).toBeLessThanOrEqual(8);
  });

  it("todos os campos obrigatórios estão preenchidos", () => {
    const erros = validarPerfisProntos(PERFIS_PRONTOS);
    expect(erros).toEqual([]);
  });

  it("ids são únicos e estáveis", () => {
    const ids = PERFIS_PRONTOS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z][a-z0-9-]+$/);
  });

  it("nenhum perfil preenche sobre_usuario", () => {
    for (const p of PERFIS_PRONTOS) {
      expect(p).not.toHaveProperty("sobre_usuario");
    }
  });

  it("textos curtos, sem nomes reais e em PT-BR", () => {
    for (const p of PERFIS_PRONTOS) {
      expect(p.rotulo.length).toBeLessThan(40);
      expect(p.descricao.length).toBeLessThan(80);
      expect(p.tom.length).toBeLessThan(40);
      // Sem nomes próprios conhecidos como palavra inteira (evita falso positivo em "analogias", "pedra" etc.)
      const minusculo = `${p.rotulo} ${p.descricao} ${p.personalidade}`.toLowerCase();
      for (const nome of ["maria", "joão", "ana", "pedro", "carlos", "fernanda"]) {
        const regex = new RegExp(`\\b${nome}\\b`, "i");
        expect(regex.test(minusculo), `nome "${nome}" encontrado em "${p.rotulo}"`).toBe(false);
      }
    }
  });
});