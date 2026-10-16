/** Vozes Kokoro próprias do Vard (voice_id do /falar quando roteadas pelo motor Kokoro local).
 *  Compatíveis com VOZES_KOKORO em voz/vard_voz/kokoro.py. */
export const VOZES_KOKORO = [
  { id: "pf_dora", rotulo: "Dora (pt-BR, feminina)" },
  { id: "pm_alex", rotulo: "Alex (pt-BR, masculina)" },
  { id: "pm_santa", rotulo: "Santa (pt-BR, masculina)" },
  { id: "af_heart", rotulo: "Heart (en-US, feminina)" },
  { id: "af_bella", rotulo: "Bella (en-US, feminina)" },
  { id: "am_adam", rotulo: "Adam (en-US, masculina)" },
  { id: "am_michael", rotulo: "Michael (en-US, masculina)" },
  { id: "bf_emma", rotulo: "Emma (en-GB, feminina)" },
  { id: "bm_george", rotulo: "George (en-GB, masculina)" },
] as const;

/** Vozes Edge TTS pt-BR (Microsoft Neural, via edge-tts no backend).
 *  Compatíveis com VOZES_EDGE_PT_BR em voz/vard_voz/edge.py. */
export const VOZES_EDGE_PT_BR = [
  { id: "pt-BR-FranciscaNeural", rotulo: "Francisca (pt-BR, feminina)" },
  { id: "pt-BR-AntonioNeural", rotulo: "Antônio (pt-BR, masculina)" },
  { id: "pt-BR-BrendaNeural", rotulo: "Brenda (pt-BR, feminina)" },
  { id: "pt-BR-DonatoNeural", rotulo: "Donato (pt-BR, masculina)" },
  { id: "pt-BR-ElzaNeural", rotulo: "Elza (pt-BR, feminina)" },
  { id: "pt-BR-FabioNeural", rotulo: "Fábio (pt-BR, masculina)" },
  { id: "pt-BR-GiovannaNeural", rotulo: "Giovanna (pt-BR, feminina)" },
  { id: "pt-BR-HumbertoNeural", rotulo: "Humberto (pt-BR, masculina)" },
  { id: "pt-BR-JulioNeural", rotulo: "Júlio (pt-BR, masculina)" },
  { id: "pt-BR-LeilaNeural", rotulo: "Leila (pt-BR, feminina)" },
  { id: "pt-BR-LeticiaNeural", rotulo: "Letícia (pt-BR, feminina)" },
  { id: "pt-BR-ManuelaNeural", rotulo: "Manuela (pt-BR, feminina)" },
  { id: "pt-BR-NicolauNeural", rotulo: "Nicolau (pt-BR, masculina)" },
  { id: "pt-BR-ThalitaNeural", rotulo: "Thalita (pt-BR, feminina)" },
  { id: "pt-BR-ValerioNeural", rotulo: "Valério (pt-BR, masculina)" },
  { id: "pt-BR-YaraNeural", rotulo: "Yara (pt-BR, feminina)" },
] as const;

/** Vozes Piper pt-BR (local, CPU, via piper-tts no backend).
 *  Compatíveis com VOZES_PIPER_PT_BR em voz/vard_voz/piper.py. */
export const VOZES_PIPER_PT_BR = [
  { id: "pt_BR-feminina-medium", rotulo: "Feminina (pt-BR, medium)" },
  { id: "pt_BR-masculina-medium", rotulo: "Masculina (pt-BR, medium)" },
  { id: "pt_BR-feminina-low", rotulo: "Feminina (pt-BR, low)" },
  { id: "pt_BR-masculina-low", rotulo: "Masculina (pt-BR, low)" },
] as const;