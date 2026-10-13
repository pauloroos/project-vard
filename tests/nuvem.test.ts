import { describe, it, expect, vi } from "vitest";
import { ElevenLabs } from "../src/conectores/nuvem/elevenlabs";
import { Gemini, VOZES_GEMINI } from "../src/conectores/nuvem/gemini";
import { ErroVoz } from "../src/conectores/voz/cliente";

const pcm = (bytes: number[]) => new Response(new Uint8Array(bytes), { status: 200, headers: { "Content-Type": "audio/pcm" } });
async function lerTudo(corpo: ReadableStream<Uint8Array>): Promise<number[]> {
  const s: number[] = []; const r = corpo.getReader();
  for (;;) { const { done, value } = await r.read(); if (done) return s; s.push(...value); }
}

describe("ElevenLabs", () => {
  it("manda_chave_voz_e_pcm_24k", async () => {
    const f = vi.fn(async () => pcm([1, 0, 2, 0]));
    const el = new ElevenLabs("chave-x", "voz-y", { fetch: f });
    const { corpo, taxa } = await el.falar("Oi.", 1.05);
    expect(taxa).toBe(24000);
    expect(await lerTudo(corpo)).toEqual([1, 0, 2, 0]);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.elevenlabs.io/v1/text-to-speech/voz-y/stream?output_format=pcm_24000");
    expect((init.headers as Record<string, string>)["xi-api-key"]).toBe("chave-x");
    const corpoPedido = JSON.parse(String(init.body));
    expect(corpoPedido.text).toBe("Oi.");
    expect(corpoPedido.voice_settings.speed).toBe(1.05);
  });
  it("velocidade_limitada_a_0_7_1_2", async () => {
    const f = vi.fn(async () => pcm([0, 0]));
    await new ElevenLabs("k", "v", { fetch: f }).falar("Oi.", 2);
    expect(JSON.parse(String((f.mock.calls[0] as unknown as [string, RequestInit])[1].body)).voice_settings.speed).toBe(1.2);
  });
  it("401_vira_ErroVoz_sem_conexao", async () => {
    const f = vi.fn(async () => new Response("{}", { status: 401 }));
    await expect(new ElevenLabs("k", "v", { fetch: f }).falar("Oi.", 1)).rejects.toMatchObject({ name: "ErroVoz", conexao: false });
  });
  it("rede_vira_ErroVoz_com_conexao", async () => {
    const f = vi.fn(async () => { throw new TypeError("fetch failed"); });
    await expect(new ElevenLabs("k", "v", { fetch: f }).falar("Oi.", 1)).rejects.toBeInstanceOf(ErroVoz);
    await expect(new ElevenLabs("k", "v", { fetch: f }).falar("Oi.", 1)).rejects.toMatchObject({ conexao: true });
  });
  it("saude_nao_faz_rede", async () => {
    const f = vi.fn();
    expect(await new ElevenLabs("k", "v", { fetch: f }).saude()).toBe(true);
    expect(await new ElevenLabs("", "v", { fetch: f }).saude()).toBe(false);
    expect(f).not.toHaveBeenCalled();
  });
  it("vozes_lista_id_e_nome", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ voices: [{ voice_id: "a", name: "Ana" }, { voice_id: "b", name: "Bia" }] }), { status: 200 }));
    expect(await new ElevenLabs("k", "v", { fetch: f }).vozes()).toEqual([{ id: "a", nome: "Ana" }, { id: "b", nome: "Bia" }]);
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe("https://api.elevenlabs.io/v1/voices");
  });
});

describe("Gemini", () => {
  it("manda_chave_voz_e_decodifica_o_base64", async () => {
    const b64 = btoa(String.fromCharCode(1, 0, 2, 0));
    const f = vi.fn(async () => new Response(JSON.stringify({ candidates: [{ content: { parts: [{ inlineData: { mimeType: "audio/L16;codec=pcm;rate=24000", data: b64 } }] } }] }), { status: 200 }));
    const g = new Gemini("chave-g", "Kore", { fetch: f });
    const { corpo, taxa } = await g.falar("Oi.", 1);
    expect(taxa).toBe(24000);
    expect(await lerTudo(corpo)).toEqual([1, 0, 2, 0]);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent");
    expect((init.headers as Record<string, string>)["x-goog-api-key"]).toBe("chave-g");
    const c = JSON.parse(String(init.body));
    expect(c.generationConfig.responseModalities).toEqual(["AUDIO"]);
    expect(c.generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName).toBe("Kore");
  });
  it("resposta_sem_audio_e_erro_sem_conexao", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ candidates: [] }), { status: 200 }));
    await expect(new Gemini("k", "Kore", { fetch: f }).falar("Oi.", 1)).rejects.toMatchObject({ conexao: false });
  });
  it("saude_nao_faz_rede_e_vozes_fixas", async () => {
    const f = vi.fn();
    expect(await new Gemini("k", "Kore", { fetch: f }).saude()).toBe(true);
    expect(f).not.toHaveBeenCalled();
    expect(VOZES_GEMINI).toContain("Kore");
    expect(VOZES_GEMINI.length).toBeGreaterThanOrEqual(30);
  });
});
