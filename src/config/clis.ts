/**
 * Detecção das CLIs de agente instaladas (T17a, 0.8).
 *
 * Vem da ponte: `GET /cli/detectar` (PATH + `--version`, sem caminho na resposta).
 * Ponte vazia, fora ou sem rota devolve lista vazia: os tipos cli-* não aparecem.
 */
export interface CliDetectada {
  tipo: string;
  instalada: boolean;
  versao: string;
  modelos: string[];
}

function validar(raw: unknown): CliDetectada | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.tipo !== "string" || !o.tipo) return null;
  if (typeof o.instalada !== "boolean") return null;
  return {
    tipo: o.tipo,
    instalada: o.instalada,
    versao: typeof o.versao === "string" ? o.versao : "",
    modelos: Array.isArray(o.modelos) ? o.modelos.filter((m): m is string => typeof m === "string") : [],
  };
}

/** CLIs detectadas pela ponte; nunca lança erro (ponte fora é lista vazia). */
export async function detectarClis(base: string): Promise<CliDetectada[]> {
  const raiz = base.trim().replace(/\/+$/, "");
  if (!raiz) return [];
  const ac = new AbortController();
  const relogio = setTimeout(() => ac.abort(), 5000);
  try {
    const url = new URL("/cli/detectar", raiz.includes("://") ? raiz : `http://${raiz}`);
    const resposta = await fetch(url.toString(), { signal: ac.signal });
    if (!resposta.ok) return [];
    const corpo: unknown = await resposta.json();
    if (!Array.isArray(corpo)) return [];
    return corpo.map(validar).filter((c): c is CliDetectada => c !== null);
  } catch {
    return [];
  } finally {
    clearTimeout(relogio);
  }
}
