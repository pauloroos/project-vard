import type { StatusPonte } from "../conectores/ponte/cliente";

/** O que cada botão pode fazer num modo da ponte. null = ponte fora: nada. */
export function acoesDoModo(modo: string | null): { ligar: boolean; jogo: boolean; desligar: boolean } {
  if (modo === null) return { ligar: false, jogo: false, desligar: false };
  if (modo === "ligado") return { ligar: false, jogo: true, desligar: true };
  return { ligar: true, jogo: false, desligar: true };
}

/** Dois cliques no mesmo verbo dentro do prazo confirmam; o prazo estourado ou outro verbo recomeçam. */
export class Confirmacao {
  private verbo: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private janelaMs: number, private aoExpirar: () => void) {}
  /** Verbo que espera o segundo clique agora (null = nenhum). */
  get armado(): string | null { return this.verbo; }
  pedir(verbo: string): boolean {
    if (this.verbo === verbo) { this.cancelar(); return true; }
    this.cancelar();
    this.verbo = verbo;
    this.timer = setTimeout(() => { this.verbo = null; this.timer = null; this.aoExpirar(); }, this.janelaMs);
    return false;
  }
  cancelar() { if (this.timer !== null) clearTimeout(this.timer); this.timer = null; this.verbo = null; }
}

export interface DepsAbaSistema {
  statusPonte: () => Promise<StatusPonte | null>;
  modo: (verbo: string) => Promise<boolean>;
}

const TEXTO = "A ponte liga o Vard à sua instalação: olhos na tela (o que está no monitor), modo jogo (desliga tudo e tira os modelos da GPU) e os avisos da oficina. Sem ela o widget funciona igual, só sem esses recursos.";
const VERBOS: [string, string, "ligar" | "jogo" | "desligar"][] = [["voltar", "Ligar", "ligar"], ["jogo", "Modo jogo", "jogo"], ["parar", "Desligar", "desligar"]];

/** Aba Sistema: estado da ponte a cada 5 s enquanto aberta e os três verbos do ciclo. O campo ponte_url fica no painel, fora daqui. */
export class AbaSistema {
  private relogio = 0;
  private confirmacao = new Confirmacao(5000, () => this.rotular());
  private botoes = new Map<string, HTMLButtonElement>();
  private estado!: HTMLElement;
  private msg!: HTMLElement;
  private acoes = acoesDoModo(null);
  private ativa = false;

  constructor(private raiz: HTMLElement, private deps: DepsAbaSistema) {}

  montar() {
    const p = document.createElement("p"); p.className = "nota"; p.textContent = TEXTO;
    this.estado = document.createElement("div"); this.estado.id = "sis-estado"; this.estado.textContent = "Consultando a ponte...";
    const caixa = document.createElement("div"); caixa.className = "acoes";
    for (const [verbo, rotulo] of VERBOS) {
      const b = document.createElement("button"); b.type = "button"; b.textContent = rotulo; b.dataset.verbo = verbo;
      b.addEventListener("click", () => { void this.clicar(verbo); });
      this.botoes.set(verbo, b); caixa.append(b);
    }
    this.msg = document.createElement("div"); this.msg.id = "sis-msg";
    this.raiz.append(p, this.estado, caixa, this.msg);
    this.rotular();
  }

  ativar() { this.ativa = true; void this.sondar(); clearInterval(this.relogio); this.relogio = window.setInterval(() => { void this.sondar(); }, 5000); }
  desativar() { this.ativa = false; clearInterval(this.relogio); this.relogio = 0; this.confirmacao.cancelar(); this.rotular(); }

  private async sondar() {
    const st = await this.deps.statusPonte();
    if (!this.ativa) return; // a aba fechou enquanto a ponte respondia
    this.acoes = acoesDoModo(st ? st.modo : null);
    this.estado.textContent = st
      ? `Modo: ${st.modo || "desconhecido"}${st.detalhe ? ` (${st.detalhe})` : ""} | OpenJarvis: ${st.ok ? "no ar" : "fora"} | Tarefas abertas: ${st.tarefas_abertas ?? 0}`
      : "Ponte fora do ar ou desligada.";
    this.rotular();
  }

  private rotular() {
    for (const [verbo, rotulo, chave] of VERBOS) {
      const b = this.botoes.get(verbo)!;
      b.disabled = !this.acoes[chave];
      b.textContent = this.confirmacao.armado === verbo ? "Confirmar" : rotulo; // o ciclo de 5 s não apaga o pedido de confirmação
    }
  }

  private async clicar(verbo: string) {
    if (verbo === "voltar") this.confirmacao.cancelar();
    if (verbo !== "voltar" && !this.confirmacao.pedir(verbo)) { this.rotular(); return; }
    this.msg.textContent = "Enviando...";
    const ok = await this.deps.modo(verbo);
    this.msg.textContent = ok ? "Pedido enviado; o estado muda em alguns segundos." : "A ponte não aceitou o pedido.";
    this.rotular();
  }
}
