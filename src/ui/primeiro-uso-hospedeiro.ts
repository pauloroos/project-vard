/** Ligação do assistente de primeiro uso ao app hospedeiro (main.ts).
 *  Extrai a construção de deps e o ciclo abrir/reabrir para que seja testável
 *  sem depender do DOM completo do widget nem de Tauri. */
import type { Config } from "../config/config";
import { deveMostrarAssistente } from "../config/primeiro-uso";
import { montarAssistentePrimeiroUso, reabrirAssistentePrimeiroUso, type DepsPrimeiroUso } from "./primeiro-uso";

export interface DepsHospedeiroAudio {
  config: Config;
  transcrever: (wav: ArrayBuffer, sinal: AbortSignal) => Promise<string>;
  suspenderEscuta: () => Promise<() => void>;
  salvar: (resultado: { microfone_id: string; saida_id: string; voz_id: string }) => Promise<void>;
}

export interface DepsHospedeiro {
  ponteUrl: string;
  salvarNome: (nome: string, variantes: string[]) => Promise<void>;
  audio: DepsHospedeiroAudio;
  cerebro?: Record<string, unknown>;
}

export interface ContextoHospedeiro {
  /** Elemento raiz onde o assistente será montado. */
  raiz: HTMLElement;
  /** Verifica se o assistente deve abrir (ponte ausente = false). */
  deveMostrar: (ponteUrl: string) => Promise<boolean>;
  /** Monta o assistente; devolve função de limpeza ou null. */
  montar: (raiz: HTMLElement, deps: DepsPrimeiroUso) => Promise<(() => void) | null>;
  /** Reabre o assistente sem apagar escolhas; devolve nova limpeza ou null. */
  reabrir: (raiz: HTMLElement, deps: DepsPrimeiroUso) => Promise<(() => void) | null>;
}

const contextoPadrao: ContextoHospedeiro = {
  raiz: undefined as unknown as HTMLElement, // preenchido pelo chamador
  deveMostrar: deveMostrarAssistente,
  montar: montarAssistentePrimeiroUso,
  reabrir: reabrirAssistentePrimeiroUso,
};

/** Constrói as deps do assistente a partir das funções do widget hospedeiro.
 *  Mantém deps.cerebro como objeto vazio quando não fornecido (T3c injeta depois). */
export function construirDepsPrimeiroUso(deps: DepsHospedeiro): DepsPrimeiroUso {
  return {
    ponteUrl: deps.ponteUrl,
    salvarNome: deps.salvarNome,
    audio: {
      config: deps.audio.config,
      transcrever: deps.audio.transcrever,
      suspenderEscuta: deps.audio.suspenderEscuta,
      salvar: deps.audio.salvar,
    },
    cerebro: deps.cerebro ?? {},
  };
}

/** Abre o assistente se necessário e devolve o controle de limpeza.
 *  Ponte ausente ou instalação concluída retornam null sem erro. */
export async function abrirAssistenteSeNecessario(
  deps: DepsHospedeiro,
  ctx: Partial<ContextoHospedeiro> = {},
): Promise<(() => void) | null> {
  const contexto = { ...contextoPadrao, ...ctx };
  if (!contexto.raiz) throw new Error("raiz é obrigatória");
  try {
    if (!(await contexto.deveMostrar(deps.ponteUrl))) return null;
    return await contexto.montar(contexto.raiz, construirDepsPrimeiroUso(deps));
  } catch {
    return null;
  }
}

/** Reabre o assistente (botão nas Configurações), limpando a montagem anterior. */
export async function reabrirAssistente(
  deps: DepsHospedeiro,
  limparAnterior: (() => void) | null,
  ctx: Partial<ContextoHospedeiro> = {},
): Promise<(() => void) | null> {
  const contexto = { ...contextoPadrao, ...ctx };
  if (!contexto.raiz) throw new Error("raiz é obrigatória");
  limparAnterior?.();
  try {
    return await contexto.reabrir(contexto.raiz, construirDepsPrimeiroUso(deps));
  } catch {
    return null;
  }
}