import catalogo from "../../../config/vozes.json";
// Gemini TTS: só é chamado quando o usuário escolheu o provedor e informou a chave (nunca por padrão).
import type { FalaEmFluxo } from "../../fala/conversa";
import { fluxoParaWav } from "../../audio/wav";
import { ErroVoz } from "../voz/cliente";
import type { FonteDeVoz } from "../voz/fonte";

const URL_TTS = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent";
const TAXA_PADRAO = 24000;
const PRAZO_MS = 20000;

export const VOZES_GEMINI = catalogo.gemini;

interface RespostaGemini { candidates?: { content?: { parts?: { inlineData?: { data?: string; mimeType?: string } }[] } }[] }

export class Gemini implements FonteDeVoz {
  readonly nome: string;
  private buscar: (url: string, init: RequestInit) => Promise<Response>;
  constructor(private chave: string, private voz: string, opcoes: { fetch?: (url: string, init: RequestInit) => Promise<Response> } = {}) {
    this.nome = `gemini:${voz}`;
    this.buscar = opcoes.fetch ?? ((u, i) => fetch(u, i));
  }
  async saude(): Promise<boolean> { return this.chave.trim() !== ""; }
  /** A velocidade é ignorada: o Gemini TTS não tem esse parâmetro. A resposta vem inteira (não em fluxo). */
  async falar(texto: string, _velocidade: number, sinal?: AbortSignal, prazoMs = PRAZO_MS): Promise<FalaEmFluxo> {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), prazoMs);
    const repassar = () => ac.abort();
    sinal?.addEventListener("abort", repassar);
    try {
      let r: Response;
      try {
        r = await this.buscar(URL_TTS, {
          method: "POST", signal: ac.signal,
          headers: { "Content-Type": "application/json", "x-goog-api-key": this.chave },
          body: JSON.stringify({
            contents: [{ parts: [{ text: texto }] }],
            generationConfig: { responseModalities: ["AUDIO"], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: this.voz } } } },
          }),
        });
      } catch (erro) { throw new ErroVoz(`sem conexão com o Gemini: ${String(erro)}`, true); }
      if (!r.ok) { void r.body?.cancel().catch(() => {}); throw new ErroVoz(`Gemini respondeu ${r.status}`, false); }
      let j: RespostaGemini;
      try { j = await r.json(); } catch (erro) { throw new ErroVoz(`Gemini com resposta ilegível: ${String(erro)}`, true); }
      const dado = j?.candidates?.[0]?.content?.parts?.find((p) => p?.inlineData?.data)?.inlineData;
      if (!dado?.data) throw new ErroVoz("Gemini sem áudio", false);
      const bin = atob(dado.data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const taxa = Number(/rate=(\d+)/.exec(dado.mimeType ?? "")?.[1]) || TAXA_PADRAO;
      return { corpo: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }), taxa };
    } finally { clearTimeout(t); sinal?.removeEventListener("abort", repassar); }
  }
  async falarWav(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer> {
    const { corpo, taxa } = await this.falar(texto, velocidade, undefined, prazoMs);
    return fluxoParaWav(corpo, taxa);
  }
}
