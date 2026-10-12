import type { Mensagem } from "../fala/conversa";

async function comTimeout<T>(ms: number, f: (sinal: AbortSignal) => Promise<T>, externo?: AbortSignal): Promise<T> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  const repassar = () => ac.abort();
  if (externo?.aborted) ac.abort(); else externo?.addEventListener("abort", repassar);
  try { return await f(ac.signal); } finally { clearTimeout(t); externo?.removeEventListener("abort", repassar); }
}

export class OpenJarvis {
  private modelo: string | null = null;
  private base: string;

  constructor(base: string) { this.base = base.replace(/\/+$/, ""); }

  async saude(): Promise<boolean> {
    try {
      const r = await comTimeout(3000, (signal) => fetch(`${this.base}/health`, { signal }));
      return r.ok;
    } catch { return false; }
  }

  async fala(): Promise<boolean> {
    try {
      const r = await comTimeout(3000, (signal) => fetch(`${this.base}/v1/speech/health`, { signal }));
      if (!r.ok) return false;
      return (await r.json()).available === true;
    } catch { return false; }
  }

  async transcrever(wav: ArrayBuffer, idioma: string): Promise<string> {
    const form = new FormData();
    form.append("file", new Blob([wav], { type: "audio/wav" }), "fala.wav");
    if (idioma) form.append("language", idioma);
    return comTimeout(30000, async (signal) => {
      const r = await fetch(`${this.base}/v1/speech/transcribe`, { method: "POST", body: form, signal });
      if (!r.ok) throw new Error(`transcrever HTTP ${r.status}`);
      const j = await r.json();
      return String(j.text ?? "").trim();
    });
  }

  private async idModelo(): Promise<string> {
    if (this.modelo) return this.modelo;
    const r = await comTimeout(5000, (signal) => fetch(`${this.base}/v1/models`, { signal }));
    if (!r.ok) throw new Error(`modelos HTTP ${r.status}`);
    const j = await r.json();
    const id = j?.data?.[0]?.id;
    if (!id) throw new Error("nenhum modelo");
    this.modelo = id as string;
    return this.modelo;
  }

  async perguntar(mensagens: Mensagem[], externo?: AbortSignal): Promise<string> {
    const model = await this.idModelo();
    return comTimeout(90000, async (signal) => {
      const r = await fetch(`${this.base}/v1/chat/completions`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal,
        body: JSON.stringify({ model, messages: mensagens, stream: false }),
      });
      if (!r.ok) throw new Error(`perguntar HTTP ${r.status}`);
      const j = await r.json();
      return String(j?.choices?.[0]?.message?.content ?? "");
    }, externo);
  }

  async sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer> {
    return comTimeout(30000, async (signal) => {
      const r = await fetch(`${this.base}/v1/speech/synthesize`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal,
        body: JSON.stringify({ text: texto, voice_id: voz, speed: velocidade }),
      });
      if (!r.ok) throw new Error(`sintetizar HTTP ${r.status}`);
      return r.arrayBuffer();
    });
  }
}
