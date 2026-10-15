/** Estado do assistente de primeiro uso: cliente HTTP das rotas /primeiro-uso do núcleo.
 *  Separado da config ativa; instalação preexistente devolve concluido=true e o
 *  assistente nunca aparece nem muda preferências. */

export interface EstadoPrimeiroUso {
  schema: number;
  etapa: string;
  concluido: boolean;
  pendencias: string[];
  nome_chamada?: string;
  cerebro_id?: string;
  voz_id?: string;
  microfone_id?: string;
  saida_id?: string;
}

async function comTimeout<T>(ms: number, f: (sinal: AbortSignal) => Promise<T>): Promise<T> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  try {
    return await f(ac.signal);
  } finally {
    clearTimeout(t);
  }
}

/** Lê o estado atual do assistente; ponte ausente devolve null sem erro. */
export async function lerEstadoPrimeiroUso(ponteUrl: string): Promise<EstadoPrimeiroUso | null> {
  if (!ponteUrl) return null;
  try {
    return await comTimeout(5000, async (signal) => {
      const r = await fetch(`${ponteUrl}/primeiro-uso`, { signal });
      if (!r.ok) return null;
      return (await r.json()) as EstadoPrimeiroUso;
    });
  } catch {
    return null;
  }
}

/** Aplica patch de campos conhecidos ao estado; nome vazio é recusado pelo núcleo.
 *  Devolve o estado saneado ou null em caso de erro/rede. */
export async function atualizarEstadoPrimeiroUso(
  ponteUrl: string,
  patch: Partial<EstadoPrimeiroUso>,
): Promise<EstadoPrimeiroUso | null> {
  if (!ponteUrl) return null;
  try {
    return await comTimeout(5000, async (signal) => {
      const r = await fetch(`${ponteUrl}/primeiro-uso`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal,
      });
      if (!r.ok) return null;
      return (await r.json()) as EstadoPrimeiroUso;
    });
  } catch {
    return null;
  }
}

/** Reabre o assistente sem apagar escolhas salvas; devolve o novo estado ou null. */
export async function reabrirPrimeiroUso(ponteUrl: string): Promise<EstadoPrimeiroUso | null> {
  if (!ponteUrl) return null;
  try {
    return await comTimeout(5000, async (signal) => {
      const r = await fetch(`${ponteUrl}/primeiro-uso/reabrir`, {
        method: "POST",
        signal,
      });
      if (!r.ok) return null;
      return (await r.json()) as EstadoPrimeiroUso;
    });
  } catch {
    return null;
  }
}

/** true quando o assistente deve ser mostrado (concluido=false); false se concluído ou ponte ausente. */
export async function deveMostrarAssistente(ponteUrl: string): Promise<boolean> {
  const estado = await lerEstadoPrimeiroUso(ponteUrl);
  if (!estado) return false;
  return !estado.concluido;
}