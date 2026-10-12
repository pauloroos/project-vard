import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import type { AddressInfo } from "node:net";
// @ts-expect-error módulo .mjs sem tipos
import { criarServidor, criarPonteFalsa, criarVozFalsa } from "./servidor-falso.mjs";
import { OpenJarvis } from "../../src/conectores/openjarvis/cliente";
import { Ponte } from "../../src/conectores/ponte/cliente";
import { Voz } from "../../src/conectores/voz/cliente";
import { Conversa } from "../../src/fala/conversa";
import { CONFIG_PADRAO } from "../../src/config/config";
import { pcmParaWav } from "../../src/audio/wav";

let servidor: ReturnType<typeof criarServidor>;
let oj: OpenJarvis;
let porta = 0;

beforeAll(async () => {
  servidor = criarServidor();
  await new Promise<void>((r) => servidor.listen(0, "127.0.0.1", r));
  porta = (servidor.address() as AddressInfo).port;
  oj = new OpenJarvis(`http://127.0.0.1:${porta}`);
});
afterAll(() => new Promise<void>((r) => servidor.close(() => r())));

describe("Conversa com OpenJarvis contra o servidor falso", () => {
  it("saúde e fala no ar", async () => {
    expect(await oj.saude()).toBe(true);
    expect(await oj.fala()).toBe(true);
  });

  it("transcrever, perguntar e sintetizar de ponta a ponta", async () => {
    const tocados: ArrayBuffer[] = [];
    const boca = { falando: false, tocar: async (w: ArrayBuffer) => { tocados.push(w); }, parar() {} };
    const estados: string[] = [];
    const c = new Conversa({
      oj, boca, config: CONFIG_PADRAO,
      falas: (t) => oj.sintetizar(t, CONFIG_PADRAO.voz, CONFIG_PADRAO.velocidade),
      aoEstado: (e) => estados.push(e),
    });

    const wav = pcmParaWav(new Float32Array(16000), 16000);
    const texto = await oj.transcrever(wav, "pt");
    expect(texto).toBe("Vard, que horas são");

    await c.aoTextoTranscrito(texto, false);
    expect(estados).toEqual(["pensando", "falando", "repouso"]);
    expect(tocados).toHaveLength(1);
    const v = new DataView(tocados[0]);
    expect(String.fromCharCode(v.getUint8(0), v.getUint8(1), v.getUint8(2), v.getUint8(3))).toBe("RIFF");
    expect(tocados[0].byteLength).toBeGreaterThan(10000);
    expect(c.historico[1]).toEqual({ role: "assistant", content: "Agora são 13h." });
  });

  it("o texto da transcrição vem do header X-Texto-Falso", async () => {
    const form = new FormData();
    form.append("file", new Blob([new ArrayBuffer(8)], { type: "audio/wav" }), "fala.wav");
    const r = await fetch(`http://127.0.0.1:${porta}/v1/speech/transcribe`, { method: "POST", body: form, headers: { "X-Texto-Falso": "abre o youtube" } });
    expect((await r.json()).text).toBe("abre o youtube");
  });
});

describe("Ponte do Vard contra a ponte falsa", () => {
  let srv: ReturnType<typeof criarPonteFalsa>;
  let ponte: Ponte;
  beforeAll(async () => {
    srv = criarPonteFalsa();
    await new Promise<void>((r) => srv.listen(0, "127.0.0.1", r));
    ponte = new Ponte(`http://127.0.0.1:${(srv.address() as AddressInfo).port}`);
  });
  afterAll(() => new Promise<void>((r) => srv.close(() => r())));

  it("status, ver e modo", async () => {
    expect(await ponte.status()).toEqual({ ok: true, modo: "ligado", detalhe: undefined });
    expect(await ponte.ver("/9j/4AAQ", "o que está na tela?")).toBe("Um editor de código aberto.");
    expect(srv.estado.pedidos[0].jpeg).toBe(true);
    expect(await ponte.modo("jogo")).toBe(true);
    expect((await ponte.status())?.modo).toBe("jogo");
  });

  it("503 vira ErroPonte com o código", async () => {
    srv.estado.erroVer = "modelo_fora";
    await expect(ponte.ver("/9j/4AAQ", "?")).rejects.toMatchObject({ codigo: "modelo_fora" });
  });

  it("ponte ausente: status null", async () => {
    expect(await new Ponte("http://127.0.0.1:1").status()).toBeNull();
  });
});

describe("Voz própria contra a voz falsa", () => {
  let srv: ReturnType<typeof criarVozFalsa>;
  let voz: Voz;
  beforeAll(async () => {
    srv = criarVozFalsa();
    await new Promise<void>((r) => srv.listen(0, "127.0.0.1", r));
    voz = new Voz(`http://127.0.0.1:${(srv.address() as AddressInfo).port}`);
  });
  afterAll(() => new Promise<void>((r) => srv.close(() => r())));

  it("saúde, PCM em fluxo e a conversa falando pela voz própria", async () => {
    expect(await voz.saude()).toBe(true);
    expect(voz.nome).toBe("Voz Falsa");
    const { corpo, taxa } = await voz.falar("Teste da voz.", 1.05);
    expect(taxa).toBe(24000);
    let bytes = 0;
    const leitor = corpo.getReader();
    for (;;) { const { done, value } = await leitor.read(); if (done) break; bytes += value.length; }
    expect(bytes).toBe(14400); // 3 x 0,1 s a 24 kHz, 16 bits

    // Boca sem tocarFluxo: a conversa lê a frase inteira e toca como WAV.
    const tocados: ArrayBuffer[] = [];
    const boca = { falando: false, tocar: async (w: ArrayBuffer) => { tocados.push(w); }, parar() {} };
    const c = new Conversa({ oj, voz, boca, config: CONFIG_PADRAO, falas: async () => new ArrayBuffer(0) });
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    await c.aoTextoTranscrito("Vard, que horas são", false);
    info.mockRestore();
    expect(tocados).toHaveLength(1);
    expect(tocados[0].byteLength).toBe(44 + 14400);
    expect(new DataView(tocados[0]).getUint32(24, true)).toBe(24000);
    expect(srv.estado.pedidos.at(-1)).toEqual({ texto: "Agora são 13h.", velocidade: CONFIG_PADRAO.velocidade, pcm: true });
  });

  it("voz aquecendo (503): a frase sai pela reserva do OpenJarvis", async () => {
    srv.estado.aquecendo = true;
    const tocados: ArrayBuffer[] = [];
    const boca = { falando: false, tocar: async (w: ArrayBuffer) => { tocados.push(w); }, parar() {} };
    const c = new Conversa({ oj, voz, boca, config: CONFIG_PADRAO, falas: async () => new ArrayBuffer(0) });
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    try {
      await c.aoTextoTranscrito("Vard, que horas são", false);
      expect(aviso).toHaveBeenCalledWith("voz própria falhou, usei a reserva", expect.anything());
      expect(tocados).toHaveLength(1);
      expect(new DataView(tocados[0]).getUint32(24, true)).toBe(22050); // a senoide do OpenJarvis falso
    } finally {
      aviso.mockRestore(); info.mockRestore();
      srv.estado.aquecendo = false;
    }
  });
});
