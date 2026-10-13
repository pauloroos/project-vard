import { gatilhos, type Config } from "../config/config";
import { fluxoParaWav } from "../audio/wav";
import { FALAS, saudacaoPara } from "./falas";
import { cortarEmFrases } from "./frases";
import { ehEncerramento } from "./encerramento";
import { aPartirDoGatilho, classificar, ehConfirmacao, ehInterrupcao, extrairComando } from "./rotas";

export type Estado = "repouso" | "ouvindo" | "pensando" | "falando" | "jogo" | "erro" | "fora";
export interface Mensagem { role: "system" | "user" | "assistant"; content: string }
/** PCM 16 bits mono em fluxo, como o serviço de voz entrega. */
export interface FalaEmFluxo { corpo: ReadableStream<Uint8Array>; taxa: number }
/** Uma frase pronta para tocar: em fluxo (voz própria) ou WAV inteiro (reserva no OpenJarvis). */
type Som = { fluxo: ReadableStream<Uint8Array>; taxa: number } | { wav: ArrayBuffer };

/** Fecha o pedido de uma frase que não vai mais tocar. */
function descartar(som: Som | null | undefined): void {
  if (som && "fluxo" in som) void som.fluxo.cancel().catch(() => {});
}

export interface DepsConversa {
  oj: {
    perguntar(mensagens: Mensagem[], sinal?: AbortSignal): Promise<string>;
    sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer>;
  };
  boca: {
    falando: boolean;
    tocar(wav: ArrayBuffer): Promise<void>;
    /** Toca PCM conforme chega. Sem isto a frase da voz própria é lida inteira e tocada como WAV. */
    tocarFluxo?(corpo: ReadableStream<Uint8Array>, taxa: number, sinal?: AbortSignal): Promise<void>;
    parar(): void;
  };
  /** Serviço de voz próprio e opcional (docs/voz-propria.md). Sem ele, ou quando ele falha, a voz é a do OpenJarvis. */
  voz?: { falar(texto: string, velocidade: number, sinal?: AbortSignal): Promise<FalaEmFluxo> };
  /** Fala fixa já sintetizada (com cache). */
  falas: (texto: string) => Promise<ArrayBuffer>;
  config: Pick<Config, "nome" | "variantes" | "voz" | "velocidade" | "instrucao_formato" | "conversa_ms"> & Partial<Pick<Config, "usuario">>;
  /** Ponte opcional do Vard: olhos na tela e modo jogo. */
  ponte?: {
    ver(jpegB64: string, pergunta: string): Promise<string>;
    modo(verbo: string): Promise<boolean>;
  };
  /** A ponte respondeu na última sondagem? Sem isto, a ponte (se existir) conta como no ar. */
  ponteNoAr?: () => boolean;
  /** JPEG em base64 do monitor sob a janela. */
  capturar?: () => Promise<string>;
  /** Acende o indicador vermelho e espera ~1 s antes da captura. */
  antesDaCaptura?: () => Promise<void>;
  /** Apaga o indicador vermelho: chamado sempre que a captura termina, falha ou é interrompida. */
  depoisDaCaptura?: () => void;
  abrirMicrofone?: () => void | Promise<void>;
  /** Devolve false se o microfone nem estava aberto (então a volta do jogo não o abre). */
  fecharMicrofone?: () => boolean | void | Promise<boolean | void>;
  aoEstado?: (e: Estado, detalhe: string) => void;
  aoResposta?: (texto: string) => void;
  /** Frase de encerramento ("pode parar de me ouvir"): quem usa muta o microfone. */
  mutar?: () => void;
  /** O modo conversa abriu (true) ou fechou (false): o nome está dispensado enquanto aberto. */
  aoCanal?: (aberto: boolean) => void;
}

const MAX_MENSAGENS = 20; // 10 trocas
const PRAZO_CONFIRMACAO_MS = 15000;

export class Conversa {
  estado: Estado = "repouso";
  detalhe = "";
  historico: Mensagem[] = [];
  private foraAvisado = false;
  private aguardaConfirmacao = 0; // instante em que o modo jogo foi pedido; 0 = nada a confirmar
  private microfoneFechado = false;
  private erroPonte = false;
  private pergunta: AbortController | null = null;
  private canalAte = 0; // instante em que o modo conversa fecha; 0 = fechado
  private relogioCanal: ReturnType<typeof setTimeout> | null = null;
  private entrandoEmJogo = false; // aviso do modo jogo tocando: a sondagem da ponte não mexe no estado

  constructor(private d: DepsConversa) {}

  /** Modo conversa: depois de uma resposta, o nome fica dispensado até o silêncio de `conversa_ms`. */
  canalAberto(): boolean { return this.canalAte > 0 && Date.now() < this.canalAte; }

