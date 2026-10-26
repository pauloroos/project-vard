import { gatilhos, type Config } from "../config/config";
import { INSTRUCAO_HABILIDADES, lerHabilidades, temHabilidadesLigadas } from "../config/habilidades";
import { fluxoParaWav } from "../audio/wav";
import { FALAS, saudacaoPara } from "./falas";
import { cortarEmFrases } from "./frases";
import { ehEncerramento } from "./encerramento";
import { aPartirDoGatilho, classificar, ehConfirmacao, ehInterrupcao, extrairComando } from "./rotas";
import type { Cerebro } from "../config/cerebro";
import { ErroPonte, type EventoPedidoSSE } from "../conectores/ponte/cliente";

export type Estado = "repouso" | "ouvindo" | "transcrevendo" | "pensando" | "falando" | "jogo" | "erro" | "fora";
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
  /** null quando cerebro=proprio e toggle usar_openjarvis está desligado (sem-openjarvis.md). */
  oj: {
    perguntar(mensagens: Mensagem[], sinal?: AbortSignal): Promise<string>;
    sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer>;
  } | null;
  boca: {
    falando: boolean;
    tocar(wav: ArrayBuffer): Promise<void>;
    /** Toca PCM conforme chega. Sem isto a frase da voz própria é lida inteira e tocada como WAV. */
    tocarFluxo?(corpo: ReadableStream<Uint8Array>, taxa: number, sinal?: AbortSignal): Promise<void>;
    parar(): void;
  };
  /** Serviço de voz próprio e opcional (docs/voz-propria.md). Sem ele, ou quando ele falha, a voz é a do OpenJarvis. */
  voz?: {
    falar(texto: string, velocidade: number, sinal?: AbortSignal): Promise<FalaEmFluxo>;
    falarWav?(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer>;
  };
  /** Voz de reserva configurada pelo usuário; usada automaticamente quando a principal falhar. */
  vozReserva?: {
    falarWav(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer>;
  };
  /** Fala fixa já sintetizada (com cache). */
  falas: (texto: string) => Promise<ArrayBuffer>;
  /** false = "não falar": nenhuma síntese nem áudio; a resposta fica só em texto. */
  falarPermitida?: () => boolean;
  config: Pick<Config, "nome" | "variantes" | "voz" | "velocidade" | "instrucao_formato" | "conversa_ms"> & Partial<Pick<Config, "usuario">>;
  /** Ponte opcional do Vard: olhos na tela e modo jogo. */
  ponte?: {
    ver(jpegB64: string, pergunta: string, sessaoId?: string): Promise<string>;
    modo(verbo: string): Promise<boolean>;
    /** Cérebro próprio: admite um pedido e devolve o estado inicial. */
    pedir?(texto: string, sessaoId: string): Promise<{ pedido_id: string; sessao_id: string; estado: string }>;
    /** Cancela um pedido do cérebro próprio. */
    cancelar?(pedidoId: string): Promise<{ estado: string } | null>;
    /** Consulta o estado de um pedido do cérebro próprio. */
    consultarPedido?(pedidoId: string): Promise<{ resposta?: string | null; estado: string; erro?: string | null; ultimo_seq?: number } | null>;
  };
  /** Cérebro ativo: 'openjarvis' (padrão) ou 'proprio' (usa rotas /pedidos). */
  cerebro?: Cerebro;
  /** ID da sessão de voz atual (usado pelo cérebro próprio para isolar pedidos). */
  sessaoVoz?: () => string;
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
  /** Desliga a máquina ConversaAberta e o HUD: chamado por frase de encerramento para cobrir ligações via atalho/voz. */
  aoDesligarConversaAberta?: () => void;
  /** Liga a máquina ConversaAberta sem duplicar: chamado por "fica me ouvindo". */
  aoLigarConversaAberta?: () => void;
  /** Chamado quando a resposta foi entregue (fim da fala): a conversa aberta volta a ouvir. */
  aoProcessamentoConcluido?: () => void;
  /** Reunião em andamento (a ponte avisa): o widget não fala nada enquanto durar. */
  reuniaoAtiva?: () => boolean;
}

const MAX_MENSAGENS = 20; // 10 trocas
const PRAZO_CONFIRMACAO_MS = 15000;
const PRAZO_SEM_PROGRESSO_MS = 90000;
const INTERVALO_CONSULTA_PEDIDO_MS = 3000;

export class Conversa {
  estado: Estado = "repouso";
  detalhe = "";
  historico: Mensagem[] = [];
  private foraAvisado = false;
  private aguardaConfirmacao = 0; // instante em que o modo jogo foi pedido; 0 = nada a confirmar
  private microfoneFechado = false;
  private erroPonte = false;
  private pergunta: AbortController | null = null;
  /** Fila de fala progressiva: garante que frases não se sobreponham e que this.pergunta viva até o fim. */
  private filaFala: Promise<void> = Promise.resolve();
  private canalAte = 0; // instante em que o modo conversa fecha; 0 = fechado
  private relogioCanal: ReturnType<typeof setTimeout> | null = null;
  private entrandoEmJogo = false; // aviso do modo jogo tocando: a sondagem da ponte não mexe no estado

  constructor(private d: DepsConversa) {}

  /** Modo conversa: depois de uma resposta, o nome fica dispensado até o silêncio de `conversa_ms`. */
  canalAberto(): boolean { return this.canalAte > 0 && Date.now() < this.canalAte; }

  private abrirCanal() {
    const ms = this.d.config.conversa_ms;
    if (!(ms > 0)) { this.fecharCanal(); return; } // conversa_ms mudou para 0 ao vivo: não deixa o canal aberto
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

  /** Reunião em andamento: o widget não fala nada (sem gravar nada na config, é só o estado do momento). */
  private mudoPorReuniao(): boolean { return this.d.reuniaoAtiva?.() === true; }

  /** "Não falar" ligado ou reunião em andamento: nenhuma síntese nem áudio (a resposta já está em texto). */
  private podeFalar(): boolean { return !this.mudoPorReuniao() && this.d.falarPermitida?.() !== false; }

  private mudar(e: Estado, detalhe = "") {
    this.estado = e;
    this.detalhe = detalhe;
    this.d.aoEstado?.(e, detalhe);
  }

  private async tocar(wav: Promise<ArrayBuffer>, mudarEstado = true) {
    try {
      if (!this.podeFalar()) { await wav.catch(() => {}); return; } // sem voz: o áudio não toca
      const w = await wav;
      if (mudarEstado) this.mudar("falando");
      await this.d.boca.tocar(w);
    } catch (erro) {
      console.warn("falha ao falar", erro);
    }
  }

  private async falarFixa(texto: string, mudarEstado = true) {
    if (!this.podeFalar()) return; // nem sintetiza
    await this.tocar(this.d.falas(texto), mudarEstado);
    if (mudarEstado && this.estado === "falando") this.mudar("repouso");
  }

  /** Fala a resposta frase a frase: a frase seguinte é pedida antes de a atual começar a tocar. */
  private async falarEmFrases(texto: string, sinal: AbortSignal): Promise<void> {
    if (!this.podeFalar()) return; // sem voz: a resposta já foi mostrada em texto
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
    // Reserva de fala: usa a voz de reserva configurada quando disponível;
    // cai para o OpenJarvis se a reserva também falhar ou não estiver configurada.
    const reserva = async (frase: string): Promise<ArrayBuffer> => {
      if (d.vozReserva?.falarWav) {
        try {
          return await d.vozReserva.falarWav(frase, d.config.velocidade);
        } catch (erro) {
          console.warn("reserva configurada falhou", erro);
        }
      }
      if (d.voz?.falarWav) {
        try {
          return await d.voz.falarWav(frase, d.config.velocidade);
        } catch (erro) {
          console.warn("reserva pela voz própria falhou", erro);
        }
      }
      // Com cerebro=proprio e toggle desligado, d.oj pode ser null: não há OpenJarvis como reserva.
      if (!d.oj) throw new Error("Sem voz disponível (OpenJarvis desligado e nenhuma voz própria/reserva configurada)");
      return d.oj.sintetizar(frase, d.config.voz, d.config.velocidade);
    };
    let caiuNoMeio = false; // a voz caiu no meio de uma frase: o resto da resposta nem tenta a voz
    const pararBoca = () => d.boca.parar();
    sinal.addEventListener("abort", pararBoca);
    let pendente: Promise<Som | null> | null = sintetizar(frases[0]);
    let primeiro = true;
    try {
      for (let i = 0; i < frases.length; i++) {
        if (!this.podeFalar()) return; // "não falar" ligou no meio: corta sem esperar o fim de uma fala que não existe
        let som: Som | null = null;
        try { som = await pendente; } catch (erro) { console.warn("falha ao sintetizar a frase", erro); this.mudar("erro", `sintese: ${(erro as Error).message || String(erro)}`); }
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

    // T13: frase de ativação da conversa aberta ("fica me ouvindo" e variantes).
    const comandoBruto = extrairComando(bruto, v) ?? bruto;
    if (/fica\s+me\s+ouvindo|continua\s+me\s+ouvindo|pode\s+ficar\s+ouvindo/.test(comandoBruto.toLowerCase())) {
      // Liga a máquina ConversaAberta sem duplicar (atalho/voz já podem ter ligado).
      this.d.aoLigarConversaAberta?.();
      await this.falarFixa(saudacaoPara(this.d.config.usuario));
      return;
    }

    // Frase de encerramento: com ou sem o nome na frente. Fala "Parei de ouvir." e muta até alguém reativar.
    // Desliga a ConversaAberta independente de como foi ligada (atalho, voz, aoCanal).
    if (ehEncerramento(comandoBruto)) {
      this.fecharCanal();
      this.d.aoDesligarConversaAberta?.();
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
    let falouProgressivamente = false; // FR-008: evita duplicar fala no fim se já falou durante streaming
    try {
      if (ver) {
        if (!this.d.capturar || !this.d.ponte) throw new Error("sem captura");
        let jpeg: string;
        try {
          await this.d.antesDaCaptura?.();
          if (ac.signal.aborted) return;
          jpeg = await this.d.capturar();
        } finally { this.d.depoisDaCaptura?.(); }
        const sessao = this.d.sessaoVoz?.(); // a visão entra na mesma sessão da voz (uma CLI só)
        resposta = (await (sessao ? this.d.ponte.ver(jpeg, comando, sessao) : this.d.ponte.ver(jpeg, comando))).trim();
      } else if (this.d.cerebro === "proprio" && this.d.ponte?.pedir && this.d.sessaoVoz) {
        // Cérebro próprio: admite pedido e espera texto via EventoPedido (SSE).
        const sessaoId = this.d.sessaoVoz();
        const estado = await this.d.ponte.pedir(comando, sessaoId);
        const pedidoId = estado.pedido_id;
        // O abort pode chegar enquanto /pedidos ainda admite ou reconcilia o pedido.
        let cancelado = false;
        const cancelarPedido = () => {
          if (cancelado) return;
          cancelado = true;
          void this.d.ponte?.cancelar?.(pedidoId).catch(() => {});
        };
        ac.signal.addEventListener("abort", cancelarPedido, { once: true });
        if (ac.signal.aborted || this.emJogo()) { cancelarPedido(); return; }
        let ultimoSeq = -1;
        let ultimoEstado = estado.estado ?? "na_fila";
        let textoAcumulado = "";
        // FR-008: buffer para fala incremental — só frases completas (com pontuação) são faladas durante streaming.
        let bufferFala = "";
        let posFalada = 0;
        const falarFrasesCompletas = () => {
          if (!this.podeFalar()) return;
          const frases = cortarEmFrases(bufferFala);
          if (frases.length <= 1) return; // sem frase completa ainda
          // Fala todas exceto a última (que pode ser parcial), serializando pela fila
          for (let i = 0; i < frases.length - 1; i++) {
            const frase = frases[i];
            if (!frase) continue;
            falouProgressivamente = true;
            this.filaFala = this.filaFala.then(() => this.falarEmFrases(frase, ac.signal)).catch(() => {});
            posFalada += frase.length;
          }
          // Mantém o resto no buffer
          bufferFala = frases[frases.length - 1] ?? "";
        };
        let snapInicial: { resposta?: string | null; estado: string; ultimo_seq?: number; erro?: string | null } | null = null;
        // Reconciliação inicial: consulta estado atual para pegar texto já produzido antes do SSE.
        try {
          const snap = await this.d.ponte.consultarPedido?.(pedidoId);
          if (snap) {
            snapInicial = snap;
            if (typeof snap.resposta === "string") textoAcumulado = snap.resposta;
            ultimoSeq = Number((snap as { ultimo_seq?: number }).ultimo_seq ?? 0);
            if (snap.estado) ultimoEstado = snap.estado;
          }
        } catch { /* segue com SSE */ }
        // O "fim" pode ter saído antes desta consulta: com o pedido encerrado, nenhum evento novo vai chegar.
        const jaTerminou = !!snapInicial && ["concluido", "falhou", "cancelado"].includes(snapInicial.estado);
        if (ac.signal.aborted || this.emJogo()) return;
        const promessaInicial = () => {
          if (!snapInicial || snapInicial.estado === "concluido") return Promise.resolve(textoAcumulado.trim());
          if (snapInicial.estado === "falhou") return Promise.reject(new ErroPonte(snapInicial.erro ?? "modelo_http"));
          return Promise.reject(new Error("cancelado"));
        };
        const esperarFim = jaTerminou ? promessaInicial() : new Promise<string>((resolve, reject) => {
          let resolvido = false;
          let timerPrazo: ReturnType<typeof setTimeout> | null = null;
          let timerIntervalo: ReturnType<typeof setInterval> | null = null;

          const estourarPrazo = () => {
            if (resolvido || ac.signal.aborted) return;
            resolvido = true;
            cleanup();
            cancelarPedido();
            this.d.depoisDaCaptura?.();
            this.mudar("erro", FALAS.erros.modelo_demorou);
            reject(new ErroPonte("modelo_demorou"));
          };

          const rearmarPrazo = () => {
            if (timerPrazo) clearTimeout(timerPrazo);
            timerPrazo = setTimeout(estourarPrazo, PRAZO_SEM_PROGRESSO_MS);
          };

          const consultar = async () => {
            if (resolvido || ac.signal.aborted) return;
            try {
              const snap = await this.d.ponte?.consultarPedido?.(pedidoId);
              if (!snap || resolvido || ac.signal.aborted) return;
              const snapSeq = Number((snap as { ultimo_seq?: number }).ultimo_seq ?? ultimoSeq);
              const snapEstado = snap.estado;
              let progresso = false;
              if (snapSeq > ultimoSeq) {
                ultimoSeq = snapSeq;
                progresso = true;
              }
              if (snapEstado !== ultimoEstado) {
                ultimoEstado = snapEstado;
                progresso = true;
              }
              if (typeof snap.resposta === "string" && snap.resposta.length > textoAcumulado.length) {
                textoAcumulado = snap.resposta;
                progresso = true;
              }
              if (progresso) rearmarPrazo();
              if (snapEstado === "concluido") {
                resolvido = true;
                cleanup();
                resolve(textoAcumulado.trim());
              } else if (snapEstado === "falhou") {
                resolvido = true;
                cleanup();
                reject(new ErroPonte(snap.erro ?? "modelo_http"));
              } else if (snapEstado === "cancelado") {
                resolvido = true;
                cleanup();
                reject(new Error("cancelado"));
              }
            } catch {
              /* segue aguardando próximo ciclo ou evento */
            }
          };

          const onEvento = (ev: Event) => {
            if (resolvido || ac.signal.aborted) return;
            const msg = (ev as MessageEvent).data;
            if (typeof msg !== "string") return;
            let obj: EventoPedidoSSE | null = null;
            try { obj = JSON.parse(msg) as EventoPedidoSSE; } catch { return; }
            if (!obj || obj.tipo !== "pedido" || obj.sessao_id !== sessaoId || obj.pedido_id !== pedidoId) return;
            // Qualquer evento válido do pedido indica progresso
            rearmarPrazo();
            if (obj.seq <= ultimoSeq) return; // ignora repetido
            ultimoSeq = obj.seq;
            if (obj.evento_tipo === "texto" && typeof obj.dados.texto === "string") {
              textoAcumulado += obj.dados.texto;
              // FR-008: fala incremental — só frases completas durante streaming
              bufferFala += obj.dados.texto;
              falarFrasesCompletas();
            } else if (obj.evento_tipo === "fim") {
              // FR-008: flush do buffer restante como frase final, serializado pela fila
              const resto = bufferFala.trim();
              if (resto && this.podeFalar()) {
                falouProgressivamente = true;
                this.filaFala = this.filaFala.then(() => this.falarEmFrases(resto, ac.signal)).catch(() => {});
              }
              bufferFala = "";
              resolvido = true;
              cleanup();
              resolve(textoAcumulado.trim());
            } else if (obj.evento_tipo === "erro") {
              resolvido = true;
              cleanup();
              const erroCod = typeof obj.dados?.erro === "string" ? obj.dados.erro : "modelo_http";
              reject(new ErroPonte(erroCod));
            }
          };

          const onReconectou = () => { void consultar(); };
          const onError = () => { cleanup(); reject(new Error("sse_erro")); };

          const cleanup = () => {
            if (timerPrazo) { clearTimeout(timerPrazo); timerPrazo = null; }
            if (timerIntervalo) { clearInterval(timerIntervalo); timerIntervalo = null; }
            window.removeEventListener("vard-evento-pedido", onEvento as unknown as EventListener);
            window.removeEventListener("vard-sse-reconectou", onReconectou);
            window.removeEventListener("error", onError);
          };

          window.addEventListener("vard-evento-pedido", onEvento as unknown as EventListener);
          window.addEventListener("vard-sse-reconectou", onReconectou);
          window.addEventListener("error", onError);
          ac.signal.addEventListener("abort", () => { cleanup(); reject(new Error("abortado")); });

          rearmarPrazo();
          timerIntervalo = setInterval(() => { void consultar(); }, INTERVALO_CONSULTA_PEDIDO_MS);
        });
        try {
          resposta = await esperarFim;
        } catch (erro) {
          // Cancela pedido se a fala foi cortada (abort) ou houve erro.
          cancelarPedido();
          this.d.depoisDaCaptura?.();
          if (ac.signal.aborted || this.emJogo()) return;
          throw erro;
        }
        if (!resposta) throw new Error("resposta vazia");
      } else {
        let instrucao = this.d.config.instrucao_formato;
        try {
          const cfg = await lerHabilidades();
          if (temHabilidadesLigadas(cfg)) instrucao += `\n${INSTRUCAO_HABILIDADES}`;
        } catch { /* Arquivo ilegível não impede conversar nem afirma receitas inexistentes. */ }
        if (ac.signal.aborted || this.emJogo()) return;
        // Com cerebro=proprio e toggle desligado, d.oj é null: não há OpenJarvis para perguntar.
        if (!this.d.oj) throw new Error("OpenJarvis desligado e nenhum provedor próprio configurado para responder.");
        resposta = (await this.d.oj.perguntar([
          { role: "system", content: instrucao },
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
      this.mudar("erro", `resposta: ${fala}`);
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
    // FR-008: se a fala já ocorreu progressivamente durante streaming, não repete
    if (!falouProgressivamente) {
      await this.falarEmFrases(resposta, ac.signal);
    } else {
      // Aguarda a fila de fala progressiva terminar antes de liberar this.pergunta,
      // para que interromper() ainda possa abortar e cancelar o pedido.
      try { await this.filaFala; } catch { /* erros de fala já foram tratados dentro de falarEmFrases */ }
    }
    if (this.pergunta === ac) this.pergunta = null;
    if (!ac.signal.aborted && !this.emJogo()) { this.abrirCanal(); this.d.aoProcessamentoConcluido?.(); this.mudar("repouso"); }
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
    // T13: modo jogo desliga a conversa aberta automaticamente (o main escuta este estado via aoEstado)
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
