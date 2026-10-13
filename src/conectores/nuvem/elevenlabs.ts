// ElevenLabs: só é chamado quando o usuário escolheu o provedor e informou a chave (nunca por padrão).
import type { FalaEmFluxo } from "../../fala/conversa";
import { fluxoParaWav } from "../../audio/wav";
import { ErroVoz } from "../voz/cliente";
import type { FonteDeVoz } from "../voz/fonte";

const BASE = "https://api.elevenlabs.io/v1";
const TAXA = 24000;
const PRAZO_MS = 15000;

export class ElevenLabs implements FonteDeVoz {
  readonly nome: string;
  private buscar: (url: string, init: RequestInit) => Promise<Response>;
  constructor(private chave: string, private voz: string, opcoes: { fetch?: (url: string, init: RequestInit) => Promise<Response> } = {}) {
    this.nome = `elevenlabs:${voz}`;
    this.buscar = opcoes.fetch ?? ((u, i) => fetch(u, i));
  }
  async saude(): Promise<boolean> { return this.chave.trim() !== "" && this.voz.trim() !== ""; }
  async falar(texto: string, velocidade: number, sinal?: AbortSignal, prazoMs = PRAZO_MS): Promise<FalaEmFluxo> {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), prazoMs);
    const repassar = () => ac.abort();
    sinal?.addEventListener("abort", repassar);
    try {
      let r: Response;
      try {
        r = await this.buscar(`${BASE}/text-to-speech/${encodeURIComponent(this.voz)}/stream?output_format=pcm_24000`, {
          method: "POST", signal: ac.signal,
          headers: { "Content-Type": "application/json", "xi-api-key": this.chave, Accept: "audio/pcm" },
          body: JSON.stringify({ text: texto, model_id: "eleven_multilingual_v2", voice_settings: { speed: Math.min(1.2, Math.max(0.7, velocidade)) } }),
        });
      } catch (erro) { throw new ErroVoz(`sem conexão com o ElevenLabs: ${String(erro)}`, true); }
      if (!r.ok) { void r.body?.cancel().catch(() => {}); throw new ErroVoz(`ElevenLabs respondeu ${r.status}`, false); }
      if (!r.body) throw new ErroVoz("ElevenLabs sem corpo", false);
      return { corpo: r.body, taxa: TAXA };
    } finally { clearTimeout(t); sinal?.removeEventListener("abort", repassar); }
  }
  async falarWav(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer> {
    const { corpo, taxa } = await this.falar(texto, velocidade, undefined, prazoMs);
    return fluxoParaWav(corpo, taxa);
  }
  /** Vozes da conta (GET /v1/voices). Só por clique do usuário. */
  async vozes(): Promise<{ id: string; nome: string }[]> {
    const r = await this.buscar(`${BASE}/voices`, { headers: { "xi-api-key": this.chave } });
    if (!r.ok) throw new ErroVoz(`ElevenLabs respondeu ${r.status}`, false);
    const j = await r.json();
    return Array.isArray(j?.voices) ? j.voices.map((v: { voice_id?: unknown; name?: unknown }) => ({ id: String(v?.voice_id ?? ""), nome: String(v?.name ?? "") })).filter((v: { id: string }) => v.id) : [];
  }
}
