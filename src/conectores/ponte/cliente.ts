// Cliente da ponte opcional do Vard (127.0.0.1:4700). Sem ponte o HUD funciona igual: tudo aqui falha em silêncio.
export interface StatusPonte { ok: boolean; modo: string; detalhe?: string; reserva?: string; tarefas_abertas?: number; modelos_lmstudio?: string[]; reuniao?: "ativa" | "inativa" | "ausente" }

/** Estado da reunião segundo o /reuniao/status da ponte. */
export interface StatusReuniao { ativa: boolean; pasta?: string; inicio?: string; duracao_s?: number; falas?: number }

/** Uma reunião já terminada, como o /reuniao/lista devolve. */
export interface ReuniaoDaLista { pasta: string; inicio: string; fim: string; duracao_s: number; ata: boolean; relatorio: boolean }

/** Resultado de um pedido de reunião: `frase` é o texto (em português) para mostrar na tela. */
export interface ResultadoReuniao { ok: boolean; frase: string }

/** Frase fixa quando a ponte responde 503 (o serviço da reunião não está instalado ou caiu). */
export const FRASE_REUNIAO_AUSENTE = "A reunião não está instalada ou está fora do ar.";

/** Um aviso da central da ponte. `n` só existe nos do tipo tarefa. */
export interface Aviso { id: number; hora: string; tipo: string; resumo: string; n?: number; estado?: string; lido: boolean }

/** Resultado de uma tarefa da ponte. */
export interface ResultadoTarefa { n: number; estado: string; resumo: string; texto: string }

/** Uma tarefa em andamento segundo o /tarefas/andamento da ponte (só as que estão rodando). */
export interface TarefaAndamento { n: number; ferramenta: string; quem: string; estado: string; resumo: string; segundos: number }

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

/** `frase` da ponte quando ela manda texto; o padrão entra quando o corpo não veio ou veio vazio. */
function fraseDe(j: unknown, padrao: string): string {
  const f = (j as { frase?: unknown } | null)?.frase;
  return typeof f === "string" && f.trim() ? f.trim() : padrao;
}

/** Flag de documento pronto: `true` ou um caminho/texto não vazio (a ponte pode devolver os dois). */
function pronto(v: unknown): boolean { return v === true || (typeof v === "string" && v.trim() !== ""); }

function paraBlob(b64: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: "image/jpeg" });
}

/** Estado de um pedido do cérebro próprio segundo /pedidos/{id}. */
export interface EstadoPedido {
  pedido_id: string;
  sessao_id: string;
  estado: "na_fila" | "executando" | "concluido" | "falhou" | "cancelado";
  resposta?: string | null;
  erro?: string | null;
  ultimo_seq?: number;
}

/** Evento SSE do tipo 'pedido' emitido pelo /events. */
export interface EventoPedidoSSE {
  tipo: "pedido";
  pedido_id: string;
  sessao_id: string;
  seq: number;
  evento_tipo: "estado" | "texto" | "ferramenta" | "reserva" | "fim" | "erro";
  dados: Record<string, unknown>;
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
        const reuniao = j.reuniao === "ativa" || j.reuniao === "inativa" || j.reuniao === "ausente" ? j.reuniao : undefined;
        return { ok: j.openjarvis === true && j.lmstudio === true, modo: String(j.modo ?? ""), detalhe, reserva, tarefas_abertas, modelos_lmstudio: modelos, ...(reuniao ? { reuniao } : {}) };
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

