// Atalhos globais no formato do plugin global-shortcut do Tauri: normalização, captura pelo teclado e conflitos. Puro.

/** Ações com atalho global, na ordem do painel (a mesma da tabela ATALHOS do Rust). */
export const ACOES_ATALHO = ["falar", "parar", "mostrar", "config", "escuta", "sala", "naofalar"] as const;
export type AcaoAtalho = (typeof ACOES_ATALHO)[number];

export const ROTULOS_ATALHO: Record<AcaoAtalho, string> = {
  falar: "Falar (segurar)",
  parar: "Interromper a fala",
  mostrar: "Mostrar/ocultar o widget",
  config: "Abrir/fechar as configurações",
  escuta: "Ligar/desligar a escuta",
  sala: "Tela cheia (sala)",
  naofalar: "Não falar (ligar/desligar)",
};

/** Atalho que o Rust não conseguiu registrar no arranque (comando falhas_de_atalho). */
export interface FalhaAtalho { chave: string; combinacao: string; erro: string }

type Modificador = "Ctrl" | "Alt" | "Shift" | "Super";
const MODIFICADORES: Record<string, Modificador> = {
  ctrl: "Ctrl", control: "Ctrl", alt: "Alt", option: "Alt", shift: "Shift",
  super: "Super", win: "Super", meta: "Super", cmd: "Super", command: "Super",
};
const ORDEM: Modificador[] = ["Ctrl", "Alt", "Shift", "Super"];
const BARRA_INVERSA = String.fromCharCode(92);
const SINAIS: Record<string, string> = {
  ".": "Period", ",": "Comma", "-": "Minus", "=": "Equal", "/": "Slash", ";": "Semicolon", "'": "Quote",
  "`": "Backquote", "[": "BracketLeft", "]": "BracketRight", [BARRA_INVERSA]: "Backslash",
};
const NOMEADAS = [
  "Space", "Enter", "Tab", "Insert", "Delete", "Home", "End", "PageUp", "PageDown",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", ...Object.values(SINAIS),
];
const VISUAL: Record<string, string> = {
  Space: "Espaço", Super: "Win", ...Object.fromEntries(Object.entries(SINAIS).map(([sinal, nome]) => [nome, sinal])),
};

/** Uma tecla não modificadora no nome que o plugin aceita ("M", "1", "F5", "Comma", "Numpad0"...), ou null. */
export function teclaCanonica(t: string): string | null {
  const s = t.trim();
  if (SINAIS[s]) return SINAIS[s];
  let m = /^(?:key)?([a-z])$/i.exec(s);
  if (m) return m[1].toUpperCase();
  m = /^(?:digit)?([0-9])$/i.exec(s);
  if (m) return m[1];
  m = /^f([1-9]|1[0-9]|2[0-4])$/i.exec(s);
  if (m) return `F${m[1]}`;
  m = /^numpad([0-9])$/i.exec(s);
  if (m) return `Numpad${m[1]}`;
  return NOMEADAS.find((n) => n.toLowerCase() === s.toLowerCase()) ?? null;
}

/**
 * "ctrl + alt + ." vira "Ctrl+Alt+Period". null sem tecla, com duas teclas ou sem Ctrl, Alt ou Win
 * (um atalho global sem eles roubaria a digitação).
 */
export function normalizarAtalho(texto: string): string | null {
  const mods = new Set<Modificador>();
  let tecla: string | null = null;
  for (const parte of texto.split("+").map((p) => p.trim())) {
    if (!parte) return null;
    const mod = MODIFICADORES[parte.toLowerCase()];
    if (mod) { mods.add(mod); continue; }
    if (tecla !== null) return null;
    tecla = teclaCanonica(parte);
    if (tecla === null) return null;
  }
  if (tecla === null || !(mods.has("Ctrl") || mods.has("Alt") || mods.has("Super"))) return null;
  return [...ORDEM.filter((m) => mods.has(m)), tecla].join("+");
}

/** Combinação a partir de um keydown (campo de captura). null enquanto só há modificadores ou a tecla não é aceita. */
export function combinacaoDoEvento(ev: Pick<KeyboardEvent, "code" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">): string | null {
  const tecla = teclaCanonica(ev.code);
  if (!tecla) return null;
  const mods = [ev.ctrlKey && "Ctrl", ev.altKey && "Alt", ev.shiftKey && "Shift", ev.metaKey && "Super"].filter(Boolean);
  return normalizarAtalho([...mods, tecla].join("+"));
}

