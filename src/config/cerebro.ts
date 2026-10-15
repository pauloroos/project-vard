// Escolha do cérebro: 'openjarvis' (padrão, nada muda) ou 'proprio' (usa rotas /pedidos do núcleo).
export type Cerebro = "openjarvis" | "proprio";
export const CEREBRO_PADRAO: Cerebro = "openjarvis";
export const CEREBROS: readonly Cerebro[] = ["openjarvis", "proprio"];

export function ehCerebro(v: unknown): v is Cerebro {
  return typeof v === "string" && (CEREBROS as readonly string[]).includes(v);
}