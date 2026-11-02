import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => undefined) }));

import { CONFIG_PADRAO, type Config } from "../src/config/config";
import { Hud } from "../src/ui/hud";

function montar(parcial: Partial<Config>) {
  const raiz = document.createElement("div");
  raiz.innerHTML = '<div id="dica"></div><div id="botoes"></div><div id="resposta"></div>';
  const hud = new Hud({ ...CONFIG_PADRAO, ...parcial }, raiz);
  const botao = raiz.querySelector<HTMLButtonElement>('button[aria-label="Abrir a conversa em texto"]')!;
  return { hud, botao };
}

describe("botão da conversa em texto (interface do OpenJarvis)", () => {
  it("fica escondido sem o OpenJarvis e aparece ao ligar", () => {
    const { hud, botao } = montar({ cerebro: "proprio", usar_openjarvis: false });
    expect(botao.hidden).toBe(true);
    hud.setTextoDisponivel(true);
    expect(botao.hidden).toBe(false);
  });

  it("aparece com o OpenJarvis como cérebro", () => {
    expect(montar({ cerebro: "openjarvis", usar_openjarvis: false }).botao.hidden).toBe(false);
  });
});
