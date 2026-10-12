import { pcm16ParaFloat } from "./wav";

/** Áudio acumulado antes do primeiro trecho de um fluxo começar (evita buracos se o próximo pedaço atrasar). */
const PRE_BUFFER_S = 0.1;
/** Folga mínima entre agendar um trecho e ele começar. */
const FOLGA_S = 0.02;

/** Toca WAVs e fluxos de PCM pelo mesmo AudioContext do microfone; expõe um analisador para o núcleo reagir. */
export class Boca {
  readonly analisador: AnalyserNode;
  falando = false;
  /** Para o que estiver tocando e resolve a promessa de quem tocou. */
  private fim: (() => void) | null = null;
  /** Muda a cada parar(): um tocar que ainda estava decodificando não começa depois de parado. */
  private geracao = 0;

  constructor(private contexto: AudioContext) {
    this.analisador = contexto.createAnalyser();
    this.analisador.fftSize = 256;
    this.analisador.smoothingTimeConstant = 0.8;
    this.analisador.connect(contexto.destination);
  }

  async tocar(wav: ArrayBuffer): Promise<void> {
    this.parar();
    const g = this.geracao;
    if (this.contexto.state === "suspended") await this.contexto.resume();
    const buffer = await this.contexto.decodeAudioData(wav.slice(0));
    if (g !== this.geracao) return; // parado enquanto decodificava
    const fonte = this.contexto.createBufferSource();
    fonte.buffer = buffer;
    fonte.connect(this.analisador);
    this.falando = true;
    await new Promise<void>((resolve) => {
      let feito = false;
      const terminar = () => {
        if (feito) return;
        feito = true;
        fonte.onended = null;
        try { fonte.stop(); } catch { /* já parada */ }
        if (this.fim === terminar) { this.fim = null; this.falando = false; }
        resolve();
      };
      this.fim = terminar;
      fonte.onended = terminar;
      fonte.start();
    });
  }

  /**
   * Toca PCM 16 bits mono conforme chega: cada pedaço vira um AudioBuffer agendado logo depois do anterior.
   * Resolve quando o último trecho termina; parar() ou `sinal` cortam o som e cancelam a leitura.
   * Se o fluxo falhar no meio, corta o som e rejeita com o erro do fluxo.
   */
  async tocarFluxo(corpo: ReadableStream<Uint8Array>, taxa: number, sinal?: AbortSignal): Promise<void> {
    this.parar();
    const leitor = corpo.getReader();
    const fontes = new Set<AudioBufferSourceNode>();
    let acabou = false;
    let fluxoNoFim = false;
    let resolver!: () => void;
    const fim = new Promise<void>((r) => { resolver = r; });
    const terminar = () => {
      if (acabou) return;
      acabou = true;
      for (const f of fontes) { f.onended = null; try { f.stop(); } catch { /* já parada */ } }
      fontes.clear();
      void leitor.cancel().catch(() => {});
      sinal?.removeEventListener("abort", terminar);
      if (this.fim === terminar) { this.fim = null; this.falando = false; }
      resolver();
    };
    this.fim = terminar;
    if (sinal?.aborted) { terminar(); return; }
    sinal?.addEventListener("abort", terminar);
    this.falando = true;

    let proximoInicio = 0;
    const agendar = (amostras: Float32Array) => {
      if (acabou || amostras.length === 0) return;
      const buffer = this.contexto.createBuffer(1, amostras.length, taxa);
      buffer.getChannelData(0).set(amostras);
      const fonte = this.contexto.createBufferSource();
      fonte.buffer = buffer;
      fonte.connect(this.analisador);
      const inicio = Math.max(proximoInicio, this.contexto.currentTime + FOLGA_S);
      proximoInicio = inicio + buffer.duration;
      fontes.add(fonte);
      fonte.onended = () => {
        fontes.delete(fonte);
        if (fluxoNoFim && fontes.size === 0) terminar();
      };
      fonte.start(inicio);
    };

    try {
      if (this.contexto.state === "suspended") await this.contexto.resume();
      const minimo = Math.round(taxa * PRE_BUFFER_S);
      let sobra: Uint8Array | undefined;
      let espera: Float32Array[] = []; // antes do primeiro trecho: junta até ~100 ms
      let emEspera = 0;
      let comecou = false;
      const soltarEspera = () => {
        const tudo = new Float32Array(emEspera);
        let o = 0;
        for (const a of espera) { tudo.set(a, o); o += a.length; }
        espera = []; emEspera = 0; comecou = true;
        agendar(tudo);
      };
      while (!acabou) {
        const { done, value } = await leitor.read();
        if (done || acabou) break;
        if (!value?.length) continue;
        const r = pcm16ParaFloat(value, sobra);
        sobra = r.sobra;
        if (comecou) { agendar(r.amostras); continue; }
        espera.push(r.amostras); emEspera += r.amostras.length;
        if (emEspera >= minimo) soltarEspera();
      }
      if (!acabou && emEspera > 0) soltarEspera(); // fala mais curta que o pre-buffer
    } catch (erro) {
      if (!acabou) {
        // O fluxo caiu no meio: corta o que já estava agendado e avisa quem tocou, para refazer a frase por outra voz.
        terminar();
        throw erro;
      }
    }
    fluxoNoFim = true;
    if (fontes.size === 0) terminar();
    await fim;
  }

  parar(): void {
    this.geracao++;
    const f = this.fim;
    this.fim = null;
    this.falando = false;
    f?.();
  }
}
