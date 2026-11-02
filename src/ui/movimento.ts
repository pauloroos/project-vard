import type { Estado } from "./nucleo";

export interface OpcoesCadencia {
  estado: Estado;
  movimentoReduzido: boolean;
  oculto?: boolean;
}

/**
 * Retorna os quadros por segundo recomendados para o estado do núcleo:
 * - Em repouso: cadência menor (~30 fps).
 * - Em repouso com movimento reduzido: ainda menor (10 fps).
 * - Estados ativos (ouvindo, transcrevendo, pensando, falando): fluidos (60 fps, ou 30 fps com movimento reduzido).
 * - Em erro ou fora: 30 fps (ou 10 fps com movimento reduzido).
 * - Em jogo ou oculto: 0 fps (parado).
 */
export function cadenciaFps(opcoes: OpcoesCadencia): number {
  if (opcoes.oculto) return 0;
  if (opcoes.estado === "jogo") return 0;

  const ativo =
    opcoes.estado === "ouvindo" ||
    opcoes.estado === "transcrevendo" ||
    opcoes.estado === "pensando" ||
    opcoes.estado === "falando";

  if (opcoes.movimentoReduzido) {
    return ativo ? 30 : 10;
  }

  return ativo ? 60 : 30;
}

/**
 * Retorna o intervalo mínimo em milissegundos entre quadros para dada cadência (fps).
 */
export function intervaloMinimoMs(fps: number): number {
  if (fps <= 0 || !Number.isFinite(fps)) return Infinity;
  return 1000 / fps;
}

/**
 * Avalia se já decorreu tempo suficiente desde o último quadro desenhado.
 * Usa tolerância de 1.5ms para compensar jitter de agendamento do requestAnimationFrame.
 */
export function deveDesenharQuadro(
  agora: number,
  ultimoDesenho: number,
  intervaloMinimo: number,
  toleranciaMs = 1.5
): boolean {
  if (intervaloMinimo <= 0 || !Number.isFinite(intervaloMinimo)) return false;
  if (ultimoDesenho === 0) return true;
  return agora - ultimoDesenho >= intervaloMinimo - toleranciaMs;
}

/**
 * Consulta a preferência do sistema operacional por movimento reduzido.
 */
export function prefereMovimentoReduzido(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
