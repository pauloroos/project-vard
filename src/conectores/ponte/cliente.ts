// Cliente da ponte opcional do Vard (127.0.0.1:4700). Sem ponte o HUD funciona igual: tudo aqui falha em silêncio.
export interface StatusPonte { ok: boolean; modo: string; detalhe?: string; reserva?: string; tarefas_abertas?: number; modelos_lmstudio?: string[] }

/** Um aviso da central da ponte. `n` só existe nos do tipo tarefa. */
export interface Aviso { id: number; hora: string; tipo: string; resumo: string; n?: number; estado?: string; lido: boolean }

/** Resultado de uma tarefa da ponte. */
export interface ResultadoTarefa { n: number; estado: string; resumo: string; texto: string }

/** Um aviso vindo da rede, com os campos frouxos: id obrigatório, o resto com padrão. */
export function normalizarAviso(a: unknown): Aviso | null {
  if (typeof a !== "object" || a === null) return null;
  const o = a as Record<string, unknown>;
  if (typeof o.id !== "number") return null;
  return {
    id: o.id,
    hora: typeof o.hora === "string" ? o.hora : "",
    tipo: typeof o.tipo === "string" ? o.tipo : "",
    resumo: typeof o.resumo === "string" ? o.resumo : "",
    ...(typeof o.n === "number" ? { n: o.n } : {}),
    ...(typeof o.estado === "string" ? { estado: o.estado } : {}),
    lido: o.lido === true,
  };
}

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
    if (!this.base) return null; // ponte_url vazio = ponte desligada
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/status`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        const detalhe = typeof j.detalhe === "string" && j.detalhe ? j.detalhe : undefined;
        const reserva = typeof j.reserva === "string" && j.reserva.trim() ? j.reserva.trim() : undefined;
        const modelos = Array.isArray(j.modelos_lmstudio) ? j.modelos_lmstudio.filter((x: unknown) => typeof x === "string") : undefined;
        const tarefas_abertas = typeof j.tarefas_abertas === "number" ? j.tarefas_abertas : undefined;
        return { ok: j.openjarvis === true && j.lmstudio === true, modo: String(j.modo ?? ""), detalhe, reserva, tarefas_abertas, modelos_lmstudio: modelos };
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
    if (!this.base) return false; // ponte_url vazio = ponte desligada: nada de rede
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
      ouvir("ping"); ouvir("oficina"); ouvir("reuniao");
      es.onmessage = (ev) => { try { cb("message", JSON.parse(ev.data)); } catch { cb("message", null); } };
    };
    abrir();
    return () => { parado = true; clearTimeout(timer); fonte?.close(); };
  }

  /** Central de avisos: lista e total de não lidos. null = ponte ausente. */
  async avisos(): Promise<{ avisos: Aviso[]; nao_lidos: number } | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/avisos`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        const bruto: unknown[] = Array.isArray(j.avisos) ? j.avisos : [];
        const lista = bruto.map(normalizarAviso).filter((a): a is Aviso => a !== null);
        return { avisos: lista, nao_lidos: typeof j.nao_lidos === "number" ? j.nao_lidos : lista.filter((a) => !a.lido).length };
      });
    } catch { return null; }
  }

  /** Marca avisos como lidos (ids dados ou todos). null = ponte ausente. */
  async marcarLidos(ids?: number[]): Promise<{ ok: boolean; nao_lidos: number } | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(10000, async (signal) => {
        const r = await fetch(`${this.base}/avisos/lidos`, {
          method: "POST", headers: { "Content-Type": "application/json" }, signal,
          body: JSON.stringify(ids ? { ids } : {}),
        });
        if (!r.ok) return null;
        const j = await r.json();
        return { ok: j.ok === true, nao_lidos: typeof j.nao_lidos === "number" ? j.nao_lidos : 0 };
      });
    } catch { return null; }
  }

  /** Texto do resultado de uma tarefa. null = ponte ausente ou tarefa não existe (404). */
  async resultadoTarefa(n: number): Promise<ResultadoTarefa | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(10000, async (signal) => {
        const r = await fetch(`${this.base}/tarefas/${n}/resultado`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        return { n: typeof j.n === "number" ? j.n : n, estado: String(j.estado ?? ""), resumo: String(j.resumo ?? ""), texto: String(j.texto ?? "") };
      });
    } catch { return null; }
  }
}
