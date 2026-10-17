/**
 * Oficina: habilidades.json na mesma pasta de paineis.json (VARD_CONFIG ou pasta de configuração).
 * { "versao": 1, "habilidades": [{ "id": "rotina-bom-dia", "nome": "Começar o dia",
 *   "quando": ["bom dia"], "instrucoes": "1. Consultar a agenda.", "ligada": true,
 *   "situacao": "treinada", "criada_em": "2026-10-17T12:00:00Z", "validada_em": null }],
 *   "desligadas": ["computador"] }
 * Só receitas do usuário são persistidas; fábrica fica no código. desligadas é opcional na leitura.
 * IDs: letras minúsculas ASCII/números separados por hífen, únicos e distintos dos IDs de fábrica.
 * Datas: UTC ISO 8601, segundos ou milissegundos; treinada exige null, validada exige data.
 * Campos desconhecidos são preservados. Leitura inválida falha sem sobrescrever o arquivo.
 * Limites: 200 receitas, nome 80, até 10 frases de 200 e instruções 4000.
 * Tamanhos de texto contam unidades UTF-16, como maxlength nos campos HTML.
 */
import { invoke } from "@tauri-apps/api/core";

export const IDS_FABRICA = ["conversa", "computador", "oficina", "consultas", "memoria", "reuniao", "sistema", "resumo-manha", "pesquisa", "agente-remoto"] as const;
export type SituacaoHabilidade = "treinada" | "validada";
export interface Habilidade {
  id: string;
  nome: string;
  quando: string[];
  instrucoes: string;
  ligada: boolean;
  situacao: SituacaoHabilidade;
  criada_em: string;
  validada_em: string | null;
}
export interface HabilidadesConfig { versao: 1; habilidades: Habilidade[]; desligadas: string[] }
export const HABILIDADES_PADRAO: HabilidadesConfig = { versao: 1, habilidades: [], desligadas: [] };
export const LIMITES_HABILIDADES = { habilidades: 200, nome: 80, frases: 10, frase: 200, instrucoes: 4000 } as const;
export const INSTRUCAO_HABILIDADES = "Há habilidades cadastradas pelo usuário; antes de agir num pedido, consulte listar_habilidades do MCP de configurações, se a ferramenta estiver disponível.";

function objeto(raw: unknown, _campos: string[]): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("habilidades.json deve conter objetos válidos");
  const obj = raw as Record<string, unknown>;
  return obj;
}
// Mesmo conjunto de espaços do Python/Rust, incluindo BOM, NEL e separadores de controle.
function texto(valor: unknown): valor is string { return typeof valor === "string" && /[^\s\u0085\u001c-\u001f]/u.test(valor); }
function data(valor: unknown): boolean {
  if (typeof valor !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$/.test(valor) || valor.startsWith("0000")) return false;
  const n = Date.parse(valor);
  return Number.isFinite(n) && new Date(n).toISOString() === (valor.includes(".") ? valor : valor.replace("Z", ".000Z"));
}

export function validarHabilidades(raw: unknown): HabilidadesConfig {
  const obj = objeto(raw, ["versao", "habilidades", "desligadas"]);
  if (obj.versao !== 1 || !Array.isArray(obj.habilidades)) throw new Error("Versão ou lista de habilidades inválida");
  if (obj.habilidades.length > LIMITES_HABILIDADES.habilidades) throw new Error("Cadastre até 200 habilidades");
  const desligadas = obj.desligadas === undefined ? [] : obj.desligadas;
  if (!Array.isArray(desligadas) || desligadas.some((id) => !(IDS_FABRICA as readonly unknown[]).includes(id)) || new Set(desligadas).size !== desligadas.length) {
    throw new Error("Lista de habilidades de fábrica desligadas inválida");
  }
  const ids = new Set<string>(IDS_FABRICA);
  for (const bruto of obj.habilidades) {
    const h = objeto(bruto, ["id", "nome", "quando", "instrucoes", "ligada", "situacao", "criada_em", "validada_em"]);
    if (typeof h.id !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(h.id) || ids.has(h.id)) throw new Error("ID de habilidade inválido ou repetido");
    ids.add(h.id);
    if (!texto(h.nome) || !texto(h.instrucoes) || !Array.isArray(h.quando) || h.quando.length === 0 || !h.quando.every(texto)) throw new Error("Preencha nome, frases de exemplo e instruções");
    if (h.nome.length > LIMITES_HABILIDADES.nome) throw new Error("Nome deve ter até 80 caracteres");
    if (h.quando.length > LIMITES_HABILIDADES.frases) throw new Error("Use até 10 frases de exemplo");
    if (h.quando.some((f) => f.length > LIMITES_HABILIDADES.frase)) throw new Error("Cada frase deve ter até 200 caracteres");
    if (h.instrucoes.length > LIMITES_HABILIDADES.instrucoes) throw new Error("Instruções devem ter até 4000 caracteres");
    if (typeof h.ligada !== "boolean" || !["treinada", "validada"].includes(h.situacao as string) || !data(h.criada_em)) throw new Error("Estado ou data de criação inválidos");
    if (h.situacao === "treinada" ? h.validada_em !== null : !data(h.validada_em)) throw new Error("Data de validação incompatível com a situação");
  }
  return structuredClone({ ...obj, desligadas }) as unknown as HabilidadesConfig;
}
export async function lerHabilidades(): Promise<HabilidadesConfig> {
  const raw = await invoke<unknown>("ler_habilidades");
  return raw == null ? structuredClone(HABILIDADES_PADRAO) : validarHabilidades(raw);
}
export async function gravarHabilidades(valor: HabilidadesConfig): Promise<void> {
  await invoke("gravar_habilidades", { valor: validarHabilidades(valor) });
}
