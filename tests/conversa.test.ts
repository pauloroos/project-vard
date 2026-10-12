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
    expect(c.detalhe).toContain("voz");
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

describe("interromper cancela a pergunta em voo", () => {
  it("resposta tardia não é falada nem entra no histórico", async () => {
    const WAV2 = new ArrayBuffer(8);
    let liberar!: (t: string) => void;
    const oj = {
      perguntar: vi.fn().mockImplementation(() => new Promise<string>((r) => { liberar = r; })),
      sintetizar: vi.fn().mockResolvedValue(WAV2),
    };
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const estados: string[] = [];
    const c = new Conversa({ oj, boca, config: CONFIG_PADRAO, falas: async () => WAV2, aoEstado: (e) => estados.push(e) });
    const p = c.aoTextoTranscrito("Vard, oi", false);
    await Promise.resolve();
    c.interromper();
    liberar("resposta atrasada");
    await p;
    expect(boca.tocar).not.toHaveBeenCalled();
    expect(oj.sintetizar).not.toHaveBeenCalled();
    expect(c.historico.length).toBe(0);
    expect(c.estado).toBe("repouso");
    expect(estados).toEqual(["pensando", "repouso"]);
  });
});

describe("ponte do Vard (opcional)", () => {
  function montar(comPonte: boolean) {
    const oj = { perguntar: vi.fn().mockResolvedValue("x"), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const falas: string[] = [];
    const estados: string[] = [];
    const ponte = { ver: vi.fn().mockResolvedValue("Um editor de código aberto."), modo: vi.fn().mockResolvedValue(true) };
    const capturar = vi.fn().mockResolvedValue("QUJD");
    const abrirMicrofone = vi.fn();
    const fecharMicrofone = vi.fn();
    const c = new Conversa({
      oj, boca, config: CONFIG_PADRAO,
      falas: async (t: string) => { falas.push(t); return WAV; },
      aoEstado: (e) => estados.push(e),
      ...(comPonte ? { ponte, capturar, abrirMicrofone, fecharMicrofone } : {}),
    });
    return { c, oj, boca, falas, estados, ponte, capturar, abrirMicrofone, fecharMicrofone };
  }

  it("sem_ponte: ver vira fala semPonte, sem chamar o agente", async () => {
    const m = montar(false);
    await m.c.aoTextoTranscrito("Vard, o que você está vendo", false);
    expect(m.falas).toEqual([FALAS.semPonte]);
    expect(m.oj.perguntar).not.toHaveBeenCalled();
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    expect(m.falas).toEqual([FALAS.semPonte, FALAS.semPonte]);
  });

  it("com_ponte_ver: captura uma vez, ponte.ver e fala a resposta", async () => {
    const m = montar(true);
    await m.c.aoTextoTranscrito("Vard, o que você está vendo", false);
    expect(m.capturar).toHaveBeenCalledOnce();
    expect(m.ponte.ver).toHaveBeenCalledWith("QUJD", "o que você está vendo");
    expect(m.oj.sintetizar).toHaveBeenCalledWith("Um editor de código aberto.", CONFIG_PADRAO.voz, CONFIG_PADRAO.velocidade);
    expect(m.oj.perguntar).not.toHaveBeenCalled();
    expect(m.c.estado).toBe("repouso");
  });

  it("erro 503 da ponte fala a frase fixa do código", async () => {
    const m = montar(true);
    m.ponte.ver.mockRejectedValue(Object.assign(new Error("segredos"), { codigo: "segredos" }));
    await m.c.aoTextoTranscrito("Vard, olha a tela", false);
    expect(m.falas).toEqual([FALAS.erros.segredos]);
    expect(m.c.estado).toBe("repouso");
  });

  it("modo_jogo_fecha_e_reabre", async () => {
    const m = montar(true);
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    expect(m.falas).toEqual([FALAS.modoJogoConfirmar]);
    expect(m.ponte.modo).not.toHaveBeenCalled();
    await m.c.aoTextoTranscrito("sim", false);
    expect(m.ponte.modo).toHaveBeenCalledWith("jogo");
    expect(m.falas).toContain(FALAS.modoJogoAtivado);
    expect(m.c.estado).toBe("jogo");
    expect(m.fecharMicrofone).toHaveBeenCalledOnce();
    await m.c.aoTextoTranscrito("Vard, oi", false); // no jogo ninguém escuta
    expect(m.oj.perguntar).not.toHaveBeenCalled();
    await m.c.aoHealth(false, false); // OpenJarvis parado de propósito: não vira "fora"
    expect(m.c.estado).toBe("jogo");
    await m.c.aoStatusPonte({ modo: "ligando" });
    expect(m.c.estado).toBe("jogo");
    expect(m.abrirMicrofone).not.toHaveBeenCalled();
    await m.c.aoStatusPonte({ modo: "ligado" });
    expect(m.abrirMicrofone).toHaveBeenCalledOnce();
    expect(m.c.estado).toBe("repouso");
    expect(m.falas[m.falas.length - 1]).toBe(FALAS.voltei);
  });

  it("jogo com ponte em erro mostra o detalhe e sai quando volta", async () => {
    const m = montar(true);
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    await m.c.aoTextoTranscrito("confirmo", false);
    await m.c.aoStatusPonte({ modo: "erro", detalhe: "LM Studio não respondeu" });
    expect(m.c.estado).toBe("erro");
    expect(m.c.detalhe).toBe("LM Studio não respondeu");
    await m.c.aoStatusPonte({ modo: "ligado" });
    expect(m.abrirMicrofone).toHaveBeenCalledOnce();
    expect(m.c.estado).toBe("repouso");
  });

  it("confirmacao_so_sim: 'simples' não ativa o modo jogo", async () => {
    const m = montar(true);
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    await m.c.aoTextoTranscrito("simples", false);
    expect(m.ponte.modo).not.toHaveBeenCalled();
    expect(m.c.estado).toBe("repouso");
    await m.c.aoTextoTranscrito("sim", false); // a confirmação já expirou
    expect(m.ponte.modo).not.toHaveBeenCalled();
  });

  it("ponte que falha ao ligar o jogo fala modo_falhou e segue ouvindo", async () => {
    const m = montar(true);
    m.ponte.modo.mockResolvedValue(false);
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    await m.c.aoTextoTranscrito("sim", false);
    expect(m.falas[m.falas.length - 1]).toBe(FALAS.erros.modo_falhou);
    expect(m.c.estado).toBe("repouso");
    expect(m.fecharMicrofone).not.toHaveBeenCalled();
  });
});
