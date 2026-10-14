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
  fala: '<svg viewBox="0 0 24 24"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6"/></svg>',
  falaCortada: '<svg viewBox="0 0 24 24"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M4 4l16 16"/></svg>',
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
  /** Botão Não falar: a resposta passa a aparecer só em texto (o main alterna e grava). */
  aoNaoFalar?: () => void;
  aoInterromper?: () => void;
  /** Botão Tela (só existe com a ponte do Vard): pergunta o que está na tela. */
  aoTela?: () => void;
  /** Engrenagem: abre o painel de configurações. */
  aoConfig?: () => void;
  /** Bolinha de avisos não lidos: abre o painel já na aba Avisos. */
  aoAvisos?: () => void;
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
  private naoFalar = false;
  private linha: HTMLElement;
  private botoes: HTMLElement;
  private respostaEl: HTMLElement;
  private timerResposta = 0;
  private revelador: Revelador;
  private botaoMudo: HTMLButtonElement;
  private botaoNaoFalar: HTMLButtonElement;
  private botaoModo: HTMLButtonElement;
  private botaoTopoEl: HTMLButtonElement;
  private botaoTela: HTMLButtonElement;
  private contadorAvisos: HTMLButtonElement;
  private chipReuniao: HTMLElement;
  private indicadorAndamento: HTMLElement;

  constructor(private cfg: Config, private raiz: HTMLElement, private acoes: AcoesHud = {}) {
    const q = (id: string) => raiz.querySelector<HTMLElement>(`#${id}`)!;
    this.linha = q("dica"); this.botoes = q("botoes"); this.respostaEl = q("resposta");
    this.botaoMudo = this.botao(ICONES.micMudo, "Não ouvir", () => this.acoes.aoMudo?.());
    this.botaoMudo.classList.add("ativo");
    this.botaoNaoFalar = this.botao(ICONES.fala, "", () => this.acoes.aoNaoFalar?.());
    this.botaoTela = this.botao(ICONES.tela, "Olhar a tela", () => this.acoes.aoTela?.());
    this.botaoTela.hidden = true; // aparece quando a ponte responde
    this.botaoModo = this.botao(ICONES.compacto, "Compacto", () => { void this.alternarCompacto(); });
    this.botaoTopoEl = this.botao(ICONES.topo, "", () => { void this.alternarTopo(); });
    this.rotuloTopo();
    this.botoes.append(
      this.botaoMudo,
      this.botaoNaoFalar,
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
    // Bolinha de avisos não lidos no canto superior direito (fora da barra: fica visível também no compacto).
    this.contadorAvisos = document.createElement("button");
    this.contadorAvisos.id = "cont-avisos"; this.contadorAvisos.type = "button";
    this.contadorAvisos.hidden = true;
    this.contadorAvisos.addEventListener("click", () => this.acoes.aoAvisos?.());
    this.rotularContador(0);
    raiz.append(this.contadorAvisos);
    // Chip "reunião" (canto superior esquerdo): some no modo invisível junto com o resto do #app.
    this.chipReuniao = document.createElement("div");
    this.chipReuniao.id = "chip-reuniao"; this.chipReuniao.hidden = true; this.chipReuniao.textContent = "reunião";
    raiz.append(this.chipReuniao);
    // Bolinha de tarefas em andamento (canto superior esquerdo, abaixo do chip quando os dois aparecem).
    // Fica dentro do #app: no modo invisível some com o resto (só a dica da bandeja sinaliza).
    this.indicadorAndamento = document.createElement("div");
    this.indicadorAndamento.id = "andamento"; this.indicadorAndamento.hidden = true;
    raiz.append(this.indicadorAndamento);
    this.setNaoFalar(cfg.nao_falar);
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

  /** true = resposta só em texto: nenhuma síntese nem áudio (o texto fica até a próxima resposta). */
  setNaoFalar(v: boolean) {
    this.naoFalar = v;
    this.botaoNaoFalar.classList.toggle("ativo", v);
    this.botaoNaoFalar.innerHTML = v ? ICONES.falaCortada : ICONES.fala;
    const dica = `Não falar: ${v ? "ligado" : "desligado"}`;
    this.botaoNaoFalar.title = dica;
    this.botaoNaoFalar.setAttribute("aria-label", dica);
    // Desligando, o texto que ficou parado volta a sumir sozinho depois do prazo de sempre.
    if (!v && this.respostaEl.classList.contains("visivel")) this.agendarSumirResposta();
  }

  /** Conversa aberta contínua (T13): anel do holograma aceso enquanto o modo estiver ligado. */
  setConversaAberta(ligada: boolean) {
    this.raiz.classList.toggle("conversa-aberta", ligada);
  }

  /** Modo invisível: só opacidade (a janela nunca é escondida, para os timers do VAD seguirem). */
  setInvisivel(oculto: boolean) { this.raiz.classList.toggle("invisivel", oculto); }

  /** Compacto: só o holograma; a barra aparece com o mouse em cima. Também chamado quando o painel muda a config. */
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

  /** Reunião em andamento (a ponte avisa): chip discreto no HUD; no modo invisível ele some com o resto do #app. */
  setReuniao(ativa: boolean) { this.chipReuniao.hidden = !ativa; }

  /** Tarefas em andamento da ponte: bolinha girando + contador (separado dos avisos e do "pensando"); some com zero. */
  setEmAndamento(n: number, textoDaDica: string) {
    const v = Number.isFinite(n) ? Math.max(0, Math.round(n)) : 0;
    this.indicadorAndamento.hidden = v === 0;
    this.indicadorAndamento.textContent = v ? String(v) : "";
    this.indicadorAndamento.title = textoDaDica;
  }

  /** Contador de avisos não lidos: some com zero. */
  setNaoLidos(n: number) {
    const v = Number.isFinite(n) ? Math.max(0, Math.round(n)) : 0;
    this.contadorAvisos.hidden = v === 0;
    this.rotularContador(v);
  }

  private rotularContador(n: number) {
    const dica = n === 1 ? "1 aviso não lido; clique para ver" : `${n} avisos não lidos; clique para ver`;
    this.contadorAvisos.textContent = String(n);
    this.contadorAvisos.title = dica;
    this.contadorAvisos.setAttribute("aria-label", dica);
  }
  /** Indicador vermelho: a tela está prestes a ser capturada. */
  setIndicadorTela(ligado: boolean) { this.raiz.classList.toggle("capturando", ligado); }

  setEstado(e: Estado, detalhe = "") { this.estado = e; this.detalhe = detalhe; this.pintar(); }
  setOuvido(t: string) { this.ouvido = t; this.pintar(); }
  setResposta(t: string) {
    this.resposta = t; this.pintar();
    this.respostaEl.textContent = t;
    this.respostaEl.classList.add("visivel");
    clearTimeout(this.timerResposta);
    // Com "não falar" ligado o texto não some sozinho: fica até a próxima resposta.
    if (!this.naoFalar) this.agendarSumirResposta();
  }
  private agendarSumirResposta() {
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
