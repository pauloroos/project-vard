import type { Mensagem } from "../../fala/conversa";
import type { Conector } from "../conector";

async function comTimeout<T>(ms: number, f: (sinal: AbortSignal) => Promise<T>, externo?: AbortSignal): Promise<T> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  const repassar = () => ac.abort();
  if (externo?.aborted) ac.abort(); else externo?.addEventListener("abort", repassar);
  try { return await f(ac.signal); } finally { clearTimeout(t); externo?.removeEventListener("abort", repassar); }
}

/** O preferido se o núcleo ainda o expõe; senão o primeiro (caiu = true quando havia um preferido). null sem modelos. */
export function escolherModelo(ids: string[], preferido: string): { id: string; caiu: boolean } | null {
  if (ids.length === 0) return null;
  const p = preferido.trim();
  if (p && ids.includes(p)) return { id: p, caiu: false };
  return { id: ids[0], caiu: p !== "" };
}

export class OpenJarvis implements Conector {
  private modelo: string | null = null;
  private base: string;

  constructor(base: string, private preferido = "", private habilitado: () => boolean = () => true) { this.base = base.replace(/\/+$/, ""); }

  /** Consulta a configuração viva antes de cada requisição, inclusive após esperas. */
  private buscar(url: string, opcoes?: RequestInit): Promise<Response> {
    if (!this.habilitado()) throw new Error("OpenJarvis desligado. Ative-o em Quem responde e reinicie os serviços.");
    return fetch(url, opcoes);
  }

  async saude(): Promise<boolean> {
    try {
      const r = await comTimeout(3000, (signal) => this.buscar(`${this.base}/health`, { signal }));
      return r.ok;
    } catch { return false; }
  }

  async fala(): Promise<boolean> {
    try {
      const r = await comTimeout(3000, (signal) => this.buscar(`${this.base}/v1/speech/health`, { signal }));
      if (!r.ok) return false;
      return (await r.json()).available === true;
    } catch { return false; }
  }

  async transcrever(wav: ArrayBuffer, idioma: string, externo?: AbortSignal): Promise<string> {
    const form = new FormData();
    form.append("file", new Blob([wav], { type: "audio/wav" }), "fala.wav");
    if (idioma) form.append("language", idioma);
    return comTimeout(30000, async (signal) => {
      const r = await this.buscar(`${this.base}/v1/speech/transcribe`, { method: "POST", body: form, signal });
      if (!r.ok) throw new Error(`transcrever HTTP ${r.status}`);
      const j = await r.json();
      return String(j.text ?? "").trim();
    }, externo);
  }

  async modelos(): Promise<string[]> {
    const r = await comTimeout(5000, (signal) => this.buscar(`${this.base}/v1/models`, { signal }));
    if (!r.ok) throw new Error(`modelos HTTP ${r.status}`);
    const j = await r.json();
    return Array.isArray(j?.data) ? j.data.map((m: { id?: unknown }) => String(m?.id ?? "")).filter(Boolean) : [];
  }

  definirModelo(preferido: string) { this.preferido = preferido; this.modelo = null; }

  private async idModelo(): Promise<string> {
    if (this.modelo) return this.modelo;
    const preferido = this.preferido;
    const escolha = escolherModelo(await this.modelos(), preferido);
    if (this.preferido !== preferido) return this.idModelo(); // definirModelo() rodou durante a espera: o resultado é obsoleto
    if (!escolha) throw new Error("nenhum modelo");
    if (escolha.caiu) console.warn(`modelo ${this.preferido} não está mais no OpenJarvis; usando ${escolha.id}`);
    this.modelo = escolha.id;
    return this.modelo;
  }

  async perguntar(mensagens: Mensagem[], externo?: AbortSignal): Promise<string> {
    const model = await this.idModelo();
    return comTimeout(90000, async (signal) => {
      const r = await this.buscar(`${this.base}/v1/chat/completions`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal,
        body: JSON.stringify({ model, messages: mensagens, stream: false }),
      });
      if (!r.ok) throw new Error(`perguntar HTTP ${r.status}`);
      const j = await r.json();
      return String(j?.choices?.[0]?.message?.content ?? "");
    }, externo);
  }

  async sintetizar(texto: string, voz: string, velocidade: number, externo?: AbortSignal): Promise<ArrayBuffer> {
    return comTimeout(30000, async (signal) => {
      const r = await this.buscar(`${this.base}/v1/speech/synthesize`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal,
        body: JSON.stringify({ text: texto, voice_id: voz, speed: velocidade }),
      });
      if (!r.ok) throw new Error(`sintetizar HTTP ${r.status}`);
      return r.arrayBuffer();
    }, externo);
  }
}
