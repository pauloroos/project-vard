import type { TarefaAndamento } from "../conectores/ponte/cliente";

/** O que o EmAndamento usa da ponte (injetável nos testes). */
export interface PonteAndamento {
  andamento(): Promise<{ total: number; tarefas: TarefaAndamento[] } | null>;
}

/** Quantas linhas da dica cabem antes de virar "+N". */
export const LIMITE_DICA = 5;

/** "40 s"; 60 s ou mais vira minutos ("2 min"). */
export function textoDosSegundos(segundos: number): string {
  const s = Math.max(0, Math.round(segundos));
  if (s < 60) return `${s} s`;
  return `${Math.round(s / 60)} min`;
}

/** Uma linha da dica: "Claude: issues do Linear, 40 s". */
export function linhaDaTarefa(t: TarefaAndamento): string {
  const quem = t.quem || t.ferramenta;
  return `${quem}: ${t.resumo}, ${textoDosSegundos(t.segundos)}`;
}

/** Dica completa: uma linha por tarefa, no máximo LIMITE_DICA e depois "+N". */
export function textoDaDica(tarefas: TarefaAndamento[]): string {
  const linhas = tarefas.slice(0, LIMITE_DICA).map(linhaDaTarefa);
  if (tarefas.length > LIMITE_DICA) linhas.push(`+${tarefas.length - LIMITE_DICA}`);
  return linhas.join("\n");
}

/** Tarefas em andamento da ponte: quem manda no indicador do HUD e na dica da bandeja. Sem DOM. */
export class EmAndamento {
  tarefas: TarefaAndamento[] = [];
  aoMudar: (() => void) | null = null;

  constructor(private ponte: Pick<PonteAndamento, "andamento">) {}

  get total(): number { return this.tarefas.length; }

  /** Recarrega pela ponte. false = ponte fora do ar (a lista fica como estava). */
  async carregar(): Promise<boolean> {
    const r = await this.ponte.andamento();
    if (!r) return false;
    this.tarefas = r.tarefas;
    this.aoMudar?.();
    return true;
  }

  /** Evento ao vivo: qualquer estado da oficina recarrega a lista (terminou/falhou some sozinho da ponte). */
  async aplicarEvento(tipo: string): Promise<boolean> {
    if (tipo !== "oficina") return false;
    return this.carregar();
  }
}
