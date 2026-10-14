// Lógica pura da aba: gatilho, rota, interrupção, janela de término. Sem DOM.
export const NOME = "vard";
export const VARIANTES = ["aurora", "vard", "varde", "vardi", "ward", "bard"];
export const FINISH_MS = 900;

function simples(t) {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

export function extrairComando(texto) {
  const original = texto.trim().replace(/^[\s,.!?]+/, "");
  const t = simples(original);
  for (const v of VARIANTES) {
    const m = t.match(new RegExp(`^${v}\\b[\\s,.!?:]*`));
    if (m) return original.slice(m[0].length).replace(/^[\s,.!?:]+/, "").trim();
  }
  return null;
}

const GATILHOS_SEE = ["o que voce esta vendo", "o que esta na tela", "olha a tela", "le isso", "leia isso", "o que e isso na tela", "ve a tela"];

export function classificar(comando) {
  const c = simples(comando);
  if (c.startsWith("modo jogo")) return "modo";
  if (GATILHOS_SEE.some((g) => c.startsWith(g))) return "see";
  return "ask";
}

export function ehInterrupcao(texto) {
  const c = simples(texto).replace(/[!.,]/g, "");
  return ["para", "pare", "espera", "cala a boca", "chega"].includes(c);
}

// Confirmação do modo jogo: só "sim" ou "confirmo", sozinhos ("simples", "Simone", "pode ser" não valem).
export function ehConfirmacao(texto) {
  return /^\s*(sim|confirmo)[\s.!]*$/i.test(String(texto ?? ""));
}

// O que a aba passa a ser depois de um /status. `status` null = a ponte não respondeu.
// Em "jogo" ou "ponte_fora" ninguém escuta; a aba só volta quando o /status disser "ligado"
// (ligando, erro e desconhecido mantêm o que estava).
export function proximoEstadoPorStatus(estadoAtual, status) {
  if (!status || typeof status !== "object") return "ponte_fora";
  if (status.modo === "jogo") return "jogo";
  if (status.modo === "ligado") return "ligado";
  return estadoAtual === "ligado" ? "ligado" : "jogo";
}

export const TETO_MS = 5000;

// Acha o gatilho em qualquer início de palavra; devolve o texto a partir dele (ou null).
export function aPartirDoGatilho(texto) {
  const palavras = texto.trim().split(/\s+/);
  for (let i = 0; i < palavras.length; i++) {
    const resto = palavras.slice(i).join(" ");
    const cmd = extrairComando(resto);
    if (cmd === null) continue;
    if (i === 0) return resto;            // gatilho no começo do trecho: vale, mesmo só o nome (saudação)
    if (cmd !== "") return resto;         // no meio da frase só vale com comando depois
    return null;                          // "abre o Chrome, Vard": nome no fim, ignora o trecho
  }
  return null;
}

// Junta os finais do reconhecedor num pedido só. Conversa de fundo sem "Vard" nunca entra no buffer.
export class JanelaTermino {
  constructor(ms, despachar, { teto = TETO_MS, semGatilho = () => false } = {}) {
    this.ms = ms; this.despachar = despachar; this.teto = teto; this.semGatilho = semGatilho;
    this.buffer = ""; this.timer = null; this.inicio = 0;
  }
  receber(textoFinal) {
    const t = textoFinal.trim();
    if (!t) return;
    const noMeio = aPartirDoGatilho(t);
    if (noMeio !== null) {
      this.buffer = noMeio; this.inicio = Date.now();      // gatilho (re)começa o pedido
    } else if (this.buffer) {
      this.buffer = (this.buffer + " " + t).trim();
    } else if (this.semGatilho()) {
      this.buffer = t; this.inicio = Date.now();           // ex.: "sim" da confirmação do modo jogo
    } else {
      return;                                              // conversa de fundo: descarta
    }
    if (this.timer) clearTimeout(this.timer);
    const restante = Math.max(0, this.teto - (Date.now() - this.inicio));
    this.timer = setTimeout(() => this._despachar(), Math.min(this.ms, restante));
  }
  _despachar() {
    const t = this.buffer; this.buffer = ""; this.timer = null;
    if (t) this.despachar(t);
  }
  cancelar() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null; this.buffer = "";
  }
}
