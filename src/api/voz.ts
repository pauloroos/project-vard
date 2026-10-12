// Serviço de voz próprio e opcional (contrato em docs/voz-propria.md): POST /falar devolve PCM 16 bits em fluxo.
import { fluxoParaWav } from "../audio/wav";

/** Falha do serviço de voz. `conexao` = nem respondeu (fora do ar, caiu no meio ou passou do prazo). */
export class ErroVoz extends Error {
  constructor(mensagem: string, readonly conexao: boolean) {
    super(mensagem);
    this.name = "ErroVoz";
  }
}

export interface FalaEmFluxo { corpo: ReadableStream<Uint8Array>; taxa: number }

interface OpcoesVoz {
  /** fetch alternativo (testes). */
  fetch?: (url: string, init: RequestInit) => Promise<Response>;
  /** Prazo até o primeiro byte de áudio e entre um pedaço e outro. */
  prazoMs?: number;
}

const PRAZO_MS = 8000;
const TAXA_PADRAO = 24000; // o cabeçalho X-Taxa só é legível com Access-Control-Expose-Headers

export class Voz {
  /** Nome da voz informado pelo /saude ("" até a primeira resposta). Entra na chave do cache das falas fixas. */
  nome = "";
  private base: string;
  private buscar: (url: string, init: RequestInit) => Promise<Response>;
  private prazo: number;

  constructor(url: string, opcoes: OpcoesVoz = {}) {
    this.base = url.replace(/\/+$/, "");
    this.buscar = opcoes.fetch ?? ((u, i) => fetch(u, i));
    this.prazo = opcoes.prazoMs ?? PRAZO_MS;
  }

  /** true só quando o serviço responde e diz que está pronto (modelo carregado). */
  async saude(): Promise<boolean> {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 3000);
    try {
      const r = await this.buscar(`${this.base}/saude`, { signal: ac.signal });
      if (!r.ok) return false;
      const j = await r.json();
      if (typeof j?.voz === "string") this.nome = j.voz;
      return j?.pronta === true;
    } catch { return false; } finally { clearTimeout(t); }
  }

  /**
   * Pede a fala de um trecho e resolve quando o primeiro pedaço de áudio chega (prazo de 8 s, ou `prazoMs`).
   * O corpo devolvido entrega o PCM conforme o serviço sintetiza; cancelar o corpo ou abortar `sinal` encerra o pedido.
   */
  async falar(texto: string, velocidade: number, sinal?: AbortSignal, prazoMs?: number): Promise<FalaEmFluxo> {
    const prazo = prazoMs ?? this.prazo;
    if (sinal?.aborted) throw new ErroVoz("interrompido", false);
    const ac = new AbortController();
    let estourou = false;
    let relogio: ReturnType<typeof setTimeout> | undefined;
    let leitor: ReadableStreamDefaultReader<Uint8Array> | undefined;
    // Abortar o pedido também solta a leitura do corpo (um corpo que não obedece ao abort não pendura a fila).
    const encerrar = () => { ac.abort(); void leitor?.cancel().catch(() => {}); };
    const armar = () => { clearTimeout(relogio); relogio = setTimeout(() => { estourou = true; encerrar(); }, prazo); };
    const repassar = () => encerrar();
    sinal?.addEventListener("abort", repassar);
    const soltar = () => { clearTimeout(relogio); sinal?.removeEventListener("abort", repassar); };
    const caiu = (erro: unknown) => new ErroVoz(estourou ? "a voz passou do prazo" : `sem conexão com a voz: ${String(erro)}`, true);

    armar();
    try {
      let r: Response;
      try {
        r = await this.buscar(`${this.base}/falar`, {
          method: "POST", signal: ac.signal,
          headers: { "Content-Type": "application/json", Accept: "audio/pcm" },
          body: JSON.stringify({ texto, velocidade }),
        });
      } catch (erro) { throw caiu(erro); }
      if (!r.ok) { void r.body?.cancel().catch(() => {}); throw new ErroVoz(`voz HTTP ${r.status}`, false); }
      if (!r.body) throw new ErroVoz("voz sem corpo", false);
      const taxa = Number(r.headers.get("X-Taxa")) || TAXA_PADRAO;
      const fonte = r.body.getReader();
      leitor = fonte;
      let primeiro: Uint8Array | undefined;
      try {
        for (;;) {
          const { done, value } = await fonte.read();
          if (done) break;
          if (value?.length) { primeiro = value; break; }
        }
      } catch (erro) { throw caiu(erro); }
      if (estourou || sinal?.aborted) throw caiu("pedido encerrado");
      if (!primeiro) throw new ErroVoz("voz sem áudio", false);
      clearTimeout(relogio);

      let pendente: Uint8Array | null = primeiro;
      const corpo = new ReadableStream<Uint8Array>({
        pull: async (ctrl) => {
          if (pendente) { ctrl.enqueue(pendente); pendente = null; return; }
          armar();
          try {
            // Repete até ter bytes: um pull que volta sem enfileirar nada deixaria a leitura pendurada.
            for (;;) {
              const { done, value } = await fonte.read();
              if (done && (estourou || sinal?.aborted)) throw new Error("pedido encerrado");
              if (done) { soltar(); ctrl.close(); return; }
              if (value?.length) { ctrl.enqueue(value); return; }
            }
          } catch (erro) {
            soltar();
            ctrl.error(caiu(erro));
          } finally { clearTimeout(relogio); }
        },
        cancel: async () => {
          soltar();
          ac.abort();
          await fonte.cancel().catch(() => {});
        },
      });
      return { corpo, taxa };
    } catch (erro) {
      soltar();
      encerrar();
      throw erro;
    }
  }

  /** A fala inteira como WAV (para as falas fixas, que vão para o cache). */
  async falarWav(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer> {
    const { corpo, taxa } = await this.falar(texto, velocidade, undefined, prazoMs);
    return fluxoParaWav(corpo, taxa);
  }
}
