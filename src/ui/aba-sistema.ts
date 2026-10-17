import type { StatusPonte } from "../conectores/ponte/cliente";

/** O que cada botão pode fazer num modo do ciclo nativo. null = supervisor fora: nada. */
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
  /** Tauri invoke: ciclo_pedir(verbo) -> {ok, id, erro?} */
  cicloPedir?: (verbo: string) => Promise<{ ok: boolean; id: string; erro?: string }>;
  /** Tauri listen: evento ciclo-estado com FotoCiclo */
  onCicloEstado?: (cb: (foto: { modo: string; detalhe?: string }) => void) => () => void;
}

const TEXTO = "O ciclo nativo controla os serviços do Vard: ligar sobe núcleo e conectores; Modo jogo desliga tudo e libera a GPU; Desligar encerra os runtimes e mantém a bandeja. Sem supervisor ativo, os botões ficam inativos.";
const VERBOS: [string, string, "ligar" | "jogo" | "desligar"][] = [["iniciar", "Ligar", "ligar"], ["jogo", "Modo jogo", "jogo"], ["parar", "Desligar", "desligar"]];

/** Aba Sistema: estado do ciclo nativo via evento ciclo-estado e botões via ciclo_pedir invoke. Fallback para ponte quando ciclo nativo indisponível. */
export class AbaSistema {
  private relogio = 0;
  private confirmacao = new Confirmacao(5000, () => this.rotular());
  private botoes = new Map<string, HTMLButtonElement>();
  private estado!: HTMLElement;
  private msg!: HTMLElement;
  private acoes = acoesDoModo(null);
  private ativa = false;
  private unsubscribeCiclo: (() => void) | null = null;

  constructor(private raiz: HTMLElement, private deps: DepsAbaSistema) {}

  montar() {
    const p = document.createElement("p"); p.className = "nota"; p.textContent = TEXTO;
    this.estado = document.createElement("div"); this.estado.id = "sis-estado"; this.estado.textContent = "Consultando ciclo...";
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

  ativar() {
    this.ativa = true;
    // Escuta evento ciclo-estado do Tauri
    if (this.deps.onCicloEstado) {
      this.unsubscribeCiclo = this.deps.onCicloEstado((foto) => {
        this.acoes = acoesDoModo(foto.modo);
        this.estado.textContent = `Modo: ${foto.modo}${foto.detalhe ? ` (${foto.detalhe})` : ""}`;
        this.rotular();
      });
    }
    // Fallback: sonda ponte se ciclo nativo não disponível
    if (!this.deps.cicloPedir) {
      void this.sondar();
      clearInterval(this.relogio);
      this.relogio = window.setInterval(() => { void this.sondar(); }, 5000);
    }
  }

  desativar() {
    this.ativa = false;
    clearInterval(this.relogio);
    this.relogio = 0;
    this.confirmacao.cancelar();
    if (this.unsubscribeCiclo) { this.unsubscribeCiclo(); this.unsubscribeCiclo = null; }
    this.rotular();
  }

  private async sondar() {
    const st = await this.deps.statusPonte();
    if (!this.ativa) return;
    this.acoes = acoesDoModo(st ? st.modo : null);
    this.estado.textContent = st
      ? `Modo: ${st.modo || "desconhecido"}${st.detalhe ? ` (${st.detalhe})` : ""} | OpenJarvis: ${st.ok ? "no ar" : "fora"} | Tarefas abertas: ${st.tarefas_abertas ?? 0}`
      : "Supervisor desabilitado ou ciclo indisponível.";
    this.rotular();
  }

  private rotular() {
    for (const [verbo, rotulo, chave] of VERBOS) {
      const b = this.botoes.get(verbo)!;
      b.disabled = !this.acoes[chave];
      b.textContent = this.confirmacao.armado === verbo ? "Confirmar" : rotulo;
    }
  }

  private async clicar(verbo: string) {
    if (verbo === "voltar") { this.confirmacao.cancelar(); this.rotular(); }
    if (verbo !== "voltar" && !this.confirmacao.pedir(verbo)) { this.rotular(); return; }
    this.msg.textContent = "Enviando...";
    // Usa ciclo_pedir via invoke se disponível; senão fallback para ponte
    if (this.deps.cicloPedir) {
      try {
        const res = await this.deps.cicloPedir(verbo);
        this.msg.textContent = res.ok
          ? `Pedido aceito (${res.id.slice(0, 8)}…); aguarde transição.`
          : `Recusado: ${res.erro || "motivo desconhecido"}`;
      } catch (e) {
        this.msg.textContent = `Erro: ${e instanceof Error ? e.message : String(e)}`;
      }
    } else {
      const ok = await this.deps.modo(verbo);
      this.msg.textContent = ok ? "Pedido enviado; o estado muda em alguns segundos." : "A ponte não aceitou o pedido.";
    }
    this.rotular();
  }
}

/** Dependências da seção Telegram na aba Sistema. */
export interface DepsAbaSistemaTelegram {
  verTelegram: () => Promise<{ ligado: boolean; chat_permitido: string }>;
  configurarTelegram: (ligado: boolean, chat: string) => Promise<{ ok: boolean }>;
  descobrirChat: () => Promise<{ ok: boolean; chat_id?: string; detalhe?: string }>;
  enviarTeste: () => Promise<{ ok: boolean; detalhe?: string }>;
  gravarToken: (token: string) => Promise<{ ok: boolean }>;
}

/** Seção Telegram dentro da aba Sistema: toggle, token (cofre), chat, descobrir e testar. */
export class AbaSistemaTelegram {
  private toggle!: HTMLInputElement;
  private tokenInput!: HTMLInputElement;
  private chatInput!: HTMLInputElement;
  private msg!: HTMLElement;

