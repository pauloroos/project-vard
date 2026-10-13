import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import type { DepsConversa, FalaEmFluxo, Mensagem } from "../src/fala/conversa";
import { Conversa } from "../src/fala/conversa";
import { FALAS } from "../src/fala/falas";
import { CONFIG_PADRAO } from "../src/config/config";
import { ErroVoz } from "../src/conectores/voz/cliente";

const WAV = new ArrayBuffer(8);

describe("conversa", () => {
  let oj: { perguntar: Mock<(m: Mensagem[], s?: AbortSignal) => Promise<string>>; sintetizar: Mock<(t: string, v: string, x: number) => Promise<ArrayBuffer>> };
  let boca: { falando: boolean; tocar: Mock<(w: ArrayBuffer) => Promise<void>>; parar: Mock<() => void> };
  let estados: string[];
  let ultimaFala: string | null;
  let c: Conversa;
  let deps: DepsConversa;

  beforeEach(() => {
    oj = { perguntar: vi.fn().mockResolvedValue("Agora são 13h."), sintetizar: vi.fn().mockResolvedValue(WAV) };
    boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    estados = []; ultimaFala = null;
    deps = {
      oj, boca, config: CONFIG_PADRAO,
      falas: async (t: string) => { ultimaFala = t; return WAV; },
      aoEstado: (e) => estados.push(e),
    };
    c = new Conversa(deps);
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
  it("interromper com pergunta em voo para a boca e volta ao repouso", async () => {
    oj.perguntar.mockImplementation(() => new Promise<string>(() => {}));
    void c.aoTextoTranscrito("Vard, oi", false);
    await Promise.resolve();
    expect(c.estado).toBe("pensando");
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

  it("abort durante a espera do indicador apaga o ponto vermelho e não captura", async () => {
    const m = montar(true);
    let liberar!: () => void;
    const depois = vi.fn();
    const c = new Conversa({
      oj: m.oj, boca: m.boca, config: CONFIG_PADRAO, falas: async () => WAV,
      ponte: m.ponte, capturar: m.capturar, depoisDaCaptura: depois,
      antesDaCaptura: () => new Promise<void>((r) => { liberar = r; }),
    });
    const p = c.aoTextoTranscrito("Vard, olha a tela", false);
    await Promise.resolve();
    c.interromper();
    liberar();
    await p;
    expect(depois).toHaveBeenCalledOnce();
    expect(m.capturar).not.toHaveBeenCalled();
    expect(m.ponte.ver).not.toHaveBeenCalled();
  });

  it("microfone que nunca foi aberto não é aberto na volta do jogo", async () => {
    const m = montar(true);
    m.fecharMicrofone.mockReturnValue(false);
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    await m.c.aoTextoTranscrito("sim", false);
    expect(m.c.estado).toBe("jogo");
    await m.c.aoStatusPonte({ modo: "ligado" });
    expect(m.abrirMicrofone).not.toHaveBeenCalled();
    expect(m.c.estado).toBe("repouso");
  });

  it("confirmação do modo jogo expira em 15 s", async () => {
    vi.useFakeTimers();
    try {
      const m = montar(true);
      await m.c.aoTextoTranscrito("Vard, modo jogo", false);
      vi.advanceTimersByTime(16000);
      await m.c.aoTextoTranscrito("sim", false);
      expect(m.ponte.modo).not.toHaveBeenCalled();
      await m.c.aoTextoTranscrito("Vard, modo jogo", false);
      vi.advanceTimersByTime(5000);
      await m.c.aoTextoTranscrito("sim", false);
      expect(m.ponte.modo).toHaveBeenCalledWith("jogo");
    } finally { vi.useRealTimers(); }
  });
});

describe("corridas do modo jogo", () => {
  function montarJogo() {
    const oj = { perguntar: vi.fn().mockResolvedValue("x"), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const estados: string[] = [];
    const ponte = { ver: vi.fn().mockResolvedValue("x"), modo: vi.fn().mockResolvedValue(true) };
    const abrirMicrofone = vi.fn();
    const fecharMicrofone = vi.fn().mockReturnValue(true);
    const c = new Conversa({
      oj, boca, config: CONFIG_PADRAO, falas: async () => WAV, aoEstado: (e) => estados.push(e),
      ponte, abrirMicrofone, fecharMicrofone,
    });
    return { c, oj, boca, estados, ponte, abrirMicrofone, fecharMicrofone };
  }

  it("sondagem 'jogo' durante o aviso não corta o aviso nem perde o microfone fechado", async () => {
    const m = montarJogo();
    let terminarAviso!: () => void;
    await m.c.aoTextoTranscrito("Vard, modo jogo", false);
    m.boca.tocar.mockClear();
    m.boca.tocar.mockImplementation(() => new Promise<void>((r) => { terminarAviso = r; }));
    const ativando = m.c.aoTextoTranscrito("sim", false);
    for (let i = 0; i < 50 && m.boca.tocar.mock.calls.length === 0; i++) await new Promise((r) => setTimeout(r, 0));
    expect(m.boca.tocar).toHaveBeenCalledOnce(); // aviso tocando
    await m.c.aoStatusPonte({ modo: "jogo" }); // a sondagem de 10 s cai aqui
    expect(m.fecharMicrofone).not.toHaveBeenCalled();
    expect(m.boca.parar).not.toHaveBeenCalled();
    terminarAviso();
    await ativando;
    expect(m.c.estado).toBe("jogo");
    expect(m.fecharMicrofone).toHaveBeenCalledOnce();
    m.boca.tocar.mockResolvedValue(undefined);
    await m.c.aoStatusPonte({ modo: "ligado" });
    expect(m.abrirMicrofone).toHaveBeenCalledOnce(); // na volta o microfone reabre
  });

  it("pergunta em voo não tira o HUD do jogo pedido por fora", async () => {
    const m = montarJogo();
    let liberar!: (t: string) => void;
    m.oj.perguntar.mockImplementation(() => new Promise<string>((r) => { liberar = r; }));
    const p = m.c.aoTextoTranscrito("Vard, oi", false);
    await Promise.resolve();
    await m.c.aoStatusPonte({ modo: "jogo" });
    expect(m.c.estado).toBe("jogo");
    liberar("resposta tardia");
    await p;
    expect(m.c.estado).toBe("jogo");
    expect(m.boca.tocar).not.toHaveBeenCalled();
    expect(m.estados[m.estados.length - 1]).toBe("jogo");
    await m.c.aoStatusPonte({ modo: "ligado" });
    expect(m.abrirMicrofone).toHaveBeenCalledOnce();
  });
});

describe("nome de chamada", () => {
  it("nome configurado chama o assistente e o nome padrão deixa de chamar", async () => {
    const oj = { perguntar: vi.fn().mockResolvedValue("Agora são 13h."), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const c = new Conversa({ oj, boca, config: { ...CONFIG_PADRAO, nome: "Jarvis", conversa_ms: 0 }, falas: async () => WAV });
    await c.aoTextoTranscrito("Jarvis, que horas são", false);
    expect(oj.perguntar).toHaveBeenCalledOnce();
    await c.aoTextoTranscrito("Vard, que horas são", false);
    expect(oj.perguntar).toHaveBeenCalledOnce();
  });
});

describe("voz própria frase a frase", () => {
  const F1 = "Primeira frase da resposta.";
  const F2 = "Segunda frase da resposta.";
  const F3 = "Terceira frase da resposta.";

  function adiado<T>() {
    let resolver!: (v: T) => void;
    const promessa = new Promise<T>((r) => { resolver = r; });
    return { promessa, resolver };
  }
  const espera = async (cond: () => boolean) => { for (let i = 0; i < 100 && !cond(); i++) await new Promise((r) => setTimeout(r, 0)); };

  /** Voz falsa que devolve um fluxo marcado com o texto; boca falsa que anota o que tocou e só termina quando mandada. */
  function montar(resposta: string, automatico = false) {
    const nomes = new Map<ReadableStream<Uint8Array>, string>();
    const cancelados: string[] = [];
    const fala = (texto: string): FalaEmFluxo => {
      const corpo = new ReadableStream<Uint8Array>({ cancel: () => { cancelados.push(texto); } });
      nomes.set(corpo, texto);
      return { corpo, taxa: 24000 };
    };
    const tocados: string[] = [];
    const fimDoToque: Array<() => void> = [];
    const boca = {
      falando: false,
      tocar: vi.fn(async (_w: ArrayBuffer) => { tocados.push("reserva"); }),
      tocarFluxo: vi.fn((corpo: ReadableStream<Uint8Array>, _taxa: number, _sinal?: AbortSignal) => {
        tocados.push(nomes.get(corpo) ?? "?");
        return automatico ? Promise.resolve() : new Promise<void>((r) => { fimDoToque.push(r); });
      }),
      parar: vi.fn(() => { for (const r of fimDoToque.splice(0)) r(); }),
    };
    const oj = { perguntar: vi.fn().mockResolvedValue(resposta), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const voz = { falar: vi.fn(async (t: string, _v: number, _s?: AbortSignal) => fala(t)) };
    const estados: string[] = [];
    const c = new Conversa({ oj, boca, voz, config: CONFIG_PADRAO, falas: async () => WAV, aoEstado: (e) => estados.push(e) });
    return { c, oj, boca, voz, fala, tocados, fimDoToque, cancelados, estados, nomeDe: (c: ReadableStream<Uint8Array>) => nomes.get(c) ?? "?" };
  }

  beforeEach(() => {
    vi.spyOn(console, "info").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("ordem_preservada: a 2ª frase pronta antes da 1ª acabar espera a vez", async () => {
    const m = montar(F1 + " " + F2);
    const d1 = adiado<FalaEmFluxo>();
    m.voz.falar.mockImplementationOnce(() => d1.promessa);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await espera(() => m.voz.falar.mock.calls.length === 1);
    await new Promise((r) => setTimeout(r, 0));
    expect(m.voz.falar).toHaveBeenCalledTimes(1); // a 2ª é pedida quando a 1ª começa a chegar
    d1.resolver(m.fala(F1));
    await espera(() => m.tocados.length === 1);
    expect(m.voz.falar).toHaveBeenCalledTimes(2); // pedida antes de a 1ª terminar de tocar
    expect(m.voz.falar.mock.calls[1][0]).toBe(F2);
    await new Promise((r) => setTimeout(r, 0));
    expect(m.tocados).toEqual([F1]); // a 2ª já chegou, mas não atropela a 1ª
    m.fimDoToque.shift()!();
    await espera(() => m.tocados.length === 2);
    expect(m.tocados).toEqual([F1, F2]);
    m.fimDoToque.shift()!();
    await p;
    expect(m.estados).toEqual(["pensando", "falando", "repouso"]);
    expect(m.oj.sintetizar).not.toHaveBeenCalled();
  });

  it("interromper_descarta_fila: frase pronta não toca, a seguinte nem é pedida", async () => {
    const m = montar([F1, F2, F3].join(" "));
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await espera(() => m.tocados.length === 1 && m.voz.falar.mock.calls.length === 2);
    m.c.interromper();
    expect(m.boca.parar).toHaveBeenCalled();
    await p;
    await new Promise((r) => setTimeout(r, 0));
    expect(m.tocados).toEqual([F1]);
    expect(m.cancelados).toEqual([F2]);
    expect(m.voz.falar).toHaveBeenCalledTimes(2);
    expect(m.c.estado).toBe("repouso");
  });

  it("interromper_descarta_fila: frase que chega depois do interromper é fechada e não toca", async () => {
    const m = montar([F1, F2, F3].join(" "));
    const d2 = adiado<FalaEmFluxo>();
    m.voz.falar.mockImplementationOnce(async (t) => m.fala(t)).mockImplementationOnce(() => d2.promessa);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await espera(() => m.tocados.length === 1 && m.voz.falar.mock.calls.length === 2);
    const sinal = m.voz.falar.mock.calls[1][2];
    m.c.interromper();
    expect(sinal?.aborted).toBe(true); // o pedido em voo recebe o abort
    d2.resolver(m.fala(F2)); // resposta atrasada de uma voz que não obedeceu ao abort
    await p;
    await espera(() => m.cancelados.length > 0);
    expect(m.tocados).toEqual([F1]);
    expect(m.cancelados).toEqual([F2]);
    expect(m.oj.sintetizar).not.toHaveBeenCalled();
    expect(m.boca.tocar).not.toHaveBeenCalled();
  });

  it("voz_fora_usa_reserva: erro de conexão manda o resto da resposta para o OpenJarvis", async () => {
    const m = montar(F1 + " " + F2, true);
    m.voz.falar.mockRejectedValue(new ErroVoz("sem conexão com a voz", true));
    await m.c.aoTextoTranscrito("me conta algo", true);
    expect(m.voz.falar).toHaveBeenCalledTimes(1);
    expect(m.oj.sintetizar.mock.calls.map((x) => x[0])).toEqual([F1, F2]);
    expect(m.oj.sintetizar).toHaveBeenCalledWith(F1, CONFIG_PADRAO.voz, CONFIG_PADRAO.velocidade);
    expect(m.tocados).toEqual(["reserva", "reserva"]);
    expect(console.warn).toHaveBeenCalledWith("voz própria falhou, usei a reserva", expect.any(ErroVoz));
    expect(m.c.estado).toBe("repouso");
  });

  it("fluxo cai no meio da frase: ela é falada de novo pela reserva, e o resto também", async () => {
    const m = montar(F1 + " " + F2, true);
    m.boca.tocarFluxo.mockImplementationOnce((corpo: ReadableStream<Uint8Array>) => {
      m.tocados.push(m.nomeDe(corpo));
      return Promise.reject(new ErroVoz("sem conexão com a voz", true));
    });
    await m.c.aoTextoTranscrito("me conta algo", true);
    expect(m.tocados).toEqual([F1, "reserva", "reserva"]); // F1 cortada, F1 pela reserva, F2 pela reserva
    expect(m.oj.sintetizar.mock.calls.map((x) => x[0])).toEqual([F1, F2]);
    expect(m.cancelados).toEqual([F2]); // a F2 já pedida à voz foi descartada
    expect(m.c.estado).toBe("repouso");
  });

  it("voz aquecendo (503) cai na reserva só naquela frase", async () => {
    const m = montar(F1 + " " + F2, true);
    m.voz.falar.mockRejectedValueOnce(new ErroVoz("voz HTTP 503", false));
    await m.c.aoTextoTranscrito("me conta algo", true);
    expect(m.voz.falar).toHaveBeenCalledTimes(2);
    expect(m.oj.sintetizar.mock.calls.map((x) => x[0])).toEqual([F1]);
    expect(m.tocados).toEqual(["reserva", F2]);
  });

  it("frase_sem_pontuacao_fala", async () => {
    const m = montar("abri o youtube pra você", true);
    await m.c.aoTextoTranscrito("abre o youtube", true);
    expect(m.voz.falar).toHaveBeenCalledOnce();
    expect(m.voz.falar.mock.calls[0][0]).toBe("abri o youtube pra você");
    expect(m.voz.falar.mock.calls[0][1]).toBe(CONFIG_PADRAO.velocidade);
    expect(m.tocados).toEqual(["abri o youtube pra você"]);
    expect(m.estados).toEqual(["pensando", "falando", "repouso"]);
  });

  it("sem voz própria: cada frase vai para a reserva, em ordem", async () => {
    const oj = { perguntar: vi.fn().mockResolvedValue(F1 + " " + F2), sintetizar: vi.fn().mockResolvedValue(WAV) };
    const boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    const c = new Conversa({ oj, boca, config: CONFIG_PADRAO, falas: async () => WAV });
    await c.aoTextoTranscrito("me conta algo", true);
    expect(oj.sintetizar.mock.calls.map((x) => x[0])).toEqual([F1, F2]);
    expect(boca.tocar).toHaveBeenCalledTimes(2);
  });

  it("texto que chega entre duas frases não atravessa a resposta", async () => {
    const m = montar(F1 + " " + F2);
    const p = m.c.aoTextoTranscrito("me conta algo", true);
    await espera(() => m.tocados.length === 1);
    await m.c.aoTextoTranscrito("olha a tela", true); // boca.falando é false no intervalo; o estado segura
    expect(m.oj.perguntar).toHaveBeenCalledOnce();
    m.fimDoToque.shift()!();
    await espera(() => m.tocados.length === 2);
    m.fimDoToque.shift()!();
    await p;
    expect(m.tocados).toEqual([F1, F2]);
  });
});

describe("modo conversa", () => {
  let oj: { perguntar: Mock<(m: Mensagem[], s?: AbortSignal) => Promise<string>>; sintetizar: Mock<(t: string, v: string, x: number) => Promise<ArrayBuffer>> };
  let boca: { falando: boolean; tocar: Mock<(w: ArrayBuffer) => Promise<void>>; parar: Mock<() => void> };
  let ultimaFala: string | null;
  let canal: boolean[];
  let mutar: Mock<() => void>;
  let deps: DepsConversa;
  let c: Conversa;

  beforeEach(() => {
    vi.useFakeTimers();
    oj = { perguntar: vi.fn().mockResolvedValue("Agora são 13h."), sintetizar: vi.fn().mockResolvedValue(WAV) };
    boca = { falando: false, tocar: vi.fn().mockResolvedValue(undefined), parar: vi.fn() };
    ultimaFala = null; canal = []; mutar = vi.fn();
    deps = {
      oj, boca, config: { ...CONFIG_PADRAO, conversa_ms: 20000 },
      falas: async (t: string) => { ultimaFala = t; return WAV; },
      mutar, aoCanal: (a) => canal.push(a),
    };
    c = new Conversa(deps);
  });
  afterEach(() => { vi.useRealTimers(); });

  it("depois_de_responder_o_nome_e_dispensado_ate_o_silencio", async () => {
    await c.aoTextoTranscrito("Vard, que horas são", false);
    expect(c.canalAberto()).toBe(true);
    expect(canal).toEqual([true]);
    await c.aoTextoTranscrito("e amanhã", false);
    expect(oj.perguntar).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(19999); expect(c.canalAberto()).toBe(true);
    vi.advanceTimersByTime(1); expect(c.canalAberto()).toBe(false);
    expect(canal).toEqual([true, false]);
    await c.aoTextoTranscrito("e depois", false);
    expect(oj.perguntar).toHaveBeenCalledTimes(2); // nome exigido de novo
  });
  it("cada_troca_rearma_o_relogio", async () => {
    await c.aoTextoTranscrito("Vard, oi", false);
    vi.advanceTimersByTime(15000);
    await c.aoTextoTranscrito("que horas são", false);
    vi.advanceTimersByTime(15000); expect(c.canalAberto()).toBe(true);
  });
  it("conversa_ms_zero_desliga", async () => {
    c = new Conversa({ ...deps, config: { ...CONFIG_PADRAO, conversa_ms: 0 } });
    await c.aoTextoTranscrito("Vard, que horas são", false);
    expect(c.canalAberto()).toBe(false);
    await c.aoTextoTranscrito("e amanhã", false);
    expect(oj.perguntar).toHaveBeenCalledTimes(1);
  });
  it("frase_de_encerramento_fala_e_muta_com_ou_sem_o_nome", async () => {
    await c.aoTextoTranscrito("Vard, pode parar de me ouvir", false);
    expect(ultimaFala).toBe(FALAS.pareiDeOuvir);
    expect(mutar).toHaveBeenCalledOnce();
    expect(c.canalAberto()).toBe(false);
    await c.aoTextoTranscrito("Vard, oi", false);
    await c.aoTextoTranscrito("vou entrar em reunião", false);
    expect(mutar).toHaveBeenCalledTimes(2);
    expect(oj.perguntar).not.toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ content: "vou entrar em reunião" })]), expect.anything());
  });
  it("jogo_fecha_o_canal", async () => {
    const ponte = { ver: vi.fn(), modo: vi.fn().mockResolvedValue(true) };
    c = new Conversa({ ...deps, ponte, fecharMicrofone: () => true });
    await c.aoTextoTranscrito("Vard, oi", false);
    await c.aoStatusPonte({ modo: "jogo" });
    expect(c.canalAberto()).toBe(false);
    expect(canal).toEqual([true, false]);
  });
  it("nucleo_fora_fecha_o_canal", async () => {
    await c.aoTextoTranscrito("Vard, oi", false);
    await c.aoHealth(false, false);
    expect(c.canalAberto()).toBe(false);
  });
  it("push_to_talk_tambem_abre_o_canal", async () => {
    await c.aoTextoTranscrito("que horas são", true);
    expect(c.canalAberto()).toBe(true);
  });
});