  private abrirCanal() {
    const ms = this.d.config.conversa_ms;
    if (!(ms > 0)) return;
    const estava = this.canalAte > 0; // simétrico ao fecharCanal: não depende do relógio
    this.canalAte = Date.now() + ms;
    if (this.relogioCanal) clearTimeout(this.relogioCanal);
    this.relogioCanal = setTimeout(() => this.fecharCanal(), ms);
    if (!estava) this.d.aoCanal?.(true);
  }

  private fecharCanal() {
    if (this.relogioCanal) { clearTimeout(this.relogioCanal); this.relogioCanal = null; }
    const estava = this.canalAte > 0; // não por canalAberto(): no disparo do relógio o instante já passou
    this.canalAte = 0;
    if (estava) this.d.aoCanal?.(false);
  }

  /** Método (não comparação direta) para o TypeScript não estreitar `estado` através dos await. */
  private emJogo(): boolean { return this.estado === "jogo"; }

  private mudar(e: Estado, detalhe = "") {
    this.estado = e;
    this.detalhe = detalhe;
    this.d.aoEstado?.(e, detalhe);
  }

  private async tocar(wav: Promise<ArrayBuffer>, mudarEstado = true) {
    try {
      const w = await wav;
      if (mudarEstado) this.mudar("falando");
      await this.d.boca.tocar(w);
    } catch (erro) {
      console.warn("falha ao falar", erro);
    }
  }

  private async falarFixa(texto: string, mudarEstado = true) {
    await this.tocar(this.d.falas(texto), mudarEstado);
    if (mudarEstado && this.estado === "falando") this.mudar("repouso");
  }

  /** Fala a resposta frase a frase: a frase seguinte é pedida antes de a atual começar a tocar. */
  private async falarEmFrases(texto: string, sinal: AbortSignal): Promise<void> {
    const frases = cortarEmFrases(texto);
    if (frases.length === 0) return;
    const d = this.d;
    const t0 = performance.now();
    let soReserva = !d.voz; // depois de um erro de conexão, o resto desta resposta vai pela reserva
    const sintetizar = async (frase: string): Promise<Som | null> => {
      if (!soReserva && d.voz) {
        try {
          const r = await d.voz.falar(frase, d.config.velocidade, sinal);
          if (sinal.aborted) { descartar({ fluxo: r.corpo, taxa: r.taxa }); return null; }
          return { fluxo: r.corpo, taxa: r.taxa };
        } catch (erro) {
          if (sinal.aborted) return null;
          if ((erro as { conexao?: unknown } | null)?.conexao === true) soReserva = true;
          console.warn("voz própria falhou, usei a reserva", erro);
        }
      }
      if (sinal.aborted) return null;
      return { wav: await reserva(frase) };
    };
    const reserva = (frase: string) => d.oj.sintetizar(frase, d.config.voz, d.config.velocidade);
    let caiuNoMeio = false; // a voz caiu no meio de uma frase: o resto da resposta nem tenta a voz
    const pararBoca = () => d.boca.parar();
    sinal.addEventListener("abort", pararBoca);
    let pendente: Promise<Som | null> | null = sintetizar(frases[0]);
    let primeiro = true;
    try {
      for (let i = 0; i < frases.length; i++) {
        let som: Som | null = null;
        try { som = await pendente; } catch (erro) { console.warn("falha ao sintetizar a frase", erro); }
        pendente = null;
        if (sinal.aborted || this.emJogo()) { descartar(som); return; }
        if (i + 1 < frases.length) pendente = sintetizar(frases[i + 1]);
        if (!som) continue;
        if (caiuNoMeio && "fluxo" in som) { // pedida antes da queda: refaz pela reserva
          descartar(som);
          try { som = { wav: await reserva(frases[i]) }; } catch (erro) { console.warn("falha ao sintetizar a frase", erro); continue; }
          if (sinal.aborted) return;
        }
        if (primeiro) {
          primeiro = false;
          console.info(`voz: 1º áudio em ${Math.round(performance.now() - t0)} ms após a resposta`);
        }
        if (this.estado !== "falando") this.mudar("falando");
        try {
          await this.tocarSom(som, sinal);
        } catch (erro) {
          if (sinal.aborted) return;
          console.warn("falha ao falar", erro);
          if ("fluxo" in som) {
            // A voz própria caiu no meio da frase: ela é falada de novo, inteira, pela reserva, e o resto da resposta também.
            soReserva = true;
            caiuNoMeio = true;
            try {
              const wav = await reserva(frases[i]);
              if (!sinal.aborted) await d.boca.tocar(wav);
            } catch (erro2) { console.warn("falha ao falar pela reserva", erro2); }
          }
        }
        if (sinal.aborted) return;
      }
    } finally {
      sinal.removeEventListener("abort", pararBoca);
      if (pendente) void pendente.then(descartar, () => {}); // interrompido: a frase já pedida não toca
    }
  }

