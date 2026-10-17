/** Capacidades do produto: nunca são gravadas como receitas do usuário; só os ajustes delas (habilidades.json, "fabrica"). */
import { IDS_FABRICA, type AjusteFabrica } from "./habilidades";

export interface HabilidadeFabrica {
  id: string; nome: string; quando: string[]; situacao: "capaz"; ligada: boolean; etiqueta: string | null;
  /** Frases sem o nome do assistente na frente, como ficam no modal de edição. */
  frases: string[];
  /** Orientação extra cadastrada pelo usuário ("" quando não há). */
  instrucoes: string;
  /** Tem ajuste gravado: oferece "Restaurar padrão". */
  personalizada: boolean;
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
/** Nome e frases de fábrica de uma capacidade, sem ajustes. */
export function padraoFabrica(id: string): { nome: string; frases: string[] } {
  const i = (IDS_FABRICA as readonly string[]).indexOf(id);
  if (i < 0) throw new Error("Habilidade de fábrica não encontrada");
  return { nome: CATEGORIAS[i][0], frases: [...CATEGORIAS[i][2]] };
}
export function habilidadesFabrica(nome: string, ponteNoAr: boolean, desligadas: string[] = [], temProvedorProprio = false, ajustes: Record<string, AjusteFabrica> = {}): HabilidadeFabrica[] {
  const texto = nome.trim() || "vard";
  const chamada = texto[0].toUpperCase() + texto.slice(1);
  return CATEGORIAS.map(([padrao, requisito, frasesPadrao], i) => {
    const id = IDS_FABRICA[i];
    const ajuste = ajustes[id];
    let etiqueta: string | null = null;
    if (requisito === true && !ponteNoAr) etiqueta = "precisa da instalação";
    else if (requisito === "agente" && !temProvedorProprio) etiqueta = "precisa de um agente configurado";
    const frases = [...(ajuste?.quando ?? frasesPadrao)];
    return {
      id, nome: ajuste?.nome ?? padrao, quando: frases.map((f) => `${chamada}, ${f}`), situacao: "capaz",
      ligada: !desligadas.includes(id), etiqueta, frases, instrucoes: ajuste?.instrucoes ?? "", personalizada: ajuste !== undefined,
    };
  });
}