/** Para mostrar no painel: "Ctrl+Alt+Comma" vira "Ctrl+Alt+,"; "Super" vira "Win". */
export function exibirAtalho(combinacao: string): string {
  const n = normalizarAtalho(combinacao);
  return n ? n.split("+").map((p) => VISUAL[p] ?? p).join("+") : combinacao;
}

/** Pares [primeira, repetida] de ações com a mesma combinação (depois de normalizar). */
export function conflitos(atalhos: Record<AcaoAtalho, string>): [AcaoAtalho, AcaoAtalho][] {
  const vistos = new Map<string, AcaoAtalho>();
  const pares: [AcaoAtalho, AcaoAtalho][] = [];
  for (const acao of ACOES_ATALHO) {
    const chave = normalizarAtalho(atalhos[acao]) ?? atalhos[acao].trim().toLowerCase();
    const outra = vistos.get(chave);
    if (outra) pares.push([outra, acao]); else vistos.set(chave, acao);
  }
  return pares;
}

const TECLAS_ALTGR = new Set(["Q", "W", "E", "R", "C", "2", "3", "4", "5", "6", "Comma"]);

/** Aviso (não bloqueia) quando Ctrl+Alt+<tecla> coincide com AltGr+<tecla> do ABNT2; null se não há risco. */
export function avisoAltGr(atalho: string): string | null {
  const n = normalizarAtalho(atalho);
  if (!n) return null;
  const partes = n.split("+");
  if (partes.length !== 3 || partes[0] !== "Ctrl" || partes[1] !== "Alt" || !TECLAS_ALTGR.has(partes[2])) return null;
  const k = exibirAtalho(n).split("+")[2].toUpperCase();
  return `Em teclados ABNT2, Ctrl+Alt+${k} é a mesma tecla que AltGr+${k} (ç, /, ?, °...). Prefira outra tecla.`;
}

/** Motivo por ação para o painel marcar o campo. Vazio = pode salvar. */
export function validarAtalhos(atalhos: Record<AcaoAtalho, string>): Partial<Record<AcaoAtalho, string>> {
  const erros: Partial<Record<AcaoAtalho, string>> = {};
  for (const acao of ACOES_ATALHO) {
    if (normalizarAtalho(atalhos[acao]) === null) erros[acao] = "Combinação inválida: use Ctrl, Alt ou Win mais uma tecla.";
  }
  for (const [primeira, repetida] of conflitos(atalhos)) erros[repetida] ??= `Igual a "${ROTULOS_ATALHO[primeira]}".`;
  return erros;
}

// --- Migração 0.5 → 0.6 (Ctrl+Alt → Win) ---

/** Padrões antigos da 0.5 (Ctrl+Alt). Usados como referência para migração automática. */
export const ATALHOS_ANTIGOS: Record<AcaoAtalho, string> = {
  falar: "Ctrl+Alt+Space",
  parar: "Ctrl+Alt+Period",
  mostrar: "Ctrl+Alt+V",
  config: "Ctrl+Alt+P",
  escuta: "Ctrl+Alt+L",
  sala: "Ctrl+Alt+F",
  naofalar: "Ctrl+Alt+N",
};

/** Novos padrões da 0.6 (Win+Alt / Win+Shift). */
export const ATALHOS_NOVOS: Record<AcaoAtalho, string> = {
  falar: "Super+Alt+Space",
  parar: "Super+Alt+Period",
  mostrar: "Super+Alt+V",
  config: "Super+Shift+K",
  escuta: "Super+Alt+L",
  sala: "Super+Shift+G",
  naofalar: "Super+Alt+N",
};

/**
 * Migra atalhos da 0.5 para os novos padrões da 0.6.
 * Só migra se o valor for exatamente o padrão antigo; personalizações são preservadas.
 * Se já estiver usando Super (Win), não mexe.
 */
export function migrarAtalhosWin(atalhos: Record<AcaoAtalho, string>): Record<AcaoAtalho, string> {
  const saida = { ...atalhos };
  for (const acao of ACOES_ATALHO) {
    const atual = normalizarAtalho(saida[acao]) ?? saida[acao];
    const antigo = ATALHOS_ANTIGOS[acao];
    // Só migra se for exatamente o padrão antigo
    if (atual === antigo) {
      saida[acao] = ATALHOS_NOVOS[acao];
    }
  }
  return saida;
}