  private async tocarSom(som: Som, sinal: AbortSignal): Promise<void> {
    const boca = this.d.boca;
    if ("wav" in som) return boca.tocar(som.wav);
    if (boca.tocarFluxo) return boca.tocarFluxo(som.fluxo, som.taxa, sinal);
    const wav = await fluxoParaWav(som.fluxo, som.taxa);
    if (!sinal.aborted) await boca.tocar(wav);
  }

  async aoTextoTranscrito(texto: string, pushToTalk: boolean): Promise<void> {
    // Entre uma frase e outra a boca fica muda por um instante: o estado "falando" segura a vez.
    if (this.d.boca.falando || this.estado === "falando") return;
    const inicio = performance.now();
    if (this.estado === "fora" || this.estado === "erro" || this.emJogo()) return;
    const bruto = texto.trim();
    if (!bruto) return;
    const v = gatilhos(this.d.config);

    // Confirmação do modo jogo: vale só a próxima frase; "sim" ou "confirmo" sozinhos (com ou sem o nome).
    if (this.aguardaConfirmacao) {
      const dentroDoPrazo = Date.now() - this.aguardaConfirmacao <= PRAZO_CONFIRMACAO_MS;
      this.aguardaConfirmacao = 0;
      if (dentroDoPrazo && ehConfirmacao(extrairComando(bruto, v) ?? bruto)) { await this.ativarJogo(); return; }
    }

    // Frase de encerramento: com ou sem o nome na frente. Fala "Parei de ouvir." e muta até alguém reativar.
    if (ehEncerramento(extrairComando(bruto, v) ?? bruto)) {
      this.fecharCanal();
      await this.falarFixa(FALAS.pareiDeOuvir);
      this.d.mutar?.();
      return;
    }

    let comando: string;
    if (pushToTalk) {
      comando = extrairComando(bruto, v) ?? bruto;
    } else {
      const apartir = aPartirDoGatilho(bruto, v);
      if (apartir === null) { if (!this.canalAberto()) return; comando = bruto; } else comando = extrairComando(apartir, v) ?? apartir;
    }
    if (comando === "") { await this.falarFixa(saudacaoPara(this.d.config.usuario)); this.abrirCanal(); return; }
    if (ehInterrupcao(comando)) return;

    const rota = classificar(comando);
    if (rota !== "ask") {
      const d = this.d;
      if (!d.ponte || d.ponteNoAr?.() === false) { await this.falarFixa(FALAS.semPonte); return; }
      if (rota === "modo") {
        this.aguardaConfirmacao = Date.now();
        await this.falarFixa(FALAS.modoJogoConfirmar);
        return;
      }
    }

    this.mudar("pensando");
    // O relógio velho não pode fechar o canal no meio de uma resposta longa (pisca no modo invisível): o canal segue "aberto" e o fim da resposta rearma.
    if (this.relogioCanal) { clearTimeout(this.relogioCanal); this.relogioCanal = null; }
    this.pergunta?.abort();
    const ac = new AbortController();
    this.pergunta = ac;
    const ver = rota === "see";
    let resposta: string;
    try {
      if (ver) {
        if (!this.d.capturar || !this.d.ponte) throw new Error("sem captura");
        let jpeg: string;
        try {
          await this.d.antesDaCaptura?.();
          if (ac.signal.aborted) return;
          jpeg = await this.d.capturar();
        } finally { this.d.depoisDaCaptura?.(); }
        resposta = (await this.d.ponte.ver(jpeg, comando)).trim();
      } else {
        resposta = (await this.d.oj.perguntar([
          { role: "system", content: this.d.config.instrucao_formato },
          ...this.historico,
          { role: "user", content: comando },
        ], ac.signal)).trim();
      }
      if (ac.signal.aborted || this.emJogo()) return;
      if (!resposta) throw new Error("resposta vazia");
      console.info(`resposta do núcleo em ${Math.round(performance.now() - inicio)} ms`);
    } catch (erro) {
      if (ac.signal.aborted || this.emJogo()) return;
      console.warn(ver ? "olhos falharam" : "agente falhou", erro);
      const codigo = (erro as { codigo?: string } | null)?.codigo;
      const fala = (codigo && (FALAS.erros as Record<string, string>)[codigo]) || FALAS.erroModelo;
      await this.falarFixa(fala);
      this.abrirCanal();
      if (this.estado !== "repouso") this.mudar("repouso");
      return;
    }
    if (!ver) {
      this.historico.push({ role: "user", content: comando }, { role: "assistant", content: resposta });
      if (this.historico.length > MAX_MENSAGENS) this.historico = this.historico.slice(-MAX_MENSAGENS);
    }
    this.d.aoResposta?.(resposta);
    if (this.emJogo()) return;
    await this.falarEmFrases(resposta, ac.signal);
    if (this.pergunta === ac) this.pergunta = null;
    if (!ac.signal.aborted && !this.emJogo()) { this.abrirCanal(); this.mudar("repouso"); }
  }

