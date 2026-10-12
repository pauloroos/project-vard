import type { Mensagem } from "../fala/conversa";

/** Contrato de um conector: o que o Vard precisa de um assistente para ouvir, pensar e falar. */
export interface Conector {
  saude(): Promise<boolean>;
  modelos(): Promise<string[]>;
  transcrever(wav: ArrayBuffer, idioma: string): Promise<string>;
  perguntar(mensagens: Mensagem[], sinal?: AbortSignal): Promise<string>;
  sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer>;
}
