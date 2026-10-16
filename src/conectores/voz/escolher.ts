import type { Config } from "../../config/config";
import { Voz } from "./cliente";
import type { FonteDeVoz } from "./fonte";
import { ElevenLabs } from "../nuvem/elevenlabs";
import { Gemini } from "../nuvem/gemini";
import { OpenJarvis } from "../openjarvis/cliente";
import { fluxoParaWav } from "../../audio/wav";

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

/** Teste explícito: usa só o provedor escolhido, sem voz de reserva nem confirmação presumida. */
export async function ouvirTesteVoz(c: Config, saidaId: string, sinal: AbortSignal): Promise<void> {
  const frase = "O teste de voz está funcionando";
  let contexto: AudioContext | undefined;
  let fonte: AudioBufferSourceNode | undefined;
  let leitor: ReadableStream<Uint8Array> | undefined;
  let rejeitar: (() => void) | undefined;
  const abortar = () => {
    try { fonte?.stop(); } catch { /* já encerrada */ }
    void contexto?.close().catch(() => {});
    rejeitar?.();
  };
  const conferir = () => { if (sinal.aborted) throw new DOMException("Teste cancelado", "AbortError"); };
  sinal.addEventListener("abort", abortar, { once: true });
  try {
    conferir();
    let wav: ArrayBuffer;
    if (c.voz_provedor === "openjarvis") {
      wav = await new OpenJarvis(c.openjarvis_url).sintetizar(frase, c.voz, c.velocidade, sinal);
    } else {
      const voz = criarFonteDeVoz(c);
      if (!voz) throw new Error("Voz indisponível");
      const fala = await voz.falar(frase, c.velocidade, sinal);
      leitor = fala.corpo;
      wav = await fluxoParaWav(fala.corpo, fala.taxa);
    }
    conferir();
    contexto = new AudioContext();
    if (saidaId) {
      if (!("setSinkId" in contexto)) throw new Error("Seleção de saída indisponível");
      await (contexto as AudioContext & { setSinkId(id: string): Promise<void> }).setSinkId(saidaId);
    }
    conferir();
    if (contexto.state === "suspended") await contexto.resume();
    const buffer = await contexto.decodeAudioData(wav.slice(0));
    conferir();
    fonte = contexto.createBufferSource(); fonte.buffer = buffer; fonte.connect(contexto.destination);
    await new Promise<void>((ok, falhar) => {
      rejeitar = () => falhar(new DOMException("Teste cancelado", "AbortError"));
      fonte!.onended = () => ok(); fonte!.start();
    });
    conferir();
  } finally {
    sinal.removeEventListener("abort", abortar);
    if (fonte) { fonte.onended = null; fonte.disconnect(); }
    if (leitor && !leitor.locked) await leitor.cancel().catch(() => {});
    if (contexto?.state !== "closed") await contexto?.close().catch(() => {});
  }
}