  private async ativarJogo(): Promise<void> {
    const ponte = this.d.ponte;
    if (!ponte) { await this.falarFixa(FALAS.semPonte); return; }
    // Sintetiza o aviso antes: o modo jogo derruba o OpenJarvis (e a voz) logo em seguida.
    const aviso = this.d.falas(FALAS.modoJogoAtivado);
    aviso.catch(() => {});
    this.entrandoEmJogo = true;
    try {
      if (!(await ponte.modo("jogo"))) { this.entrandoEmJogo = false; await this.falarFixa(FALAS.erros.modo_falhou); return; }
      await this.tocar(aviso, false);
      this.entrarNoJogo();
      this.microfoneFechado = (await this.d.fecharMicrofone?.()) !== false || this.microfoneFechado;
    } finally { this.entrandoEmJogo = false; }
  }

  /** Muda para o jogo e cancela a pergunta em voo (a resposta tardia não tira o HUD do jogo). */
  private entrarNoJogo() {
    this.fecharCanal();
    this.pergunta?.abort();
    this.pergunta = null;
    this.mudar("jogo");
  }

  /** Resultado da sondagem da ponte (a cada 10 s). null = ponte ausente. Cuida de entrar e sair do modo jogo. */
  async aoStatusPonte(s: { modo: string; detalhe?: string } | null): Promise<void> {
    if (!s) return;
    if (this.entrandoEmJogo) return; // o aviso está tocando: ativarJogo termina a transição sozinha
    const emJogo = this.estado === "jogo";
    if (s.modo === "ligado" && (emJogo || this.erroPonte)) {
      this.erroPonte = false;
      if (this.microfoneFechado) { this.microfoneFechado = false; await this.d.abrirMicrofone?.(); }
      this.mudar("repouso");
      await this.falarFixa(FALAS.voltei, false);
    } else if (s.modo === "ligando" && emJogo) {
      if (this.detalhe !== "voltando") this.mudar("jogo", "voltando");
    } else if (s.modo === "erro" && (emJogo || this.erroPonte)) {
      this.erroPonte = true;
      const d = s.detalhe || "a ponte do Vard está com erro";
      if (this.estado !== "erro" || this.detalhe !== d) this.mudar("erro", d);
    } else if (s.modo === "jogo" && !emJogo && !this.erroPonte) {
      // Jogo pedido por fora (bandeja, atalho): o HUD acompanha, fica cinza e solta o microfone.
      this.entrarNoJogo();
      this.microfoneFechado = (await this.d.fecharMicrofone?.()) !== false || this.microfoneFechado;
    }
  }

  async aoHealth(ok: boolean, falaOk: boolean): Promise<void> {
    if (this.estado === "jogo" || this.entrandoEmJogo || this.erroPonte) return; // com o jogo ou a ponte em erro quem manda é o status da ponte
    if (!ok) {
      if (this.estado !== "fora") {
        this.fecharCanal();
        this.mudar("fora", "sem conexão com o núcleo");
        if (!this.foraAvisado) { this.foraAvisado = true; await this.falarFixa(FALAS.openjarvisFora, false); }
      }
      return;
    }
    this.foraAvisado = false;
    if (!falaOk) {
      if (this.estado !== "erro") { this.fecharCanal(); this.mudar("erro", FALAS.falaDesligada); }
      return;
    }
    if (this.estado === "fora" || this.estado === "erro") {
      const eraFora = this.estado === "fora";
      this.mudar("repouso");
      if (eraFora) await this.falarFixa(FALAS.voltei, false);
    }
  }

  interromper(): void {
    this.pergunta?.abort(); // cancela pergunta/síntese em andamento: a resposta tardia não é falada
    this.pergunta = null;
    this.d.boca.parar();
    if (this.estado === "falando" || this.estado === "pensando") this.mudar("repouso");
    // Canal órfão (relógio limpo ao perguntar): rearma para o canal fechar sozinho depois de conversa_ms.
    if (this.canalAte > 0 && !this.relogioCanal) this.abrirCanal();
  }
}
