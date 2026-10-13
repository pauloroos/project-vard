import type { Config } from "../config/config";

/** Estados de tarefa que valem ser falados (os mesmos que a ponte aceita em ESTADOS_AVISO). */
const ESTADOS_TAREFA = ["terminou", "falhou", "esperando"];

/** Um aviso da ponte como o widget recebe: o SSE entrega "oficina" (tarefa) ou "reuniao". */
export interface EventoAviso { tipo: string; estado?: string }

/**
 * true se o resumo deste aviso deve ser falado agora: `falar_avisos` ligado, "não falar" desligado,
 * boca livre (nunca interrompe uma fala em curso) e estado que interessa.
 * A reunião em andamento engole os avisos de tarefa; o próprio evento da reunião (ata pronta) fala.
 */
export function deveFalarAviso(
  cfg: Pick<Config, "falar_avisos" | "nao_falar">,
  ev: EventoAviso,
  ocupado: boolean,
  reuniaoAtiva: boolean,
): boolean {
  if (!cfg.falar_avisos || cfg.nao_falar || ocupado) return false;
  if (ev.tipo === "reuniao") return ev.estado === "ata_pronta";
  if (reuniaoAtiva) return false;
  return ev.tipo === "tarefa" && ESTADOS_TAREFA.includes(ev.estado ?? "");
}

/**
 * Um aviso por vez: sintetizar e falar demoram, e dois avisos em cima só atrapalham
 * (o resumo do primeiro já está na tela). Enquanto um corre, os demais são descartados.
 */
export class AvisoPorVez {
  private ocupado = false;

  /** Roda `tarefa` se não houver outra em curso; nesse caso devolve null sem rodar nada. */
  async executar<T>(tarefa: () => Promise<T>): Promise<T | null> {
    if (this.ocupado) return null;
    this.ocupado = true;
    try { return await tarefa(); } finally { this.ocupado = false; }
  }
}
