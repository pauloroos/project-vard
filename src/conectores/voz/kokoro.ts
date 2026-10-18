import catalogo from "../../../config/vozes.json";
/** Vozes Kokoro do serviço de voz do Vard (voz do /falar roteada ao motor Kokoro, sem OpenJarvis).
 *  Rótulos e reserva da lista; quem diz quais estão disponíveis é o /vozes do serviço.
 *  Compatíveis com VOZES_KOKORO em voz/vard_voz/kokoro.py. */
export const VOZES_KOKORO = catalogo.kokoro;

/** Vozes Edge TTS pt-BR (Microsoft Neural, via edge-tts no backend).
 *  Compatíveis com VOZES_EDGE_PT_BR em voz/vard_voz/edge.py. */
export const VOZES_EDGE_PT_BR = catalogo.edge;

/** Vozes Piper pt-BR (local, CPU, via piper-tts no backend).
 *  Compatíveis com VOZES_PIPER_PT_BR em voz/vard_voz/piper.py. */
export const VOZES_PIPER_PT_BR = catalogo.piper;