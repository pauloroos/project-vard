import { invoke } from "@tauri-apps/api/core";

export interface Config {
  openjarvis_url: string; gui_url: string; ponte_url: string;
  nome: string; usuario: string; variantes: string[]; idioma: string; voz: string; velocidade: number;
  finish_ms: number; limiar_vad: number; sempre_no_topo: boolean; click_through: boolean;
  posicao: { x: number; y: number } | null;
  atalhos: { falar: string; parar: string; mostrar: string };
  instrucao_formato: string;
}

export const CONFIG_PADRAO: Config = {
  openjarvis_url: "http://127.0.0.1:8000", gui_url: "http://127.0.0.1:5173", ponte_url: "http://127.0.0.1:4700",
  nome: "vard", usuario: "", variantes: ["vard", "varde", "vardi", "ward", "bard"], idioma: "pt", voz: "pm_alex", velocidade: 1.05,
  finish_ms: 900, limiar_vad: 0.02, sempre_no_topo: true, click_through: false, posicao: null,
  atalhos: { falar: "Ctrl+Alt+Space", parar: "Ctrl+Alt+Period", mostrar: "Ctrl+Alt+V" },
  instrucao_formato: "Responda em até duas frases, para ser lido em voz alta.",
};

/** Mescla o salvo com o padrão descartando o que tem tipo errado (arquivo editado à mão). */
function mesclar(salvo: unknown): Config {
  if (typeof salvo !== "object" || salvo === null || Array.isArray(salvo)) return { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } };
  const s = salvo as Record<string, unknown>;
  const saida: Record<string, unknown> = { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } };
  for (const [k, padrao] of Object.entries(CONFIG_PADRAO)) {
    const v = s[k];
    if (k === "atalhos") {
      if (typeof v === "object" && v !== null && !Array.isArray(v)) {
        for (const a of Object.keys(CONFIG_PADRAO.atalhos)) {
          const x = (v as Record<string, unknown>)[a];
          if (typeof x === "string") (saida.atalhos as Record<string, string>)[a] = x;
        }
      }
    } else if (k === "posicao") {
      const p = v as { x?: unknown; y?: unknown } | null;
      if (p === null || (typeof p === "object" && typeof p.x === "number" && typeof p.y === "number")) saida[k] = v;
    } else if (k === "variantes") {
      if (Array.isArray(v) && v.every((x) => typeof x === "string")) saida[k] = v;
    } else if (typeof v === typeof padrao) {
      saida[k] = v;
    }
  }
  return saida as unknown as Config;
}

/** Nunca lança: arquivo ausente, JSON inválido ou comando falhando devolvem o padrão. */
export async function carregarConfig(): Promise<Config> {
  try {
    const salvo = await invoke<unknown>("ler_config");
    return mesclar(salvo ?? {});
  } catch (erro) {
    console.warn("config ilegível, usando o padrão", erro);
    return mesclar({});
  }
}

/** Palavras que chamam o assistente: o nome mais as variantes. Com outro nome, as variantes padrão do Vard saem. */
export function gatilhos(c: Pick<Config, "nome" | "variantes">): string[] {
  const nome = c.nome.trim().toLowerCase();
  const extras = nome === "vard" ? c.variantes : c.variantes.filter((v) => !CONFIG_PADRAO.variantes.includes(v.toLowerCase()));
  const todos = [nome, ...extras.map((v) => v.trim().toLowerCase())].filter(Boolean);
  return [...new Set(todos)];
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
  return nomes.filter(([k]) => c[k] !== "" && !urlLocal(c[k])).map(([, n]) => `${n}: o endereço não é 127.0.0.1 nem localhost`);
}
