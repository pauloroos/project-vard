// Lógica pura de gatilho, rota e interrupção (porte do viewer/rotas.js do Vard). Sem DOM.
export type Rota = "see" | "modo" | "ask";

export function simples(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

const escapar = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Texto depois do nome (ou variante) no começo da frase; null se o nome não abre a frase. */
export function extrairComando(texto: string, variantes: string[]): string | null {
  const original = texto.trim().replace(/^[\s,.!?]+/, "");
  const t = simples(original);
  for (const v of variantes) {
    const m = t.match(new RegExp("^" + escapar(simples(v)) + "\\b[\\s,.!?:]*"));
    if (m) return original.slice(m[0].length).replace(/^[\s,.!?:]+/, "").trim();
  }
  return null;
}

const GATILHOS_SEE = ["o que voce esta vendo", "o que esta na tela", "olha a tela", "le isso", "leia isso", "o que e isso na tela", "ve a tela"];

// Fala natural ("consegue ver minha tela?", "dá uma olhada na tela"): cita a tela e pede para ver ou ler.
const VERBO_VER = /\b(ve|ver|veja|olha|olhe|olhar|olhada|enxerga|enxergar|le|ler|leia)\b/;
const O_QUE_TEM = /\bo que (tem|ta|esta|aparece)\b/;
const VENDO = /\bo que (voce )?(esta|ta) vendo\b/;
const TELA = /\btela\b/;

export function classificar(comando: string): Rota {
  const c = simples(comando);
  if (c.startsWith("modo jogo")) return "modo";
  if (GATILHOS_SEE.some((g) => c.startsWith(g))) return "see";
  if (VENDO.test(c)) return "see";
  if (TELA.test(c) &&(VERBO_VER.test(c) || O_QUE_TEM.test(c))) return "see";
  return "ask";
}

export function ehInterrupcao(texto: string): boolean {
  const c = simples(texto).replace(/[!.,]/g, "");
  return ["para", "pare", "espera", "cala a boca", "chega"].includes(c);
}

/** Confirmação do modo jogo: só "sim" ou "confirmo", sozinhos. */
export function ehConfirmacao(texto: string): boolean {
  return /^\s*(sim|confirmo)[\s.!]*$/i.test(String(texto ?? ""));
}

/** Acha o gatilho em qualquer início de palavra; devolve o texto a partir dele (ou null). */
export function aPartirDoGatilho(texto: string, variantes: string[]): string | null {
  const palavras = texto.trim().split(/\s+/);
  for (let i = 0; i < palavras.length; i++) {
    const resto = palavras.slice(i).join(" ");
    const cmd = extrairComando(resto, variantes);
    if (cmd === null) continue;
    if (i === 0) return resto;    // gatilho no começo: vale, mesmo só o nome (saudação)
    if (cmd !== "") return resto; // no meio da frase só vale com comando depois
    return null;                  // "abre o Chrome, Vard": nome no fim, ignora
  }
  return null;
}
