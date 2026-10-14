import { normalizarAviso, type Aviso } from "../conectores/ponte/cliente";

/** O que a central usa da ponte (injetável nos testes). */
export interface PonteAvisos {
  avisos(): Promise<{ avisos: Aviso[]; nao_lidos: number } | null>;
  marcarLidos(ids?: number[]): Promise<{ ok: boolean; nao_lidos: number } | null>;
  resultadoTarefa(n: number): Promise<{ n: number; estado: string; resumo: string; texto: string } | null>;
  eventos(cb: (tipo: string, dados: unknown) => void): () => void;
}

export const LIMITE_AVISOS = 100;

/** Rótulo curto do aviso para a tela. */
export function rotuloDoAviso(a: Aviso): string {
  if (a.tipo === "tarefa") return a.n === undefined ? "Tarefa" : `Tarefa ${a.n}`;
  if (a.tipo === "reuniao") return "Reunião";
  return a.tipo;
}

/** Central de avisos: lista da ponte mais os eventos ao vivo, sem DOM. */
export class CentralAvisos {
  avisos: Aviso[] = [];
  naoLidos = 0;
  aoMudar: (() => void) | null = null;

  constructor(private ponte: Pick<PonteAvisos, "avisos" | "marcarLidos">) {}

  /** Recarrega pela ponte. false = ponte fora do ar (a lista fica como estava). */
  async carregar(): Promise<boolean> {
    const r = await this.ponte.avisos();
    if (!r) return false;
    this.avisos = r.avisos;
    this.naoLidos = r.nao_lidos;
    this.aoMudar?.();
    return true;
  }

  /**
   * Evento ao vivo (oficina/reuniao): entra no fim da lista se tiver id novo; ignora duplicado; guarda no máximo LIMITE_AVISOS.
   * Retorna true se o aviso foi realmente adicionado (id novo e estado final que interessa); false se ignorado/duplicado/em-andamento.
   */
  aplicarEvento(tipo: string, dados: unknown): boolean {
    const mapeado = tipo === "oficina" ? "tarefa" : tipo;
    const bruto = typeof dados === "object" && dados !== null ? { tipo: mapeado, ...(dados as Record<string, unknown>) } : { tipo: mapeado };
    const a = normalizarAviso(bruto);
    if (!a) return false; // sem id não dá para deduplicar
    if (this.avisos.some((x) => x.id === a.id)) return false;
    // Só considera "aviso novo de verdade" estados finais de tarefa ou eventos de reunião relevantes.
    // Estados intermediários (em_andamento, iniciada) não devem disparar chamada nem fala.
    const estadosFinaisTarefa = ["terminou", "falhou", "esperando"];
    if (a.tipo === "tarefa" && !estadosFinaisTarefa.includes(a.estado ?? "")) return false;
    this.avisos.push(a);
    while (this.avisos.length > LIMITE_AVISOS) this.avisos.shift();
    if (!a.lido) this.naoLidos++;
    this.aoMudar?.();
    return true;
  }

  /** Marca lidos na ponte e espelha aqui. false = ponte fora (nada muda). */
  async marcarLidos(ids?: number[]): Promise<boolean> {
    const r = await this.ponte.marcarLidos(ids);
    if (!r || !r.ok) return false;
    this.naoLidos = r.nao_lidos;
    if (ids) { for (const a of this.avisos) if (ids.includes(a.id)) a.lido = true; }
    else for (const a of this.avisos) a.lido = true;
    this.aoMudar?.();
    return true;
  }
}
