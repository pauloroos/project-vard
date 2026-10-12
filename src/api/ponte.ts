// Cliente da ponte opcional do Vard (127.0.0.1:4700). Sem ponte o HUD funciona igual: tudo aqui falha em silêncio.
export interface StatusPonte { ok: boolean; modo: string; detalhe?: string }

/** Erro da ponte com o código curto (`modelo_fora`, `segredos`...) que vira fala fixa em FALAS.erros. */
export class ErroPonte extends Error {
  constructor(public codigo: string) { super(codigo); }
}

async function comTimeout<T>(ms: number, f: (sinal: AbortSignal) => Promise<T>): Promise<T> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  try { return await f(ac.signal); } finally { clearTimeout(t); }
}

function paraBlob(b64: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: "image/jpeg" });
}

export class Ponte {
  private base: string;
  constructor(base: string) { this.base = base.replace(/\/+$/, ""); }

  /** null = ponte ausente (não respondeu em 5 s). `ok` = OpenJarvis e LM Studio no ar. */
  async status(): Promise<StatusPonte | null> {
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/status`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        const detalhe = typeof j.detalhe === "string" && j.detalhe ? j.detalhe : undefined;
        return { ok: j.openjarvis === true && j.lmstudio === true, modo: String(j.modo ?? ""), detalhe };
      });
    } catch { return null; }
  }

  /** Manda o quadro (JPEG em base64) e a pergunta; devolve a resposta. 503 vira ErroPonte(codigo). */
  async ver(jpegB64: string, pergunta: string): Promise<string> {
    const form = new FormData();
    form.append("imagem", paraBlob(jpegB64), "tela.jpg");
    form.append("pergunta", pergunta);
    return comTimeout(90000, async (signal) => {
      let r: Response;
      try { r = await fetch(`${this.base}/see`, { method: "POST", body: form, signal }); }
      catch { throw new ErroPonte("rede"); }
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new ErroPonte(String(j?.erro ?? "modelo_http"));
      const t = String(j?.resposta ?? "").trim();
      if (!t) throw new ErroPonte("modelo_vazio");
      return t;
    });
  }

  /** Dispara um verbo do ciclo (`jogo`, `voltar`...). true = a ponte aceitou. */
  async modo(verbo: string): Promise<boolean> {
    try {
      return await comTimeout(10000, async (signal) => {
        const r = await fetch(`${this.base}/modo`, {
          method: "POST", headers: { "Content-Type": "application/json" }, signal,
          body: JSON.stringify({ modo: verbo }),
        });
        return r.ok && (await r.json())?.ok === true;
      });
    } catch { return false; }
  }

  /** Eventos ao vivo (SSE). Reconecta com espera exponencial até 30 s. Devolve a função que encerra. */
  eventos(cb: (tipo: string, dados: unknown) => void): () => void {
    let fonte: EventSource | null = null;
    let parado = false;
    let espera = 1000;
    let timer = 0;
    const abrir = () => {
      if (parado) return;
      const es = new EventSource(`${this.base}/events`);
      fonte = es;
      es.onopen = () => { espera = 1000; };
      es.onerror = () => {
        es.close();
        if (parado) return;
        timer = window.setTimeout(abrir, espera);
        espera = Math.min(espera * 2, 30000);
      };
      const ouvir = (tipo: string) => es.addEventListener(tipo, (ev) => {
        let dados: unknown = null;
        try { dados = JSON.parse((ev as MessageEvent).data); } catch { /* ping ou texto puro */ }
        cb(tipo, dados);
      });
      ouvir("ping"); ouvir("oficina");
      es.onmessage = (ev) => { try { cb("message", JSON.parse(ev.data)); } catch { cb("message", null); } };
    };
    abrir();
    return () => { parado = true; clearTimeout(timer); fonte?.close(); };
  }
}
