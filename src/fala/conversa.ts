import { gatilhos, type Config } from "../config/config";
import { INSTRUCAO_HABILIDADES, lerHabilidades, temHabilidadesLigadas } from "../config/habilidades";
import { fluxoParaWav } from "../audio/wav";
import { FALAS, saudacaoPara } from "./falas";
import { cortarEmFrases } from "./frases";
import { ehEncerramento } from "./encerramento";
import { aPartirDoGatilho, classificar, ehConfirmacao, ehInterrupcao, extrairComando } from "./rotas";
import type { Cerebro } from "../config/cerebro";
import type { EventoPedidoSSE } from "../conectores/ponte/cliente";

export type Estado = "repouso" | "ouvindo" | "transcrevendo" | "pensando" | "falando" | "jogo" | "erro" | "fora";
export interface Mensagem { role: "system" | "user" | "assistant"; content: string }

/** Prazo máximo esperando o `fim`/`erro` do pedido antes de sondar e desistir com erro visível. */
export const PRAZO_PEDIDO_MS = 60000;
/** Intervalo da sondagem do pedido enquanto o SSE não entrega o evento terminal. */
export const SONDAGEM_PEDIDO_MS = 2000;

/** Evento `erro` com `{erro: "cancelado"}` é interrupção normal: volta ao repouso sem mensagem. */
export function ehCancelamentoPedido(erro: unknown): boolean {
  return erro === "cancelado";
}

