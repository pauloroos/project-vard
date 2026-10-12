import { invoke } from "@tauri-apps/api/core";

export interface Config {
  openjarvis_url: string; gui_url: string; ponte_url: string;
  nome: string; variantes: string[]; idioma: string; voz: string; velocidade: number;
  finish_ms: number; limiar_vad: number; sempre_no_topo: boolean; click_through: boolean;
  posicao: { x: number; y: number } | null;
  atalhos: { falar: string; parar: string; mostrar: string };
  instrucao_formato: string;
}

export const CONFIG_PADRAO: Config = {
  openjarvis_url: "http://127.0.0.1:8000", gui_url: "http://127.0.0.1:5173", ponte_url: "http://127.0.0.1:4700",
  nome: "vard", variantes: ["vard", "varde", "vardi", "ward", "bard"], idioma: "pt", voz: "pm_alex", velocidade: 1.05,
  finish_ms: 900, limiar_vad: 0.02, sempre_no_topo: true, click_through: false, posicao: null,
  atalhos: { falar: "Ctrl+Alt+Space", parar: "Ctrl+Alt+Period", mostrar: "Ctrl+Alt+V" },
  instrucao_formato: "Responda em até duas frases, para ser lido em voz alta.",
};

export async function carregarConfig(): Promise<Config> {
  const salvo = (await invoke<Partial<Config> | null>("ler_config")) ?? {};
  return { ...CONFIG_PADRAO, ...salvo, atalhos: { ...CONFIG_PADRAO.atalhos, ...(salvo.atalhos ?? {}) } };
}
export async function salvarConfig(c: Config): Promise<void> { await invoke("gravar_config", { config: c }); }

/** true só para http(s) em 127.0.0.1 ou localhost: o HUD fala com serviços da própria máquina. */
export function urlLocal(u: string): boolean {
  try {
    const x = new URL(u);
    return (x.protocol === "http:" || x.protocol === "https:") && (x.hostname === "127.0.0.1" || x.hostname === "localhost");
  } catch { return false; }
}

/** Avisos (não bloqueiam o salvamento) para os campos de URL fora da máquina local. */
export function avisosDeUrl(c: Pick<Config, "openjarvis_url" | "gui_url" | "ponte_url">): string[] {
  const nomes: [keyof typeof c, string][] = [["openjarvis_url", "OpenJarvis"], ["gui_url", "Interface de texto"], ["ponte_url", "Ponte"]];
  return nomes.filter(([k]) => !urlLocal(c[k])).map(([, n]) => `${n}: o endereço não é 127.0.0.1 nem localhost`);
}