  constructor(private raiz: HTMLElement, private deps: DepsAbaSistemaTelegram) {}

  async montar() {
    const secao = document.createElement("div");
    secao.className = "secao-telegram";

    const titulo = document.createElement("h3");
    titulo.textContent = "Telegram";
    secao.append(titulo);

    // Toggle ligado/desligado
    const lblToggle = document.createElement("label");
    lblToggle.className = "campo";
    this.toggle = document.createElement("input");
    this.toggle.type = "checkbox";
    this.toggle.id = "tg-ligado";
    lblToggle.append(this.toggle, document.createTextNode(" Ligado"));
    secao.append(lblToggle);

    // Token (senha, nunca exibido)
    const lblToken = document.createElement("label");
    lblToken.className = "campo";
    lblToken.textContent = "Token do bot: ";
    this.tokenInput = document.createElement("input");
    this.tokenInput.type = "password";
    this.tokenInput.id = "tg-token";
    this.tokenInput.placeholder = "Cole o token aqui (salvo no cofre)";
    lblToken.append(this.tokenInput);
    secao.append(lblToken);

    // Chat permitido
    const lblChat = document.createElement("label");
    lblChat.className = "campo";
    lblChat.textContent = "Chat permitido: ";
    this.chatInput = document.createElement("input");
    this.chatInput.type = "text";
    this.chatInput.id = "tg-chat";
    this.chatInput.placeholder = "ID do chat (ex: 123456789)";
    lblChat.append(this.chatInput);
    secao.append(lblChat);

    // Botões
    const acoes = document.createElement("div");
    acoes.className = "acoes";

    const btnDescobrir = document.createElement("button");
    btnDescobrir.type = "button";
    btnDescobrir.id = "tg-descobrir";
    btnDescobrir.textContent = "Descobrir meu chat";
    btnDescobrir.addEventListener("click", () => { void this.descobrir(); });
    acoes.append(btnDescobrir);

    const btnTestar = document.createElement("button");
    btnTestar.type = "button";
    btnTestar.id = "tg-testar";
    btnTestar.textContent = "Enviar teste";
    btnTestar.addEventListener("click", () => { void this.testar(); });
    acoes.append(btnTestar);

    secao.append(acoes);

    this.msg = document.createElement("div");
    this.msg.id = "tg-msg";
    secao.append(this.msg);

    this.raiz.append(secao);

    // Carrega estado atual
    await this.carregar();

    // Listeners
    this.toggle.addEventListener("change", () => { void this.salvarEstado(); });
    this.tokenInput.addEventListener("change", () => { void this.salvarToken(); });
  }

  private async carregar() {
    try {
      const estado = await this.deps.verTelegram();
      this.toggle.checked = estado.ligado;
      this.chatInput.value = estado.chat_permitido || "";
    } catch {
      this.msg.textContent = "Erro ao carregar configuração do Telegram.";
    }
  }

  private async salvarEstado() {
    this.msg.textContent = "Salvando...";
    try {
      await this.deps.configurarTelegram(this.toggle.checked, this.chatInput.value.trim());
      this.msg.textContent = "Configuração salva.";
    } catch {
      this.msg.textContent = "Erro ao salvar.";
    }
  }

  private async salvarToken() {
    const token = this.tokenInput.value.trim();
    if (!token) return;
    this.msg.textContent = "Salvando token...";
    try {
      await this.deps.gravarToken(token);
      this.msg.textContent = "Token salvo.";
      this.tokenInput.value = "";
    } catch {
      this.msg.textContent = "Erro ao salvar token.";
    }
  }

  private async descobrir() {
    this.msg.textContent = "Buscando chat...";
    try {
      const res = await this.deps.descobrirChat();
      if (res.ok && res.chat_id) {
        this.chatInput.value = res.chat_id;
        this.msg.textContent = `Chat encontrado: ${res.chat_id}`;
        await this.salvarEstado();
      } else {
        this.msg.textContent = res.detalhe || "Nenhum /start pendente.";
      }
    } catch {
      this.msg.textContent = "Erro ao buscar chat.";
    }
  }

  private async testar() {
    this.msg.textContent = "Enviando teste...";
    try {
      const res = await this.deps.enviarTeste();
      this.msg.textContent = res.ok ? "Mensagem de teste enviada." : (res.detalhe || "Falha ao enviar.");
    } catch {
      this.msg.textContent = "Erro ao enviar teste.";
    }
  }
}