  /** Admite um pedido no cérebro próprio via POST /pedidos. Devolve o estado inicial. */
  async pedir(texto: string, sessaoId: string, origem = "painel"): Promise<EstadoPedido> {
    const pedidoId = crypto.randomUUID();
    return comTimeout(5000, async (signal) => {
      let r: Response;
      try {
        r = await fetch(`${this.base}/pedidos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal,
          body: JSON.stringify({ pedido_id: pedidoId, sessao_id: sessaoId, origem, texto }),
        });
      } catch { throw new ErroPonte("rede"); }
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new ErroPonte(String(j?.erro ?? "pedido_http"));
      return j as EstadoPedido;
    });
  }

  /** Cancela um pedido existente via POST /pedidos/{id}/cancelar. */
  async cancelar(pedidoId: string): Promise<EstadoPedido> {
    return comTimeout(5000, async (signal) => {
      let r: Response;
      try {
        r = await fetch(`${this.base}/pedidos/${encodeURIComponent(pedidoId)}/cancelar`, {
          method: "POST",
          signal,
        });
      } catch { throw new ErroPonte("rede"); }
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new ErroPonte(String(j?.erro ?? "cancelar_http"));
      return j as EstadoPedido;
    });
  }

  /** Consulta o estado de um pedido via GET /pedidos/{id}. */
  async consultarPedido(pedidoId: string): Promise<EstadoPedido | null> {
    try {
      return await comTimeout(3000, async (signal) => {
        const r = await fetch(`${this.base}/pedidos/${encodeURIComponent(pedidoId)}`, { signal });
        if (!r.ok) return null;
        return (await r.json()) as EstadoPedido;
      });
    } catch { return null; }
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

  /** Tarefas em andamento (só as rodando; as que aguardam aprovação não entram). null = ponte ausente. */
  async andamento(): Promise<{ total: number; tarefas: TarefaAndamento[] } | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/tarefas/andamento`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        const bruto: unknown[] = Array.isArray(j.tarefas) ? j.tarefas : [];
        const tarefas = bruto
          .filter((x): x is Record<string, unknown> => typeof x === "object" && x !== null)
          .map((o) => ({
            n: typeof o.n === "number" ? o.n : 0,
            ferramenta: typeof o.ferramenta === "string" ? o.ferramenta : "",
            quem: typeof o.quem === "string" ? o.quem : "",
            estado: typeof o.estado === "string" ? o.estado : "",
            resumo: typeof o.resumo === "string" ? o.resumo : "",
            segundos: typeof o.segundos === "number" ? o.segundos : 0,
          }));
        return { total: typeof j.total === "number" ? j.total : tarefas.length, tarefas };
      });
    } catch { return null; }
  }

  /** Estado da reunião agora (a ponte manda o serviço da reunião responder). null = ponte ausente. */
  async reuniaoStatus(): Promise<StatusReuniao | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/reuniao/status`, { signal });
        if (!r.ok) return null;
        const j = await r.json();
        return {
          ativa: j.ativa === true,
          ...(typeof j.pasta === "string" && j.pasta ? { pasta: j.pasta } : {}),
          ...(typeof j.inicio === "string" && j.inicio ? { inicio: j.inicio } : {}),
          ...(typeof j.duracao_s === "number" ? { duracao_s: j.duracao_s } : {}),
          ...(typeof j.falas === "number" ? { falas: j.falas } : {}),
        };
      });
    } catch { return null; }
  }

  /** Pede o começo da reunião. null = ponte ausente (ou serviço da reunião fora, tratado pela `frase`). */
  async iniciarReuniao(): Promise<ResultadoReuniao | null> {
    return this.pedidoReuniao("iniciar", "Reunião iniciada.", { 409: "Já há uma reunião em andamento." });
  }

  /** Pede o fim da reunião (quem encerra é o serviço da reunião, não o widget). null = ponte ausente. */
  async encerrarReuniao(): Promise<ResultadoReuniao | null> {
    return this.pedidoReuniao("encerrar", "Reunião encerrada.", { 409: "Não há reunião em andamento." });
  }

  /** POST /reuniao/{iniciar,encerrar}: o corpo vem com `frase` pronta; sem ela, entra o texto padrão do erro. */
  private async pedidoReuniao(rota: "iniciar" | "encerrar", ok: string, erros: Record<number, string>): Promise<ResultadoReuniao | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(10000, async (signal) => {
        const r = await fetch(`${this.base}/reuniao/${rota}`, { method: "POST", signal });
        const j: unknown = await r.json().catch(() => null);
        if (r.status === 503) return { ok: false, frase: FRASE_REUNIAO_AUSENTE };
        if (!r.ok) return { ok: false, frase: fraseDe(j, erros[r.status] ?? "A ponte não aceitou o pedido.") };
        return { ok: true, frase: fraseDe(j, ok) };
      });
    } catch { return null; }
  }

  /** As últimas reuniões (a mais nova primeiro). null = ponte ausente ou nenhum registro. */
  async listaReuniao(n = 1): Promise<ReuniaoDaLista[] | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(5000, async (signal) => {
        const r = await fetch(`${this.base}/reuniao/lista?n=${Math.max(1, Math.round(n))}`, { signal });
        if (!r.ok) return null;
        const j: unknown = await r.json();
        if (!Array.isArray(j)) return null;
        return j.map((x): ReuniaoDaLista => {
          const o = (typeof x === "object" && x !== null ? x : {}) as Record<string, unknown>;
          return {
            pasta: String(o.pasta ?? ""), inicio: String(o.inicio ?? ""), fim: String(o.fim ?? ""),
            duracao_s: typeof o.duracao_s === "number" ? o.duracao_s : 0,
            ata: pronto(o.ata), relatorio: pronto(o.relatorio),
          };
        });
      });
    } catch { return null; }
  }

  /** Lê a preferência de dispositivos de áudio da reunião (GET /reuniao/dispositivos). */
  async lerDispositivosReuniao(): Promise<{ microfone_id: string; microfone_rotulo: string; saida_id: string; saida_rotulo: string } | null> {
    if (!this.base) return null;
    try {
      const r = await fetch(`${this.base}/reuniao/dispositivos`, { signal: AbortSignal.timeout(5000) });
      if (!r.ok) return null;
      const j = await r.json().catch(() => null);
      if (!j || typeof j !== "object") return null;
      return {
        microfone_id: String((j as Record<string, unknown>).microfone_id ?? ""),
        microfone_rotulo: String((j as Record<string, unknown>).microfone_rotulo ?? ""),
        saida_id: String((j as Record<string, unknown>).saida_id ?? ""),
        saida_rotulo: String((j as Record<string, unknown>).saida_rotulo ?? ""),
      };
    } catch { return null; }
  }

  /** Grava a preferência de dispositivos de áudio da reunião (POST /reuniao/dispositivos). */
  async gravarDispositivosReuniao(pref: { microfone_id: string; microfone_rotulo: string; saida_id: string; saida_rotulo: string }): Promise<boolean> {
    if (!this.base) return false;
    try {
      const r = await fetch(`${this.base}/reuniao/dispositivos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pref),
        signal: AbortSignal.timeout(5000),
      });
      return r.ok;
    } catch { return false; }
  }

  /** Gera a ata ou o relatório (qual: "ultima"). A ponte responde a `frase` pronta em ok e em erro (404/409). */
  async gerarAta(tipo: "ata" | "relatorio", qual = "ultima"): Promise<ResultadoReuniao | null> {
    if (!this.base) return null;
    try {
      return await comTimeout(120000, async (signal) => {
        const r = await fetch(`${this.base}/reuniao/ata`, {
          method: "POST", headers: { "Content-Type": "application/json" }, signal,
          body: JSON.stringify({ tipo, qual }),
        });
        const j: unknown = await r.json().catch(() => null);
        if (r.status === 503) return { ok: false, frase: FRASE_REUNIAO_AUSENTE };
        return { ok: r.ok && (j as { ok?: unknown } | null)?.ok !== false, frase: fraseDe(j, r.ok ? (tipo === "ata" ? "Ata gerada." : "Relatório gerado.") : "Não consegui gerar o documento.") };
      });
    } catch { return null; }
  }
}
