import type { Estado } from "../fala/conversa";

/** O que a sala mostra: espelho do widget, que é quem ouve e fala. */
export interface Espelho { estado: Estado; detalhe: string; ouvido: string; resposta: string }
export type EventoEspelho =
  | { tipo: "estado"; estado: Estado; detalhe: string }
  | { tipo: "ouvido"; texto: string }
  | { tipo: "resposta"; texto: string }
  | { tipo: "retrato"; espelho: Espelho };

export const ESPELHO_INICIAL: Espelho = { estado: "repouso", detalhe: "", ouvido: "", resposta: "" };
/** Letra grande na TV: respostas longas são cortadas. */
export const MAX_TEXTO = 400;
const ESTADOS: readonly string[] = ["repouso", "ouvindo", "transcrevendo", "pensando", "falando", "jogo", "erro", "fora"];

function limitar(t: string): string {
  const s = t.trim();
  return s.length > MAX_TEXTO ? `${s.slice(0, MAX_TEXTO - 3).trimEnd()}...` : s;
}
const texto = (v: unknown): string | null => (typeof v === "string" ? limitar(v) : null);

/** Aplica um evento vindo do widget. Evento malformado (payload estranho, outra versão) devolve o mesmo objeto. */
export function reduzir(atual: Espelho, ev: unknown): Espelho {
  if (typeof ev !== "object" || ev === null) return atual;
  const e = ev as Record<string, unknown>;
  switch (e.tipo) {
    case "estado":
      if (typeof e.estado !== "string" || !ESTADOS.includes(e.estado)) return atual;
      return { ...atual, estado: e.estado as Estado, detalhe: texto(e.detalhe) ?? "" };
    case "ouvido": {
      const t = texto(e.texto);
      return t === null ? atual : { ...atual, ouvido: t, resposta: "" }; // pergunta nova: a resposta antiga sai
    }
    case "resposta": {
      const t = texto(e.texto);
      return t === null ? atual : { ...atual, resposta: t };
    }
    case "retrato": {
      if (typeof e.espelho !== "object" || e.espelho === null) return atual;
      const r = e.espelho as Record<string, unknown>;
      const comEstado = reduzir(ESPELHO_INICIAL, { tipo: "estado", estado: r.estado, detalhe: r.detalhe });
      return reduzir(reduzir(comEstado, { tipo: "ouvido", texto: r.ouvido }), { tipo: "resposta", texto: r.resposta });
    }
    default:
      return atual;
  }
}

/** "09:05", sem depender da localidade. */
export function formatarHora(d: Date): string {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** A sala existe quando a consulta por rótulo (WebviewWindow.getByLabel) devolve uma janela, e não null. Serve para o widget retomar o espelho ao recarregar. */
export function salaExiste(janela: unknown): boolean {
  return janela !== null && janela !== undefined;
}
