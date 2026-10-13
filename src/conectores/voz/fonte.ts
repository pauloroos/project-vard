import type { FalaEmFluxo } from "../../fala/conversa";

/** Uma fonte de voz (própria, ElevenLabs, Gemini): fala em fluxo PCM 16 bits mono e, para o cache, em WAV. */
export interface FonteDeVoz {
  /** Nome da voz em uso: entra na chave do cache das falas fixas. */
  readonly nome: string;
  /** Pronta para falar. Provedores na nuvem respondem sem rede (só conferem a chave). */
  saude(): Promise<boolean>;
  falar(texto: string, velocidade: number, sinal?: AbortSignal, prazoMs?: number): Promise<FalaEmFluxo>;
  falarWav(texto: string, velocidade: number, prazoMs?: number): Promise<ArrayBuffer>;
}
