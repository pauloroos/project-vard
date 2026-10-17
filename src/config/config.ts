import { invoke } from "@tauri-apps/api/core";
import { PROVEDORES_VOZ, type ProvedorVoz } from "../conectores/voz/escolher";
import { migrarAtalhosWin, normalizarAtalho, type AcaoAtalho } from "./atalhos";
import { CEREBRO_PADRAO, ehCerebro, type Cerebro } from "./cerebro";
import { validarDocumento } from "./ajustes";

export const TAMANHOS = ["pequeno", "medio", "grande", "personalizado"] as const;

export interface Config {
  openjarvis_url: string; gui_url: string; ponte_url: string;
  /** Serviço de voz próprio (POST /falar); vazio desliga e a voz fica sempre a do OpenJarvis. */
  voz_url: string;
  nome: string; usuario: string; variantes: string[]; idioma: string; voz: string; velocidade: number;
  vad: "energia" | "silero";
  interromper_ao_falar: boolean;
  finish_ms: number; limiar_vad: number; sempre_no_topo: boolean; click_through: boolean; invisivel: boolean;
  posicao: { x: number; y: number } | null;
  /** Tamanho do widget: preset ou "personalizado" (usa tamanho_px, lado em px lógicos). */
  tamanho: (typeof TAMANHOS)[number]; tamanho_px: number;
  /** Compacto: só o holograma; a barra de botões aparece com o mouse em cima. */
  compacto: boolean;
  atalhos: Record<AcaoAtalho, string>;
  instrucao_formato: string;
  /** Modelo principal do OpenJarvis; vazio = o primeiro que ele expõe. */
  modelo: string;
  /** Monitor da sala (tela cheia), pelo nome do sistema; vazio = o principal. O Rust lê a cada abertura. */
  sala_monitor: string;
  /** Modo conversa: ms ouvindo sem o nome depois de uma resposta; 0 desliga. */
  conversa_ms: number;
  /** Quem fala: voz própria (XTTS), voz do OpenJarvis (Kokoro) ou nuvem (ElevenLabs, Gemini). */
  voz_provedor: ProvedorVoz;
  /** Motor de fala dentro do serviço próprio (kokoro | edge | piper | xtts); vazio = automático pelo /saude. */
  voz_motor?: string;
  /** Voz do serviço próprio; vazio = a atual dele. */
  voz_propria: string;
  elevenlabs_chave: string; elevenlabs_voz: string;
  gemini_chave: string; gemini_voz: string;
  /** Voz de reserva: usada automaticamente quando a principal falhar. Mesma estrutura da principal (provedor+motor+id). */
  voz_reserva_provedor?: ProvedorVoz | "nenhuma";
  voz_reserva_motor?: string;
  voz_reserva_id?: string;
  /** Consulta a release mais nova ao abrir a aba Atualização do painel (só então; nunca em segundo plano). */
  atualizacao_ao_abrir: boolean;
  /** Não ouvir: microfone desligado (o mesmo que o botão Mudo do HUD). */
  nao_ouvir: boolean;
  /** Dispositivo de entrada selecionado (deviceId); vazio = padrão do sistema. */
  microfone_id: string;
  /** Rótulo do microfone selecionado (informativo, para quando o deviceId muda). */
  microfone_rotulo: string;
  /** Dispositivo de saída selecionado (deviceId); vazio = padrão do sistema. */
  saida_id: string;
  /** Rótulo da saída selecionada (informativo). */
  saida_rotulo: string;
  /** Não falar: a resposta aparece só em texto, sem síntese nem áudio. */
  nao_falar: boolean;
  /** Fala os avisos que chegam da ponte (tarefa/reunião); nunca com nao_falar ligado. */
  falar_avisos: boolean;
  /** Cérebro ativo: 'openjarvis' (padrão, nada muda) ou 'proprio' (usa rotas /pedidos do núcleo). */
  cerebro: Cerebro;
  /** Mantém o OpenJarvis ligado mesmo com cérebro próprio; serviços mudam após reiniciar. */
  usar_openjarvis: boolean;
  /** Cor dos elementos do widget (hex com #); vazio = ciano padrão. */
  cor_elementos: string;
  /** Opacidade dos elementos do widget (0.2 a 1); 1 = opaco. */
  opacidade_elementos: number;
}