/** Detalhe em português para o estado `erro` a partir do código que o núcleo mandou. */
export function mensagemParaErroPedido(erro: unknown): string {
  const codigo = typeof erro === "string" && erro.trim() ? erro.trim() : "erro_desconhecido";
  if ((FALAS.erros as Record<string, string>)[codigo]) return (FALAS.erros as Record<string, string>)[codigo];
  if (codigo === "sse_erro" || codigo === "rede" || codigo === "timeout" || codigo === "resposta vazia") {
    return "Conexão perdida com o núcleo. Tente de novo.";
  }
  return `Não consegui pensar nisso agora (${codigo}).`;
}
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
    consultarPedido?(pedidoId: string): Promise<{ resposta?: string | null; estado: string } | null>;
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
  private timerTranscrevendo: ReturnType<typeof setTimeout> | null = null;

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
    // timeout de preso também cobre transcrevendo: se ficar preso, sai
    if (this.timerTranscrevendo) { clearTimeout(this.timerTranscrevendo); this.timerTranscrevendo = null; }
    if (e === "transcrevendo") {
      this.timerTranscrevendo = setTimeout(() => {
        if (this.estado === "transcrevendo") {
          this.mudar("erro", "tempo de transcrição esgotado");
          // volta ao repouso após breve exibição, permitindo nova tentativa
          setTimeout(() => { if (this.estado === "erro") this.mudar("repouso"); }, 3000);
        }
      }, 30000);
    }
    this.estado = e;
    this.detalhe = detalhe;
    this.d.aoEstado?.(e, detalhe);
  }

  /** Notifica início de captura/transcrição: vai para transcrevendo. Retorna false se em erro (bloqueia). */
  notificarInicioTranscricao(): boolean {
    if (this.estado === "erro" || this.estado === "fora" || this.emJogo()) return false;
    this.mudar("transcrevendo");
    return true;
  }

  /** Transcrição pronta: sai de transcrevendo para pensando (usado quando a captura foi feita fora da Conversa). */
  notificarTranscricaoPronta(): void {
    if (this.estado === "transcrevendo") this.mudar("pensando");
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
    // `erro` não bloqueia a próxima tentativa: a pergunta nova sai do erro para `pensando`.
    if (this.estado === "fora" || this.emJogo()) return;
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
        let textoAcumulado = "";
        // Reconciliação inicial: consulta estado atual para pegar texto já produzido antes do SSE.
        try {
          const snap = await this.d.ponte.consultarPedido?.(pedidoId);
          if (snap && typeof snap.resposta === "string") {
            textoAcumulado = snap.resposta;
            ultimoSeq = Number((snap as { ultimo_seq?: number }).ultimo_seq ?? 0);
          }
          // O "fim" pode ter saído antes desta consulta: com o pedido encerrado, nenhum evento novo vai chegar.
          if (snap && snap.estado === "cancelado") {
            this.abrirCanal();
            if (this.estado !== "repouso") this.mudar("repouso");
            return;
          }
          if (snap && snap.estado === "falhou") {
            const erroSnap = (snap as { erro?: unknown }).erro;
            throw new Error(typeof erroSnap === "string" && erroSnap ? erroSnap : "erro_desconhecido");
          }
          if (snap && snap.estado === "concluido") {
            resposta = textoAcumulado.trim();
            if (!resposta) throw new Error("resposta vazia");
            if (ac.signal.aborted || this.emJogo()) return;
            // Segue para falar abaixo sem esperar o SSE.
          } else {
            // Escuta eventos SSE da sessão até fim/erro/cancelamento, com sondagem e prazo para nunca prender.
            if (ac.signal.aborted || this.emJogo()) return;
            const esperarFim = new Promise<string>((resolve, reject) => {
              let terminado = false;
              const onEvento = (ev: Event) => {
                if (ac.signal.aborted || terminado) return;
                const msg = (ev as MessageEvent).data;
                if (typeof msg !== "string") return;
                let obj: EventoPedidoSSE | null = null;
                try { obj = JSON.parse(msg) as EventoPedidoSSE; } catch { return; }
                if (!obj || obj.tipo !== "pedido" || obj.sessao_id !== sessaoId || obj.pedido_id !== pedidoId) return;
                if (obj.seq <= ultimoSeq) return; // ignora repetido
                ultimoSeq = obj.seq;
                if (obj.evento_tipo === "texto" && typeof obj.dados.texto === "string") {
                  const antes = textoAcumulado.length;
                  textoAcumulado += obj.dados.texto;
                  // Primeira parte da resposta: a UI sai de `pensando` para `falando`.
                  if (antes === 0 && textoAcumulado.length > 0 && this.estado === "pensando") this.mudar("falando");
                } else if (obj.evento_tipo === "fim") {
                  const erroFim = (obj.dados as Record<string, unknown>)?.erro;
                  if (typeof erroFim === "string" && erroFim && !ehCancelamentoPedido(erroFim)) {
                    cleanup();
                    reject(new Error(erroFim));
                    return;
                  }
                  if (ehCancelamentoPedido(erroFim)) {
                    cleanup();
                    reject(new Error("cancelado"));
                    return;
                  }
                  const respostaFim = (obj.dados as Record<string, unknown>)?.resposta;
                  if (typeof respostaFim === "string" && respostaFim.trim()) textoAcumulado = respostaFim;
                  cleanup();
                  resolve(textoAcumulado.trim());
                } else if (obj.evento_tipo === "erro") {
                  const codigo = (obj.dados as Record<string, unknown>)?.erro;
                  cleanup();
                  reject(new Error(typeof codigo === "string" && codigo ? codigo : "erro_desconhecido"));
                }
              };
              const onError = () => { if (!terminado) { cleanup(); reject(new Error("sse_erro")); } };
              const sondar = async () => {
                if (terminado || ac.signal.aborted) return;
                try {
                  const snap = await this.d.ponte?.consultarPedido?.(pedidoId);
                  if (!snap || terminado || ac.signal.aborted) return;
                  if (snap.estado === "cancelado") { cleanup(); reject(new Error("cancelado")); return; }
                  if (snap.estado === "falhou") {
                    cleanup();
                    const erroSonda = (snap as { erro?: unknown }).erro;
                    reject(new Error(typeof erroSonda === "string" && erroSonda ? erroSonda : "erro_desconhecido"));
                    return;
                  }
                  if (snap.estado === "concluido") {
                    if (typeof snap.resposta === "string" && snap.resposta.trim()) textoAcumulado = snap.resposta;
                    cleanup();
                    resolve(textoAcumulado.trim());
                  }
                } catch { /* rede instável: tenta de novo no próximo ciclo ou no prazo */ }
              };
              const cleanup = () => {
                if (terminado) return;
                terminado = true;
                clearTimeout(prazo);
                clearInterval(sonda);
                window.removeEventListener("vard-evento-pedido", onEvento as unknown as EventListener);
                window.removeEventListener("error", onError);
              };
              window.addEventListener("vard-evento-pedido", onEvento as unknown as EventListener);
              window.addEventListener("error", onError);
              const sonda = setInterval(() => { void sondar(); }, SONDAGEM_PEDIDO_MS);
              const prazo = setTimeout(() => { void sondar().then(() => { if (!terminado) { cleanup(); reject(new Error("timeout")); } }); }, PRAZO_PEDIDO_MS);
              ac.signal.addEventListener("abort", () => { cleanup(); reject(new Error("abortado")); }, { once: true });
            });
            try {
              resposta = await esperarFim;
            } catch (erro) {
              // Cancela pedido se a fala foi cortada (abort) ou houve erro.
              cancelarPedido();
              if (ac.signal.aborted || this.emJogo()) return;
              throw erro;
            }
            if (!resposta) throw new Error("resposta vazia");
          }
        } catch (erro) {
          // Interrupção normal (cancelado/abortado): volta ao repouso sem mensagem de erro.
          const msg = erro instanceof Error ? erro.message : String(erro ?? "");
          if (msg === "cancelado" || msg === "abortado" || ac.signal.aborted) {
            this.abrirCanal();
            if (this.estado !== "repouso") this.mudar("repouso");
            if (this.pergunta === ac) this.pergunta = null;
            return;
          }
          throw erro;
        }
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
      const msgErro = erro instanceof Error ? erro.message : String((erro as { codigo?: unknown } | null)?.codigo ?? erro ?? "");
      // Interrupção normal do cérebro próprio: volta ao repouso sem mensagem de erro.
      if (msgErro === "cancelado" || msgErro === "abortado" || ehCancelamentoPedido(msgErro)) {
        this.abrirCanal();
        if (this.estado !== "repouso") this.mudar("repouso");
        if (this.pergunta === ac) this.pergunta = null;
        return;
      }
      // Cérebro próprio: `fim`/`erro` com erro real, queda do SSE ou falha da ponte viram estado `erro` visível.
      if (!ver && this.d.cerebro === "proprio") {
        const codigo = (erro as { codigo?: string } | null)?.codigo ?? msgErro;
        const detalhe = mensagemParaErroPedido(codigo);
        console.warn("pedido falhou", erro);
        try { await this.falarFixa(FALAS.erroModelo, false); } catch { /* sem voz, o erro fica só no HUD */ }
        this.abrirCanal();
        this.mudar("erro", detalhe);
        if (this.pergunta === ac) this.pergunta = null;
        return;
      }
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
    if (this.estado === "falando" || this.estado === "pensando" || this.estado === "transcrevendo" || this.estado === "erro") this.mudar("repouso");
    // Canal órfão (relógio limpo ao perguntar): rearma para o canal fechar sozinho depois de conversa_ms.
    if (this.canalAte > 0 && !this.relogioCanal) this.abrirCanal();
  }
}
