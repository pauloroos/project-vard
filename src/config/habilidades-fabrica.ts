/** Capacidades do produto: nunca são gravadas como receitas do usuário. */
import { IDS_FABRICA } from "./habilidades";

export interface HabilidadeFabrica {
  id: string; nome: string; quando: string[]; situacao: "capaz"; ligada: boolean; etiqueta: string | null;
}
const CATEGORIAS: [string, boolean | "agente", string[]][] = [
  ["Conversa", false, ["que horas são?", "me explica ..."]],
  ["Computador", true, ["abre o YouTube", "o que está na minha tela?", "organiza as janelas"]],
  ["Oficina", true, ["manda o Codex criar um teste no projeto", "como está a tarefa 3?", "aprova a tarefa 3"]],
  ["Consultas", true, ["pede ao Claude pra ver as issues do Linear", "pergunta ao Codex o que tenho na agenda"]],
  ["Memória", true, ["lembra que ...", "o que eu pedi pra você lembrar sobre ..."]],
  ["Reunião", true, ["acompanha a reunião", "encerra a reunião", "gera a ata"]],
  ["Sistema", true, ["modo jogo", "volta do jogo", "bom dia, vamos começar o dia"]],
  ["Resumo da manhã", "agente", ["bom dia, qual é o resumo de hoje?", "me dá o resumo da manhã"]],
  ["Pesquisa", "agente", ["pesquisa sobre ...", "busca informações sobre ..."]],
  ["Agente remoto", "agente", ["roda o agente remoto", "executa a tarefa remota"]],
];
export function habilidadesFabrica(nome: string, ponteNoAr: boolean, desligadas: string[] = [], temProvedorProprio = false): HabilidadeFabrica[] {
  const texto = nome.trim() || "vard";
  const chamada = texto[0].toUpperCase() + texto.slice(1);
  return CATEGORIAS.map(([nome, requisito, frases], i) => {
    let etiqueta: string | null = null;
    if (requisito === true && !ponteNoAr) etiqueta = "precisa da instalação";
    else if (requisito === "agente" && !temProvedorProprio) etiqueta = "precisa de um agente configurado";
    return {
      id: IDS_FABRICA[i], nome, quando: frases.map((f) => `${chamada}, ${f}`), situacao: "capaz",
      ligada: !desligadas.includes(IDS_FABRICA[i]), etiqueta,
    };
  });
}
