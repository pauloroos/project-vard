/** O que a sondagem do /status devolve para a reunião (`null` = ponte fora do ar). */
export type ReuniaoStatus = "ativa" | "inativa" | "ausente" | null;

/** Decide se há reunião ativa a partir do /status da ponte (sondagem a cada 10 s) e dos eventos ao vivo.
 * "iniciou" liga na hora; "encerrou" desliga na hora; o resto (diarizando, ata_pronta, erro) não muda nada.
 * Puro: sem rede, sem DOM, sem relógio. */
export class EstadoReuniao {
  ativa = false;
  aoMudar: ((ativa: boolean) => void) | null = null;

  constructor(aoMudar?: (ativa: boolean) => void) { this.aoMudar = aoMudar ?? null; }

  /** Resultado da sondagem do /status. Ponte fora ou "ausente" conta como sem reunião. */
  atualizarStatus(reuniao: ReuniaoStatus): void { this.mudar(reuniao === "ativa"); }

  /** Evento ao vivo do SSE (tipo "reuniao"). Corpo inválido ou estado de fora da ordem não muda nada. */
  aplicarEvento(dados: unknown): void {
    const estado = typeof dados === "object" && dados !== null ? (dados as { estado?: unknown }).estado : null;
    if (estado === "iniciou") this.mudar(true);
    else if (estado === "encerrou") this.mudar(false);
  }

  /** Só avisa quem mudou de verdade: um "encerrou" sem reunião (ou o segundo "iniciou") fica em silêncio. */
  private mudar(nova: boolean) {
    if (this.ativa === nova) return;
    this.ativa = nova;
    this.aoMudar?.(nova);
  }
}
