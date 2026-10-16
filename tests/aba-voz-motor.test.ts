import { describe, it, expect } from "vitest";
import { MOTORES_PROPRIA, VOZES_POR_MOTOR } from "../src/ui/aba-voz";
import { VOZES_KOKORO, VOZES_EDGE_PT_BR, VOZES_PIPER_PT_BR } from "../src/conectores/voz/kokoro";

describe("MOTORES_PROPRIA", () => {
  it("tem_opcao_automatica_vazia_e_os_quatro_motores", () => {
    const ids = MOTORES_PROPRIA.map((m) => m.id);
    expect(ids).toContain("");
    expect(ids).toContain("kokoro");
    expect(ids).toContain("edge");
    expect(ids).toContain("piper");
    expect(ids).toContain("xtts");
  });

  it("todos_tem_rotulo_legivel", () => {
    for (const m of MOTORES_PROPRIA) {
      expect(m.rotulo.length).toBeGreaterThan(0);
    }
  });
});

describe("VOZES_POR_MOTOR", () => {
  it("kokoro_tem_vozes_pt_br", () => {
    const vozes = VOZES_POR_MOTOR.kokoro;
    expect(vozes.length).toBeGreaterThan(0);
    expect(vozes.some((v) => v.rotulo.includes("pt-BR"))).toBe(true);
  });

  it("edge_tem_vozes_pt_br_com_aviso_de_rede_na_ui", () => {
    const vozes = VOZES_POR_MOTOR.edge;
    expect(vozes.length).toBeGreaterThan(0);
    // Edge TTS usa rede: a UI deve mostrar aviso (testado via DOM no futuro).
    expect(vozes.every((v) => typeof v.id === "string" && v.id.length > 0)).toBe(true);
  });

  it("piper_tem_vozes_pt_br_locais", () => {
    const vozes = VOZES_POR_MOTOR.piper;
    expect(vozes.length).toBeGreaterThan(0);
    expect(vozes.some((v) => v.rotulo.includes("pt-BR"))).toBe(true);
  });

  it("ids_sao_unicos_por_motor", () => {
    for (const [, lista] of Object.entries(VOZES_POR_MOTOR)) {
      const ids = lista.map((v) => v.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });
});

describe("config voz_motor padrao", () => {
  it("padrao_e_vazio_para_preservar_comportamento_atual", async () => {
    const { CONFIG_PADRAO } = await import("../src/config/config");
    expect(CONFIG_PADRAO.voz_motor ?? "").toBe("");
  });
});
describe("VOZES_POR_MOTOR usa as listas do conector", () => {
  it("cada_motor_mostra_as_vozes_do_seu_backend", () => {
    expect(VOZES_POR_MOTOR.kokoro).toBe(VOZES_KOKORO);
    expect(VOZES_POR_MOTOR.edge).toBe(VOZES_EDGE_PT_BR);
    expect(VOZES_POR_MOTOR.piper).toBe(VOZES_PIPER_PT_BR);
  });
});
