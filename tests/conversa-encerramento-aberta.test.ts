import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DepsConversa } from "../src/fala/conversa";
import { Conversa } from "../src/fala/conversa";
import { CONFIG_PADRAO } from "../src/config/config";

const WAV = new ArrayBuffer(8);

describe("conversa: encerramento e conversa aberta (defeito B)", () => {
  let oj: DepsConversa["oj"];
  let boca: DepsConversa["boca"];
  let aoDesligarConversaAberta: () => void;
  let aoLigarConversaAberta: () => void;
  let desligarChamado: number;
  let ligarChamado: number;
  let c: Conversa;

  beforeEach(() => {
    oj = {
      perguntar: vi.fn().mockResolvedValue("ok"),
      sintetizar: vi.fn().mockResolvedValue(WAV),
    } as unknown as DepsConversa["oj"];
    boca = {
      falando: false,
      tocar: vi.fn().mockResolvedValue(undefined),
      parar: vi.fn(),
    } as unknown as DepsConversa["boca"];
    desligarChamado = 0;
    ligarChamado = 0;
    aoDesligarConversaAberta = () => { desligarChamado++; };
    aoLigarConversaAberta = () => { ligarChamado++; };
    const deps: DepsConversa = {
      oj,
      boca,
      config: CONFIG_PADRAO,
      falas: async () => WAV,
      aoDesligarConversaAberta,
      aoLigarConversaAberta,
    };
    c = new Conversa(deps);
  });

  it("frase de encerramento chama aoDesligarConversaAberta (defeito B)", async () => {
    await c.aoTextoTranscrito("Vard, pode parar de me ouvir", false);
    expect(desligarChamado).toBe(1);
  });

  it("frase 'fica me ouvindo' chama aoLigarConversaAberta sem duplicar", async () => {
    await c.aoTextoTranscrito("Vard, fica me ouvindo", false);
    expect(ligarChamado).toBe(1);
  });

  it("encerramento funciona mesmo sem nome quando pushToTalk", async () => {
    await c.aoTextoTranscrito("pode parar de me ouvir", true);
    expect(desligarChamado).toBe(1);
  });

  it("ativação funciona mesmo sem nome quando pushToTalk", async () => {
    await c.aoTextoTranscrito("fica me ouvindo", true);
    expect(ligarChamado).toBe(1);
  });
});