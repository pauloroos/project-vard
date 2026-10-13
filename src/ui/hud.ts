import { invoke } from "@tauri-apps/api/core";
import type { Config } from "../config/config";
import { atualizarConfig } from "../config/config";
import type { Estado } from "../fala/conversa";
import { Revelador } from "./revelador";

export const ROTULO_ESTADO: Record<Estado, string> = {
  repouso: "pronto", ouvindo: "ouvindo", pensando: "pensando", falando: "falando",
  jogo: "MODO JOGO", erro: "atenção", fora: "núcleo offline",
};

const ICONES = {
  mic: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  micMudo: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M4 4l16 16"/></svg>',
  parar: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
  texto: '<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  topo: '<svg viewBox="0 0 24 24"><path d="M12 21v-9M8 8l4-4 4 4M5 4h14"/></svg>',
  tela: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
  config: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/></svg>',
  compacto: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></svg>',
};

export interface AcoesHud {
  /** Botão do microfone: quem decide se abre ou muda o mudo é o main, que devolve o estado por setMudo. */
  aoMudo?: () => void;
  aoInterromper?: () => void;
  /** Botão Tela (só existe com a ponte do Vard): pergunta o que está na tela. */
  aoTela?: () => void;
  /** Engrenagem: abre o painel de configurações. */
  aoConfig?: () => void;
  /** O widget gravou topo ou compacto pelos próprios botões (o main avisa o painel). */
  aoConfigMudou?: (c: Config) => void;
}

/** Linha de estado, última resposta e barra de comandos (cinco ícones). Só DOM, sem regra de negócio. */
export class Hud {
  private estado: Estado = "repouso";
  private detalhe = "";
  private ouvido = "";
  private resposta = "";
  private latenciaMs: number | null = null;
  private taxaHz = 48000;
  private mudo = true;
  private linha: HTMLElement;
  private botoes: HTMLElement;
  private respostaEl: HTMLElement;
  private timerResposta = 0;
  private revelador: Revelador;
  private botaoMudo: HTMLButtonElement;
  private botaoModo: HTMLButtonElement;
  private botaoTopoEl: HTMLButtonElement;
  private botaoTela: HTMLButtonElement;

  constructor(private cfg: Config, private raiz: HTMLElement, private acoes: AcoesHud = {}) {
    const q = (id: string) => raiz.querySelector<HTMLElement>(`#${id}`)!;
    this.linha = q("dica"); this.botoes = q("botoes"); this.respostaEl = q("resposta");
    this.botaoMudo = this.botao(ICONES.micMudo, "Microfone: ligar ou desligar", () => this.acoes.aoMudo?.());
    this.botaoMudo.classList.add("ativo");
    this.botaoTela = this.botao(ICONES.tela, "Olhar a tela", () => this.acoes.aoTela?.());
    this.botaoTela.hidden = true; // aparece quando a ponte responde
    this.botaoModo = this.botao(ICONES.compacto, "Compacto", () => { void this.alternarCompacto(); });
    this.botaoTopoEl = this.botao(ICONES.topo, "", () => { void this.alternarTopo(); });
    this.rotuloTopo();
    this.botoes.append(
      this.botaoMudo,
      this.botao(ICONES.parar, "Interromper a fala", () => this.acoes.aoInterromper?.()),
      this.botaoTela,
      this.botao(ICONES.texto, "Abrir a conversa em texto", () => { void invoke("abrir_url", { url: cfg.gui_url }); }),
      this.botaoTopoEl,
      this.botao(ICONES.config, "Configurações", () => this.acoes.aoConfig?.()),
      this.botaoModo,
    );
    this.revelador = new Revelador(2000, (v) => this.raiz.classList.toggle("revelado", v));
    raiz.addEventListener("mouseenter", () => this.revelador.entrou());
    raiz.addEventListener("mouseleave", () => this.revelador.saiu());
    this.setCompacto(cfg.compacto);
    this.pintar();
  }

  /** Botões não levam data-tauri-drag-region: continuam clicáveis. */
  private botao(svg: string, dica: string, aoClicar: () => void): HTMLButtonElement {
    const b = document.createElement("button");
    b.innerHTML = svg; b.title = dica; b.setAttribute("aria-label", dica);
    b.addEventListener("click", aoClicar);
    return b;
  }

  /** Reaplica o rótulo do topo depois que o painel de configurações mudou o valor. */
  atualizarTopo() { this.rotuloTopo(); }

