import type { Mensagem } from "../fala/conversa";

/** Contrato de um conector: o que o Vard precisa de um assistente para ouvir, pensar e falar. */
export interface Conector {
  saude(): Promise<boolean>;
  modelos(): Promise<string[]>;
  /** Modelo preferido para as próximas perguntas; vazio = o primeiro de modelos(). Vale na próxima pergunta. */
  definirModelo(preferido: string): void;
  transcrever(wav: ArrayBuffer, idioma: string): Promise<string>;
  perguntar(mensagens: Mensagem[], sinal?: AbortSignal): Promise<string>;
  sintetizar(texto: string, voz: string, velocidade: number): Promise<ArrayBuffer>;
}
