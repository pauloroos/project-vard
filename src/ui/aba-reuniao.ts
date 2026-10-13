import type { ReuniaoDaLista, ResultadoReuniao, StatusReuniao } from "../conectores/ponte/cliente";

/** O que a aba usa da ponte da reunião (injetável nos testes). */
export interface PonteReuniao {
  reuniaoStatus(): Promise<StatusReuniao | null>;
  iniciarReuniao(): Promise<ResultadoReuniao | null>;
  encerrarReuniao(): Promise<ResultadoReuniao | null>;
  listaReuniao(n?: number): Promise<ReuniaoDaLista[] | null>;
  gerarAta(tipo: "ata" | "relatorio", qual?: string): Promise<ResultadoReuniao | null>;
}

/** O que cada botão da aba pode fazer. null = ponte fora: nada. */
export function acoesDaReuniao(ativa: boolean | null): { iniciar: boolean; encerrar: boolean; ata: boolean; relatorio: boolean } {
  if (ativa === null) return { iniciar: false, encerrar: false, ata: false, relatorio: false };
  return { iniciar: !ativa, encerrar: ativa, ata: true, relatorio: true };
}

/** Duração em segundos vira "1 h 05 min" (ou "25 min" / "40 s" quando cabe). */
export function formatarDuracao(segundos: number): string {
  const s = Number.isFinite(segundos) ? Math.max(0, Math.round(segundos)) : 0;
  const h = Math.floor(s / 3600);
  const min = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} h ${String(min).padStart(2, "0")} min`;
  if (min > 0) return `${min} min`;
  return `${s} s`;
}

/** Data/hora da ponte vira "13/10/2026 15:00"; texto que não é data fica como está. */
export function formatarDataHora(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

type Chave = "iniciar" | "encerrar" | "ata" | "relatorio";

const TEXTO = "A reunião pertence ao serviço da ponte: quem ouve \"encerra a reunião\" é ele, não o widget. Aqui dá para ver se há uma em andamento, começar ou encerrar pela ponte e gerar a ata ou o relatório da última. Enquanto a reunião corre, o widget fica mudo e não escuta o gatilho.";
const BOTOES: [Chave, string][] = [["iniciar", "Iniciar"], ["encerrar", "Encerrar"], ["ata", "Gerar ata"], ["relatorio", "Gerar relatório"]];

/** Aba Reunião: estado da ponte da reunião a cada 5 s enquanto aberta, os dois verbos e a última reunião. */
export class AbaReuniao {
  private relogio = 0;
  private botoes = new Map<string, HTMLButtonElement>();
  private estado!: HTMLElement;
  private msg!: HTMLElement;
  private ultima!: HTMLElement;
  private acoes = acoesDaReuniao(null);
  private ativa = false;

  constructor(private raiz: HTMLElement, private deps: PonteReuniao) {}

  montar() {
    const p = document.createElement("p"); p.className = "nota"; p.textContent = TEXTO;
    this.estado = document.createElement("div"); this.estado.id = "reu-estado"; this.estado.textContent = "Consultando a ponte...";
    const caixa = document.createElement("div"); caixa.className = "acoes";
    for (const [chave, rotulo] of BOTOES) {
      const b = document.createElement("button"); b.type = "button"; b.textContent = rotulo;
      b.addEventListener("click", () => { void this.clicar(chave); });
      this.botoes.set(chave, b); caixa.append(b);
    }
    this.msg = document.createElement("div"); this.msg.id = "reu-msg";
    this.ultima = document.createElement("div"); this.ultima.id = "reu-ultima";
    this.raiz.append(p, this.estado, caixa, this.msg, this.ultima);
    this.rotular();
  }

  ativar() { this.ativa = true; void this.puxar(true); clearInterval(this.relogio); this.relogio = window.setInterval(() => { void this.puxar(true); }, 5000); }
  desativar() { this.ativa = false; clearInterval(this.relogio); this.relogio = 0; }

  /** Recarrega pela ponte e pinta (também chamado depois de cada ação e nos testes). */
  async carregar() { await this.puxar(false); }

  /** `comGuarda`: a carga do relógio não pode repintar uma aba que já fechou no meio da espera da ponte. */
  private async puxar(comGuarda: boolean) {
    const [st, lista] = await Promise.all([this.deps.reuniaoStatus(), this.deps.listaReuniao(1)]);
    if (comGuarda && !this.ativa) return;
    this.acoes = acoesDaReuniao(st === null ? null : st.ativa);
    this.estado.textContent = st
      ? (st.ativa ? `Reunião em andamento${st.pasta ? ` (${st.pasta})` : ""}.` : "Nenhuma reunião em andamento.")
      : "Ponte fora do ar ou desligada.";
    this.desenharUltima(lista?.[0] ?? null);
    this.rotular();
  }

  private rotular() {
    for (const [chave] of BOTOES) this.botoes.get(chave)!.disabled = !this.acoes[chave];
  }

  private async clicar(chave: Chave) {
    this.msg.textContent = "Enviando...";
    const r = chave === "iniciar" ? await this.deps.iniciarReuniao()
      : chave === "encerrar" ? await this.deps.encerrarReuniao()
      : await this.deps.gerarAta(chave === "ata" ? "ata" : "relatorio", "ultima");
    this.msg.textContent = r ? r.frase : "A ponte não respondeu.";
    void this.carregar();
  }

  private desenharUltima(r: ReuniaoDaLista | null) {
    this.ultima.innerHTML = "";
    const titulo = document.createElement("h3"); titulo.textContent = "Última reunião";
    this.ultima.append(titulo);
    if (!r) { const vazio = document.createElement("div"); vazio.className = "nota"; vazio.textContent = "Nenhuma reunião registrada."; this.ultima.append(vazio); return; }
    const linhas: [string, string][] = [
      ["Data/hora", r.inicio ? formatarDataHora(r.inicio) : "—"],
      ["Duração", formatarDuracao(r.duracao_s)],
      ["Ata", r.ata ? "pronta" : "não gerada"],
      ["Relatório", r.relatorio ? "pronto" : "não gerado"],
    ];
    for (const [rotulo, valor] of linhas) {
      const linha = document.createElement("div"); linha.className = "linha"; linha.textContent = `${rotulo}: ${valor}`;
      this.ultima.append(linha);
    }
  }
}