  private rotuloTopo() {
    const sim = this.cfg.sempre_no_topo;
    this.botaoTopoEl.title = sim ? "Sempre no topo: ligado" : "Sempre no topo: desligado";
    this.botaoTopoEl.style.opacity = sim ? "1" : "0.5";
  }

  private async alternarTopo() {
    const novo = !this.cfg.sempre_no_topo;
    try {
      await invoke("definir_sempre_no_topo", { ligado: novo });
      this.cfg.sempre_no_topo = novo;
      await atualizarConfig({ sempre_no_topo: novo });
      this.acoes.aoConfigMudou?.(this.cfg);
      this.rotuloTopo();
    } catch (erro) { console.warn("não consegui alternar o topo", erro); }
  }

  /** true = microfone fechado (ou ainda não aberto). */
  setMudo(m: boolean) {
    this.mudo = m;
    this.botaoMudo.classList.toggle("ativo", m);
    this.botaoMudo.innerHTML = m ? ICONES.micMudo : ICONES.mic;
    this.pintar();
  }

  /** Compacto: só o holograma; a barra aparece com o mouse em cima. Também chamado quando o painel muda a config. */
  /** Modo invisível: só opacidade (a janela nunca é escondida, para os timers do VAD seguirem). */
  setInvisivel(oculto: boolean) { this.raiz.classList.toggle("invisivel", oculto); }

  setCompacto(c: boolean) {
    this.raiz.classList.toggle("compacto", c);
    this.botaoModo.title = c ? "Expandir" : "Compacto";
    this.botaoModo.setAttribute("aria-label", this.botaoModo.title);
  }

  private async alternarCompacto() {
    this.cfg.compacto = !this.cfg.compacto;
    this.setCompacto(this.cfg.compacto);
    try { await atualizarConfig({ compacto: this.cfg.compacto }); } catch (erro) { console.warn("não consegui gravar o compacto", erro); }
    this.acoes.aoConfigMudou?.(this.cfg);
  }

  /** Mostra ou esconde o botão Tela conforme a ponte do Vard responde. */
  setPonte(noAr: boolean) { this.botaoTela.hidden = !noAr; }
  /** Indicador vermelho: a tela está prestes a ser capturada. */
  setIndicadorTela(ligado: boolean) { this.raiz.classList.toggle("capturando", ligado); }

  setEstado(e: Estado, detalhe = "") { this.estado = e; this.detalhe = detalhe; this.pintar(); }
  setOuvido(t: string) { this.ouvido = t; this.pintar(); }
  setResposta(t: string) {
    this.resposta = t; this.pintar();
    this.respostaEl.textContent = t;
    this.respostaEl.classList.add("visivel");
    clearTimeout(this.timerResposta);
    this.timerResposta = window.setTimeout(() => this.respostaEl.classList.remove("visivel"), 9000);
  }
  dica(t: string) { this.linha.textContent = t; }
  /** Aviso que precisa ser visto mesmo no compacto (onde a linha de estado some): aparece por 10 s. */
  avisar(t: string) {
    this.dica(t);
    this.linha.classList.add("avisando");
    clearTimeout(this.relogioAviso);
    this.relogioAviso = setTimeout(() => this.linha.classList.remove("avisando"), 10000);
  }
  private relogioAviso: ReturnType<typeof setTimeout> | undefined;
  setLatencia(ms: number) { this.latenciaMs = Math.round(ms); this.pintar(); }
  setTaxa(hz: number) { this.taxaHz = hz; this.pintar(); }

  private pintar() {
    const base = this.detalhe || ROTULO_ESTADO[this.estado];
    const semOuvido = this.mudo && this.estado === "repouso" && !this.detalhe;
    const texto = semOuvido ? "toque duas vezes no núcleo para ouvir" : base;
    this.linha.textContent = this.ouvido && !semOuvido && this.estado !== "fora" && this.estado !== "erro" ? `${texto} | ${this.ouvido}` : texto;
    const khz = (this.taxaHz / 1000).toFixed(1).replace(".", ",");
    const lat = this.latenciaMs === null ? "-- ms" : `${this.latenciaMs} ms`;
    this.linha.title = [`${khz} kHz // ${lat}`, this.ouvido && `Ouvi: ${this.ouvido}`, this.resposta && `Resposta: ${this.resposta}`].filter(Boolean).join(" | ");
  }
}