export const CONFIG_PADRAO: Config = {
  openjarvis_url: "http://127.0.0.1:8000", gui_url: "http://127.0.0.1:5173", ponte_url: "http://127.0.0.1:4700",
  voz_url: "http://127.0.0.1:4710",
  nome: "vard", usuario: "", variantes: ["vard", "varde", "vardi", "ward", "bard"], idioma: "pt", voz: "pm_alex", velocidade: 1.05,
  vad: "energia", interromper_ao_falar: false,
  finish_ms: 900, limiar_vad: 0.02, sempre_no_topo: true, click_through: false, invisivel: false, posicao: null,
  tamanho: "medio", tamanho_px: 320, compacto: false,
  atalhos: {
    falar: "Alt+Super+Space", parar: "Alt+Super+Period", mostrar: "Alt+Super+V",
    config: "Shift+Super+K", escuta: "Alt+Super+L", sala: "Shift+Super+G", naofalar: "Alt+Super+N",
    conversa: "Alt+Super+C",
  },
  instrucao_formato: "Responda em até duas frases, para ser lido em voz alta.",
  modelo: "",
  sala_monitor: "",
  conversa_ms: 20000,
  voz_provedor: "propria", voz_motor: "", voz_propria: "", elevenlabs_chave: "", elevenlabs_voz: "", gemini_chave: "", gemini_voz: "Kore",
  voz_reserva_provedor: "nenhuma", voz_reserva_motor: "", voz_reserva_id: "",
  atualizacao_ao_abrir: false,
  nao_ouvir: false, nao_falar: false, falar_avisos: false,
  cerebro: CEREBRO_PADRAO,
  usar_openjarvis: false,
  microfone_id: "", microfone_rotulo: "", saida_id: "", saida_rotulo: "",
  cor_elementos: "", opacidade_elementos: 1,
};

