import type { Config } from "../config/config";
import { FALAS } from "./falas";
import { aPartirDoGatilho, classificar, ehConfirmacao, ehInterrupcao, extrairComando } from "./rotas";

export type Estado = "repouso" | "ouvindo" | "pensando" | "falando" | "jogo" | "erro" | "fora";
export interface Mensagem { role: "system" | "user" | "assistant"; content: string }

export interface DepsConversa {
  oj: {
    perguntar(mensagens: Mensagem[], sinal?: AbortSignal): Promise<string>;
    sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer>;
  };
  boca: { falando: boolean; tocar(wav: ArrayBuffer): Promise<void>; parar(): void };
  /** Fala fixa já sintetizada (com cache). */
  falas: (texto: string) => Promise<ArrayBuffer>;
  config: Pick<Config, "variantes" | "voz" | "velocidade" | "instrucao_formato">;
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
  abrirMicrofone?: () => void | Promise<void>;
  fecharMicrofone?: () => void | Promise<void>;
  aoEstado?: (e: Estado, detalhe: string) => void;
  aoResposta?: (texto: string) => void;
}

const MAX_MENSAGENS = 20; // 10 trocas

export class Conversa {
  estado: Estado = "repouso";
  detalhe = "";
  historico: Mensagem[] = [];
  private foraAvisado = false;
  private aguardaConfirmacao = false;
  private microfoneFechado = false;
  private erroPonte = false;
  private pergunta: AbortController | null = null;

  constructor(private d: DepsConversa) {}

  private mudar(e: Estado, detalhe = "") {
    this.estado = e;
    this.detalhe = detalhe;
    this.d.aoEstado?.(e, detalhe);
  }

  private async tocar(wav: Promise<ArrayBuffer>, mudarEstado = true, sinal?: AbortSignal) {
    try {
      const w = await wav;
      if (sinal?.aborted) return; // interrompido enquanto sintetizava: resposta tardia não é falada
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

  async aoTextoTranscrito(texto: string, pushToTalk: boolean): Promise<void> {
    if (this.d.boca.falando) return;
    if (this.estado === "fora" || this.estado === "erro" || this.estado === "jogo") return;
    const bruto = texto.trim();
    if (!bruto) return;
    const v = this.d.config.variantes;

    // Confirmação do modo jogo: vale só a próxima frase; "sim" ou "confirmo" sozinhos (com ou sem o nome).
    if (this.aguardaConfirmacao) {
      this.aguardaConfirmacao = false;
      if (ehConfirmacao(extrairComando(bruto, v) ?? bruto)) { await this.ativarJogo(); return; }
    }

    let comando: string;
    if (pushToTalk) {
      comando = extrairComando(bruto, v) ?? bruto;
    } else {
      const apartir = aPartirDoGatilho(bruto, v);
      if (apartir === null) return;
      comando = extrairComando(apartir, v) ?? apartir;
    }
    if (comando === "") { await this.falarFixa(FALAS.saudacao); return; }
    if (ehInterrupcao(comando)) return;

    const rota = classificar(comando);
    if (rota !== "ask") {
      const d = this.d;
      if (!d.ponte || d.ponteNoAr?.() === false) { await this.falarFixa(FALAS.semPonte); return; }
      if (rota === "modo") {
        this.aguardaConfirmacao = true;
        await this.falarFixa(FALAS.modoJogoConfirmar);
        return;
      }
    }

    this.mudar("pensando");
    this.pergunta?.abort();
    const ac = new AbortController();
    this.pergunta = ac;
    const ver = rota === "see";
    let resposta: string;
    try {
      if (ver) {
        if (!this.d.capturar || !this.d.ponte) throw new Error("sem captura");
        await this.d.antesDaCaptura?.();
        if (ac.signal.aborted) return;
        const jpeg = await this.d.capturar();
        resposta = (await this.d.ponte.ver(jpeg, comando)).trim();
      } else {
        resposta = (await this.d.oj.perguntar([
          { role: "system", content: this.d.config.instrucao_formato },
          ...this.historico,
          { role: "user", content: comando },
        ], ac.signal)).trim();
      }
      if (ac.signal.aborted) return;
      if (!resposta) throw new Error("resposta vazia");
    } catch (erro) {
      if (ac.signal.aborted) return;
      console.warn(ver ? "olhos falharam" : "agente falhou", erro);
      const codigo = (erro as { codigo?: string } | null)?.codigo;
      const fala = (codigo && (FALAS.erros as Record<string, string>)[codigo]) || FALAS.erroModelo;
      await this.falarFixa(fala);
      if (this.estado !== "repouso") this.mudar("repouso");
      return;
    }
    if (!ver) {
      this.historico.push({ role: "user", content: comando }, { role: "assistant", content: resposta });
      if (this.historico.length > MAX_MENSAGENS) this.historico = this.historico.slice(-MAX_MENSAGENS);
    }
    this.d.aoResposta?.(resposta);
    await this.tocar(this.d.oj.sintetizar(resposta, this.d.config.voz, this.d.config.velocidade), true, ac.signal);
    if (this.pergunta === ac) this.pergunta = null;
    if (!ac.signal.aborted) this.mudar("repouso");
  }

  private async ativarJogo(): Promise<void> {
    const ponte = this.d.ponte;
    if (!ponte) { await this.falarFixa(FALAS.semPonte); return; }
    // Sintetiza o aviso antes: o modo jogo derruba o OpenJarvis (e a voz) logo em seguida.
    const aviso = this.d.falas(FALAS.modoJogoAtivado);
    aviso.catch(() => {});
    if (!(await ponte.modo("jogo"))) { await this.falarFixa(FALAS.erros.modo_falhou); return; }
    await this.tocar(aviso, false);
    this.mudar("jogo");
    this.microfoneFechado = true;
    await this.d.fecharMicrofone?.();
  }

  /** Resultado da sondagem da ponte (a cada 10 s). null = ponte ausente. Cuida de entrar e sair do modo jogo. */
  async aoStatusPonte(s: { modo: string; detalhe?: string } | null): Promise<void> {
    if (!s) return;
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
      this.mudar("jogo");
      this.microfoneFechado = true;
      await this.d.fecharMicrofone?.();
    }
  }

  async aoHealth(ok: boolean, falaOk: boolean): Promise<void> {
    if (this.estado === "jogo" || this.erroPonte) return; // com o jogo ou a ponte em erro quem manda é o status da ponte
    if (!ok) {
      if (this.estado !== "fora") {
        this.mudar("fora", "sem conexão com o núcleo");
        if (!this.foraAvisado) { this.foraAvisado = true; await this.falarFixa(FALAS.openjarvisFora, false); }
      }
      return;
    }
    this.foraAvisado = false;
    if (!falaOk) {
      if (this.estado !== "erro") this.mudar("erro", FALAS.falaDesligada);
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
  }
}
