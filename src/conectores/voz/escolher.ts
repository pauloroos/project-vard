import type { Config } from "../../config/config";
import { Voz } from "./cliente";
import type { FonteDeVoz } from "./fonte";
import { ElevenLabs } from "../nuvem/elevenlabs";
import { Gemini } from "../nuvem/gemini";

export const PROVEDORES_VOZ = ["propria", "openjarvis", "elevenlabs", "gemini"] as const;
export type ProvedorVoz = (typeof PROVEDORES_VOZ)[number];
export const FRASE_AMOSTRA = "Olá, eu sou a Vard. Esta é a minha voz.";

type Fetch = (url: string, init: RequestInit) => Promise<Response>;
type ConfigVoz = Pick<Config, "voz_provedor" | "voz_url" | "voz_propria" | "elevenlabs_chave" | "elevenlabs_voz" | "gemini_chave" | "gemini_voz">;

/** A fonte de voz da config; null = só a voz do OpenJarvis (Kokoro). Nuvem sem chave vira null com aviso. Nunca faz rede. */
export function criarFonteDeVoz(c: ConfigVoz, buscar?: Fetch): FonteDeVoz | null {
  const op = buscar ? { fetch: buscar } : {};
  switch (c.voz_provedor) {
    case "propria": return c.voz_url.trim() ? new Voz(c.voz_url.trim(), { ...op, voz: c.voz_propria }) : null;
    case "elevenlabs":
      if (!c.elevenlabs_chave.trim() || !c.elevenlabs_voz.trim()) { console.warn("ElevenLabs sem chave ou voz: uso a voz do OpenJarvis"); return null; }
      return new ElevenLabs(c.elevenlabs_chave.trim(), c.elevenlabs_voz.trim(), op);
    case "gemini":
      if (!c.gemini_chave.trim()) { console.warn("Gemini sem chave: uso a voz do OpenJarvis"); return null; }
      return new Gemini(c.gemini_chave.trim(), c.gemini_voz.trim() || "Kore", op);
    default: return null;
  }
}