/** Mescla o salvo com o padrão descartando o que tem tipo errado (arquivo editado à mão). */
export function normalizarConfig(salvo: unknown): Config {
  if (typeof salvo !== "object" || salvo === null || Array.isArray(salvo)) return { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } };
  const s = salvo as Record<string, unknown>;
  const saida: Record<string, unknown> = { ...s, ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } };
  for (const [k, padrao] of Object.entries(CONFIG_PADRAO)) {
    const v = s[k];
    if (k === "atalhos") {
      if (typeof v === "object" && v !== null && !Array.isArray(v)) {
        for (const a of Object.keys(CONFIG_PADRAO.atalhos)) {
          const x = (v as Record<string, unknown>)[a];
          if (typeof x === "string") (saida.atalhos as Record<string, string>)[a] = x;
        }
        // Migração: o antigo padrão do painel roubava o ç (AltGr+, no ABNT2); só esse valor exato migra.
        const at = saida.atalhos as Record<string, string>;
        if (at.config === "Ctrl+Alt+Comma") at.config = CONFIG_PADRAO.atalhos.config;
      }
      // Migração 0.6 → 0.6.1: Ctrl+Alt antigos viram Win+Alt/Win+Shift novos; personalizados ficam.
      saida.atalhos = migrarAtalhosWin(saida.atalhos as Record<AcaoAtalho, string>);
    } else if (k === "posicao") {
      const p = v as { x?: unknown; y?: unknown } | null;
      if (p === null || (typeof p === "object" && typeof p.x === "number" && typeof p.y === "number")) saida[k] = v;
    } else if (k === "variantes") {
      if (Array.isArray(v) && v.every((x) => typeof x === "string")) saida[k] = v;
    } else if (k === "tamanho") {
      if (typeof v === "string" && (TAMANHOS as readonly string[]).includes(v)) saida[k] = v;
    } else if (k === "vad") {
      if (v === "energia" || v === "silero") saida[k] = v;
    } else if (k === "voz_provedor") {
      if (typeof v === "string" && (PROVEDORES_VOZ as readonly string[]).includes(v)) saida[k] = v;
    } else if (k === "voz_reserva_provedor") {
      const validos = [...PROVEDORES_VOZ, "nenhuma"] as readonly string[];
      if (typeof v === "string" && validos.includes(v)) saida[k] = v;
    } else if (k === "voz_reserva_motor" || k === "voz_reserva_id") {
      if (typeof v === "string") saida[k] = v;
    } else if (k === "voz_motor") {
      if (typeof v === "string") saida[k] = v;
    } else if (k === "cor_elementos") {
      if (typeof v === "string" && (/^#[0-9a-fA-F]{6}$/.test(v) || v === "")) saida[k] = v;
    } else if (k === "opacidade_elementos") {
      if (typeof v === "number" && Number.isFinite(v) && v >= 0.2 && v <= 1) saida[k] = v;
    } else if (k === "conversa_ms") {
      if (typeof v === "number" && Number.isFinite(v) && v >= 0) saida[k] = Math.round(v);
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
    return normalizarConfig(salvo ?? {});
  } catch (erro) {
    console.warn("config ilegível, usando o padrão", erro);
    return normalizarConfig({});
  }
}

/** Palavras que chamam o assistente: o nome mais as variantes. Com outro nome, as variantes padrão do Vard saem. */
export function gatilhos(c: Pick<Config, "nome" | "variantes">): string[] {
  const nome = c.nome.trim().toLowerCase();
  const extras = nome === "vard" ? c.variantes : c.variantes.filter((v) => !CONFIG_PADRAO.variantes.includes(v.toLowerCase()));
  const todos = [nome, ...extras.map((v) => v.trim().toLowerCase())].filter(Boolean);
  return [...new Set(todos)];
}
export async function salvarConfig(c: Config): Promise<void> {
  validarDocumento("hud", c);
  await invoke("gravar_config", { config: c });
}

/** Lê o que está no disco, troca só as chaves de `parcial` e grava: quem tem uma cópia velha (o widget) não desfaz o que o painel salvou. */
export async function atualizarConfig(parcial: Partial<Config>): Promise<void> {
  const atual = normalizarConfig((await invoke<unknown>("ler_config")) ?? {});
  await salvarConfig({ ...atual, ...parcial });
}

/** true só para http(s) em 127.0.0.1 ou localhost: o HUD fala com serviços da própria máquina. */
export function urlLocal(u: string): boolean {
  try {
    const x = new URL(u);
    return (x.protocol === "http:" || x.protocol === "https:") && (x.hostname === "127.0.0.1" || x.hostname === "localhost");
  } catch { return false; }
}

/** Avisos (não bloqueiam o salvamento) para os campos de URL fora da máquina local. */
export function avisosDeUrl(c: Pick<Config, "openjarvis_url" | "gui_url" | "ponte_url" | "voz_url">): string[] {
  const nomes: [keyof typeof c, string][] = [
    ["openjarvis_url", "OpenJarvis"], ["gui_url", "Interface de texto"], ["ponte_url", "Ponte"], ["voz_url", "Serviço de voz"],
  ];
  return nomes.filter(([k]) => c[k] !== "" && !urlLocal(c[k])).map(([, n]) => `${n}: o endereço não é 127.0.0.1 nem localhost`);
}

/** Chaves que o widget aplica na hora (evento config-salva). O resto só vale depois de reiniciar. */
export const CHAVES_AO_VIVO = ["tamanho", "tamanho_px", "compacto", "sempre_no_topo", "click_through", "invisivel", "usuario", "modelo", "conversa_ms", "nao_ouvir", "nao_falar", "falar_avisos", "cerebro", "usar_openjarvis", "cor_elementos", "opacidade_elementos"] as const satisfies readonly (keyof Config)[];
export type ChaveAoVivo = (typeof CHAVES_AO_VIVO)[number];

/** Copia para a config viva do widget só as chaves ao vivo; devolve as que mudaram. */
export function aplicarAoVivo(vivo: Config, novo: Pick<Config, ChaveAoVivo>): ChaveAoVivo[] {
  const mudou: ChaveAoVivo[] = [];
  for (const k of CHAVES_AO_VIVO) {
    if (JSON.stringify(vivo[k]) !== JSON.stringify(novo[k])) { Object.assign(vivo, { [k]: novo[k] }); mudou.push(k); }
  }
  return mudou;
}

const REINICIO: [keyof Config, string][] = [
  ["openjarvis_url", "endereços"], ["gui_url", "endereços"], ["ponte_url", "endereços"], ["voz_url", "endereços"],
  ["nome", "nome de chamada"], ["variantes", "nome de chamada"], ["idioma", "idioma"],
  ["voz", "voz"], ["velocidade", "voz"], ["voz_provedor", "voz"], ["voz_propria", "voz"],
  ["elevenlabs_chave", "voz"], ["elevenlabs_voz", "voz"], ["gemini_chave", "voz"], ["gemini_voz", "voz"], ["instrucao_formato", "instrução de formato"],
  ["vad", "ouvido"], ["interromper_ao_falar", "ouvido"],
  ["finish_ms", "ouvido"], ["limiar_vad", "ouvido"], ["atalhos", "atalhos"],
];

const CAMPOS_VOZ_AO_VIVO = ["voz_provedor", "voz_motor", "voz_propria", "voz", "elevenlabs_voz", "gemini_voz", "voz_reserva_provedor", "voz_reserva_motor", "voz_reserva_id", "velocidade"] as const;

/** Troca só a seleção de voz; credenciais e endereços continuam com seu contrato próprio. */
export function aplicarVozAoVivo(vivo: Config, novo: Config): boolean {
  validarDocumento("hud", novo);
  let mudou = false;
  for (const chave of CAMPOS_VOZ_AO_VIVO) {
    if (vivo[chave] !== novo[chave]) { Object.assign(vivo, { [chave]: novo[chave] }); mudou = true; }
  }
  return mudou;
}

/** O que mudou e só vale depois de reiniciar o Vard, em palavras do painel e sem repetição. */
export function mudancasQueExigemReinicio(antes: Config, depois: Config): string[] {
  const r = new Set<string>();
  const igual = (k: keyof Config) => k === "atalhos"
    ? (Object.keys(depois.atalhos) as AcaoAtalho[]).every((a) => (normalizarAtalho(antes.atalhos[a]) ?? antes.atalhos[a]) === (normalizarAtalho(depois.atalhos[a]) ?? depois.atalhos[a]))
    : JSON.stringify(antes[k]) === JSON.stringify(depois[k]);
  for (const [k, rotulo] of REINICIO) if (!(CAMPOS_VOZ_AO_VIVO as readonly string[]).includes(k) && !igual(k)) r.add(rotulo);
  return [...r];
}

/** Lado personalizado do widget em px lógicos: 160 a 800, inteiro. */
export function limitarLado(px: number): number { return Math.min(800, Math.max(160, Math.round(px))); }

/** Valida o payload de config-salva (vem de outra janela): só as chaves ao vivo, com tipo e faixa; inválido devolve null. */
export function lerConfigAoVivo(x: unknown): Pick<Config, ChaveAoVivo> | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  const px = o.tamanho_px;
  if (!(TAMANHOS as readonly unknown[]).includes(o.tamanho)) return null;
  if (typeof px !== "number" || !Number.isFinite(px)) return null;
  if (typeof o.compacto !== "boolean" || typeof o.sempre_no_topo !== "boolean" || typeof o.click_through !== "boolean" || typeof o.invisivel !== "boolean") return null;
  if (typeof o.usuario !== "string" || typeof o.modelo !== "string") return null;
  if (typeof o.conversa_ms !== "number" || !Number.isFinite(o.conversa_ms) || o.conversa_ms < 0) return null;
  if (typeof o.nao_ouvir !== "boolean" || typeof o.nao_falar !== "boolean" || typeof o.falar_avisos !== "boolean") return null;
  const cerebro = ehCerebro(o.cerebro) ? o.cerebro : CEREBRO_PADRAO;
  if (o.usar_openjarvis !== undefined && typeof o.usar_openjarvis !== "boolean") return null;
  const usar_openjarvis = o.usar_openjarvis === true;
  const cor = typeof o.cor_elementos === "string" && (/^#[0-9a-fA-F]{6}$/.test(o.cor_elementos) || o.cor_elementos === "") ? o.cor_elementos : "";
  const opacidade = typeof o.opacidade_elementos === "number" && Number.isFinite(o.opacidade_elementos) && o.opacidade_elementos >= 0.2 && o.opacidade_elementos <= 1 ? o.opacidade_elementos : 1;
  return { tamanho: o.tamanho as Config["tamanho"], tamanho_px: limitarLado(px), compacto: o.compacto, sempre_no_topo: o.sempre_no_topo, click_through: o.click_through, invisivel: o.invisivel, usuario: o.usuario, modelo: o.modelo, conversa_ms: Math.round(o.conversa_ms), nao_ouvir: o.nao_ouvir, nao_falar: o.nao_falar, falar_avisos: o.falar_avisos, cerebro, usar_openjarvis, cor_elementos: cor, opacidade_elementos: opacidade };
}

/** Valida o payload de config-mudou-no-widget (topo e compacto); inválido devolve null. */
export function lerTopoCompacto(x: unknown): Pick<Config, "sempre_no_topo" | "compacto"> | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  if (typeof o.sempre_no_topo !== "boolean" || typeof o.compacto !== "boolean") return null;
  return { sempre_no_topo: o.sempre_no_topo, compacto: o.compacto };
}

/** Payload do widget quando o "não ouvir"/"não falar" muda pelo HUD, pelo atalho ou pela bandeja. */
export function lerNaoOuvirFalar(x: unknown): Pick<Config, "nao_ouvir" | "nao_falar"> | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  if (typeof o.nao_ouvir !== "boolean" || typeof o.nao_falar !== "boolean") return null;
  return { nao_ouvir: o.nao_ouvir, nao_falar: o.nao_falar };
}
