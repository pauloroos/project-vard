import type { StatusPonte } from "../conectores/ponte/cliente";

export interface CategoriaSaber { titulo: string; frases: string[]; /** Etiqueta quando a ponte está fora; null = nada a marcar. */ etiqueta: string | null }

export interface DepsAbaSaber {
  /** Status da ponte (null = fora do ar). */
  statusPonte: () => Promise<StatusPonte | null>;
  /** Nome de chamada configurado, para as frases de exemplo. */
  nome: () => string;
}

/** Texto estático do que o Vard sabe fazer, por categoria. true = depende da ponte/instalação. */
const CATEGORIAS: [string, boolean, string[]][] = [
  ["Conversa", false, ["{n}, que horas são?", "{n}, me explica ..."]],
  ["Computador", true, ["{n}, abre o YouTube", "{n}, o que está na minha tela?", "{n}, organiza as janelas"]],
  ["Oficina", true, ["{n}, manda o Codex criar um teste no rdl-vard", "{n}, como está a tarefa 3?", "{n}, aprova a tarefa 3"]],
  ["Consultas", true, ["{n}, pede ao Claude pra ver as issues do Linear", "{n}, pergunta ao Codex o que tenho na agenda"]],
  ["Memória", true, ["{n}, lembra que ...", "{n}, o que eu pedi pra você lembrar sobre ..."]],
  ["Reunião", true, ["{n}, acompanha a reunião", "{n}, encerra a reunião", "{n}, gera a ata"]],
  ["Sistema", true, ["{n}, modo jogo", "{n}, volta do jogo", "{n}, bom dia, vamos começar o dia"]],
];

export const ETIQUETA_INSTALACAO = "precisa da instalação";

/** O nome de chamada com a primeira letra maiúscula nas frases de exemplo (aurora -> Aurora). */
export function nomeExemplo(nome: string): string {
  const t = nome.trim() || "vard";
  return t[0].toUpperCase() + t.slice(1);
}

/** As categorias com as frases já no nome dado; só as que precisam da ponte ganham a etiqueta quando ela está fora. */
export function categoriasSaber(nome: string, ponteNoAr: boolean): CategoriaSaber[] {
  const n = nomeExemplo(nome);
  return CATEGORIAS.map(([titulo, precisaPonte, frases]) => ({
    titulo,
    frases: frases.map((f) => f.replace("{n}", n)),
    etiqueta: precisaPonte && !ponteNoAr ? ETIQUETA_INSTALACAO : null,
  }));
}

/** Aba "O que eu sei fazer": texto fixo no código, sem chamar modelo; a ponte é só sondada ao ativar. */
export class AbaSaber {
  private caixa!: HTMLElement;
  private ativa = false;

  constructor(private raiz: HTMLElement, private deps: DepsAbaSaber) {}

  montar() {
    this.caixa = document.createElement("div");
    this.caixa.id = "saber-categorias";
    this.raiz.append(this.caixa);
    this.desenhar(false);
  }

  async ativar() {
    this.ativa = true;
    const st = await this.deps.statusPonte();
    if (!this.ativa) return; // a aba fechou enquanto a ponte respondia
    this.desenhar(st !== null);
  }

  desativar() { this.ativa = false; }

  private desenhar(ponteNoAr: boolean) {
    this.caixa.innerHTML = "";
    for (const c of categoriasSaber(this.deps.nome(), ponteNoAr)) {
      const bloco = document.createElement("div");
      bloco.className = "categoria";
      const cabecalho = document.createElement("div"); cabecalho.className = "cabecalho";
      const titulo = document.createElement("h3"); titulo.textContent = c.titulo;
      cabecalho.append(titulo);
      if (c.etiqueta) {
        const etiqueta = document.createElement("span");
        etiqueta.className = "etiqueta";
        etiqueta.textContent = c.etiqueta;
        cabecalho.append(etiqueta);
      }
      const lista = document.createElement("ul");
      for (const f of c.frases) {
        const item = document.createElement("li");
        item.textContent = f;
        lista.append(item);
      }
      bloco.append(cabecalho, lista);
      this.caixa.append(bloco);
    }
  }
}
