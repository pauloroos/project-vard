import type { Config } from "../config/config";
import { FALAS } from "./falas";
import { aPartirDoGatilho, classificar, ehInterrupcao, extrairComando } from "./rotas";

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
  ponte?: unknown; // Tarefa 5
  aoEstado?: (e: Estado, detalhe: string) => void;
  aoResposta?: (texto: string) => void;
}

const MAX_MENSAGENS = 20; // 10 trocas

export class Conversa {
  estado: Estado = "repouso";
  detalhe = "";
  historico: Mensagem[] = [];
  private foraAvisado = false;
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
    if (this.estado === "fora" || this.estado === "erro") return;
    const bruto = texto.trim();
    if (!bruto) return;
    const v = this.d.config.variantes;

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
    if (rota !== "ask") { await this.falarFixa(FALAS.semPonte); return; }

    this.mudar("pensando");
    this.pergunta?.abort();
    const ac = new AbortController();
    this.pergunta = ac;
    let resposta: string;
    try {
      resposta = (await this.d.oj.perguntar([
        { role: "system", content: this.d.config.instrucao_formato },
        ...this.historico,
        { role: "user", content: comando },
      ], ac.signal)).trim();
      if (ac.signal.aborted) return;
      if (!resposta) throw new Error("resposta vazia");
    } catch (erro) {
      if (ac.signal.aborted) return;
      console.warn("agente falhou", erro);
      await this.falarFixa(FALAS.erroModelo);
      if (this.estado !== "repouso") this.mudar("repouso");
      return;
    }
    this.historico.push({ role: "user", content: comando }, { role: "assistant", content: resposta });
    if (this.historico.length > MAX_MENSAGENS) this.historico = this.historico.slice(-MAX_MENSAGENS);
    this.d.aoResposta?.(resposta);
    await this.tocar(this.d.oj.sintetizar(resposta, this.d.config.voz, this.d.config.velocidade), true, ac.signal);
    if (this.pergunta === ac) this.pergunta = null;
    if (!ac.signal.aborted) this.mudar("repouso");
  }

  async aoHealth(ok: boolean, falaOk: boolean): Promise<void> {
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
