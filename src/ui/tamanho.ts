import type { Config } from "../config/config";

/** O widget é desenhado para 320 px de lado (360 de altura) e escalado a partir daí. */
export const LADO_BASE = 320;
export const ALTURA_BASE = 360;
export const LADO_MIN = 160;
export const LADO_MAX = 800;
const PRESETS: Record<string, number> = { pequeno: 240, medio: 320, grande: 480 };

/** Lado do widget em px lógicos: preset, ou tamanho_px limitado a 160..800 (inválido = 320). */
export function ladoDoTamanho(c: Pick<Config, "tamanho" | "tamanho_px">): number {
  if (c.tamanho === "personalizado") {
    const n = Math.round(Number(c.tamanho_px));
    return Number.isFinite(n) ? Math.min(LADO_MAX, Math.max(LADO_MIN, n)) : LADO_BASE;
  }
  return PRESETS[c.tamanho] ?? LADO_BASE;
}

export interface Medidas { lado: number; largura: number; altura: number; escala: number }

/** Janela e escala para um lado: a altura guarda a proporção 320x360 de hoje. */
export function medidasDoWidget(lado: number): Medidas {
  return { lado, largura: lado, altura: Math.round((lado * ALTURA_BASE) / LADO_BASE), escala: lado / LADO_BASE };
}
