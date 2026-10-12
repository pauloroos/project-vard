import { describe, it, expect, vi, beforeEach } from "vitest";
import { Conversa } from "../src/fala/conversa";
import { FALAS } from "../src/fala/falas";
import { CONFIG_PADRAO } from "../src/config/config";

const WAV = new ArrayBuffer(8);

describe("conversa", () => {
  let oj: { perguntar: ReturnType<typeof vi.fn>; sintetizar: ReturnType<typeof vi.fn> };
  let boca: { falando: boolean; tocar: ReturnType<typeof vi.fn>; parar: ReturnType<typeof vi.fn> };
  let estados: string[];
  let ultimaFala: string | null;
  let c: Conversa;

  beforeEach(() => {
    oj = { perguntar: vi.fn().mockResolvedValue("Agora são 13h."), sintetizar: vi.fn().mockResolvedValue(WAV) };
    boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    estados = []; ultimaFala = null;
    c = new Conversa({
      oj, boca, config: CONFIG_PADRAO,
      falas: async (t: string) => { ultimaFala = t; return WAV; },
      aoEstado: (e) => estados.push(e),
    });
  });

  it("texto sem o nome é descartado sem chamar o agente", async () => {
    await c.aoTextoTranscrito("abre o youtube", false);
    expect(oj.perguntar).not.toHaveBeenCalled();
  });
  it("push-to-talk dispensa o nome", async () => {
    await c.aoTextoTranscrito("abre o youtube", true);
    expect(oj.perguntar).toHaveBeenCalledOnce();
  });
  it("fluxo completo: pensando, falando, repouso", async () => {
    oj.perguntar.mockResolvedValue("Aberto, senhor.");
    await c.aoTextoTranscrito("Vard, abre o youtube", false);
    expect(estados).toEqual(["pensando", "falando", "repouso"]);
    expect(boca.tocar).toHaveBeenCalledOnce();
    expect(oj.sintetizar).toHaveBeenCalledWith("Aberto, senhor.", CONFIG_PADRAO.voz, CONFIG_PADRAO.velocidade);
  });
  it("manda instrução de formato e o comando sem o nome", async () => {
    await c.aoTextoTranscrito("Vard, que horas são", false);
    const msgs = oj.perguntar.mock.calls[0][0];
    expect(msgs[0]).toEqual({ role: "system", content: CONFIG_PADRAO.instrucao_formato });
    expect(msgs[msgs.length - 1]).toEqual({ role: "user", content: "que horas são" });
  });
  it("histórico guarda no máximo 10 trocas", async () => {
    for (let i = 0; i < 12; i++) await c.aoTextoTranscrito("pergunta " + i, true);
    expect(c.historico.length).toBe(20);
    expect(c.historico[0].content).toBe("pergunta 2");
  });
  it("só o nome vira saudação fixa", async () => {
    await c.aoTextoTranscrito("Vard", false);
    expect(oj.perguntar).not.toHaveBeenCalled();
    expect(ultimaFala).toBe(FALAS.saudacao);
  });
  it("ignora texto enquanto a boca fala", async () => {
    boca.falando = true;
    await c.aoTextoTranscrito("Vard, oi", false);
    expect(oj.perguntar).not.toHaveBeenCalled();
  });
  it("rota que precisa da ponte, sem ponte, fala semPonte", async () => {
    await c.aoTextoTranscrito("Vard, o que você está vendo", false);
    expect(ultimaFala).toBe(FALAS.semPonte);
  });
  it("openjarvis_fora_e_volta", async () => {
    await c.aoHealth(false, false);
    expect(c.estado).toBe("fora");
    expect(boca.tocar).toHaveBeenCalledTimes(1);
    await c.aoHealth(false, false);
    expect(boca.tocar).toHaveBeenCalledTimes(1);
    await c.aoHealth(true, true);
    expect(c.estado).toBe("repouso");
  });
  it("fala desligada no OpenJarvis mostra ajuda", async () => {
    await c.aoHealth(true, false);
    expect(c.estado).toBe("erro");
    expect(c.detalhe).toContain("fala");
  });
  it("erro do agente vira fala fixa curta, sem texto técnico", async () => {
    oj.perguntar.mockRejectedValue(new Error("HTTP 500 <html>"));
    await c.aoTextoTranscrito("Vard, oi", false);
    expect(ultimaFala).toBe(FALAS.erroModelo);
    expect(c.estado).toBe("repouso");
  });
  it("interromper para a boca e volta ao repouso", () => {
    c.interromper();
    expect(boca.parar).toHaveBeenCalled();
    expect(c.estado).toBe("repouso");
  });
});
