import { simples } from "./rotas";

/** Expressões (já normalizadas por `simples`) que encerram o modo conversa e mutam o microfone. */
const ENCERRAMENTOS = [
  "parar de me ouvir", "pare de me ouvir", "para de me ouvir", "deixa de me ouvir", "nao precisa mais me ouvir",
  "entrar em reuniao", "entrando em reuniao", "estou em reuniao", "to em reuniao", "modo silencioso", "pode descansar",
];

/** true quando o texto (com ou sem o nome na frente, já tirado por quem chama) contém uma expressão de encerramento. */
export function ehEncerramento(texto: string): boolean {
  const t = simples(texto).replace(/[!.,?:;]/g, " ").replace(/\s+/g, " ").trim();
  return t !== "" && ENCERRAMENTOS.some((e) => t.includes(e));
}
