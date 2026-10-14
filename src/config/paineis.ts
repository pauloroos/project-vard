/**
 * Configuração externa dos painéis (0.6).
 *
 * Arquivo: `%LOCALAPPDATA%\rdl-vard\config\paineis.json` (ou VARD_CONFIG/paineis.json).
 * Estado:  `%LOCALAPPDATA%\rdl-vard\paineis-estado.json` (ou VARD_DADOS/paineis-estado.json).
 *
 * Nenhum segredo no JSON; credenciais são referências ao cofre (tipo/id).
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, renameSync } from "node:fs";
import { join, dirname } from "node:path";

// --- Contrato (spec 0.6) ---

export type Agente = "claude" | "codex" | "opencode" | "agy";

export interface Provedor {
  id: string;
  nome: string;
  tipo: string;
  url_base: string;
  modelo: string;
  credencial_ref?: string;
}

export interface EscolhaAgente {
  padrao: string;
  modelos: string[];
}

export interface Mcp {
  id: string;
  nome: string;
  habilitado: boolean;
  command?: string;
  args?: string[];
  url?: string;
  credencial_ref?: string;
}

export interface PaineisConfig {
  versao: 1;
  provedores: Provedor[];
  ativo: string | null;
  reserva: string | null;
  agentes: Record<Agente, EscolhaAgente>;
  mcps: Mcp[];
}

export type EstadoFase = "pendente" | "aplicando" | "aplicado" | "erro";

export interface PaineisEstado {
  revisao: number;
  estado: EstadoFase;
  ativo_efetivo: string | null;
  reserva_efetiva: string | null;
  erro?: string;
}

// --- Caminhos ---

function baseUsuario(): string {
  const env = globalThis.process?.env ?? {};
  const local = (env as Record<string, string | undefined>).LOCALAPPDATA || (env as Record<string, string | undefined>).HOME || ".";
  return join(local, "rdl-vard");
}

export function caminhoPaineis(): string {
  const env = globalThis.process?.env ?? {};
  const override = ((env as Record<string, string | undefined>).VARD_CONFIG || "").trim();
  return override ? join(override, "paineis.json") : join(baseUsuario(), "config", "paineis.json");
}

export function caminhoEstado(): string {
  const env = globalThis.process?.env ?? {};
  const override = ((env as Record<string, string | undefined>).VARD_DADOS || "").trim();
  return override ? join(override, "paineis-estado.json") : join(baseUsuario(), "paineis-estado.json");
}

// --- Padrões ---

export const PAINEIS_PADRAO: PaineisConfig = {
  versao: 1,
  provedores: [],
  ativo: null,
  reserva: null,
  agentes: {
    claude: { padrao: "", modelos: [] },
    codex: { padrao: "", modelos: [] },
    opencode: { padrao: "", modelos: [] },
    agy: { padrao: "", modelos: [] },
  },
  mcps: [],
};

export const ESTADO_PADRAO: PaineisEstado = {
  revisao: 0,
  estado: "pendente",
  ativo_efetivo: null,
  reserva_efetiva: null,
};

// --- Validação ---

const AGENTES_VALIDOS: Agente[] = ["claude", "codex", "opencode", "agy"];
const ESTADOS_VALIDOS: EstadoFase[] = ["pendente", "aplicando", "aplicado", "erro"];

export function validarPaineis(raw: unknown): PaineisConfig {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("paineis.json deve ser um objeto");
  }
  const obj = raw as Record<string, unknown>;

  if (obj.versao !== 1) {
    throw new Error(`versão desconhecida: ${obj.versao}`);
  }

  // provedores
  if (!Array.isArray(obj.provedores)) throw new Error("provedores deve ser array");
  for (const p of obj.provedores) {
    if (typeof p !== "object" || p === null) throw new Error("provedor inválido");
    const pv = p as Record<string, unknown>;
    if (typeof pv.id !== "string" || !pv.id) throw new Error("provedor sem id");
    if (typeof pv.nome !== "string") throw new Error(`provedor ${pv.id} sem nome`);
    if (typeof pv.tipo !== "string" || !pv.tipo) throw new Error(`provedor ${pv.id} sem tipo`);
    if (typeof pv.url_base !== "string") throw new Error(`provedor ${pv.id} sem url_base`);
    if (typeof pv.modelo !== "string") throw new Error(`provedor ${pv.id} sem modelo`);
    if (pv.credencial_ref !== undefined && typeof pv.credencial_ref !== "string") {
      throw new Error(`provedor ${pv.id} com credencial_ref inválida`);
    }
  }

  // ativo / reserva
  if (obj.ativo !== null && typeof obj.ativo !== "string") throw new Error("ativo deve ser string ou null");
  if (obj.reserva !== null && typeof obj.reserva !== "string") throw new Error("reserva deve ser string ou null");

  // agentes
  if (typeof obj.agentes !== "object" || obj.agentes === null || Array.isArray(obj.agentes)) {
    throw new Error("agentes deve ser objeto");
  }
  const ag = obj.agentes as Record<string, unknown>;
  for (const chave of AGENTES_VALIDOS) {
    const entrada = ag[chave];
    if (typeof entrada !== "object" || entrada === null || Array.isArray(entrada)) {
      throw new Error(`agente ${chave} inválido`);
    }
    const e = entrada as Record<string, unknown>;
    if (typeof e.padrao !== "string") throw new Error(`agente ${chave} sem padrao`);
    if (!Array.isArray(e.modelos) || !e.modelos.every((m) => typeof m === "string")) {
      throw new Error(`agente ${chave} com modelos inválidos`);
    }
  }

  // mcps
  if (!Array.isArray(obj.mcps)) throw new Error("mcps deve ser array");
  for (const m of obj.mcps) {
    if (typeof m !== "object" || m === null) throw new Error("mcp inválido");
    const mv = m as Record<string, unknown>;
    if (typeof mv.id !== "string" || !mv.id) throw new Error("mcp sem id");
    if (typeof mv.nome !== "string") throw new Error(`mcp ${mv.id} sem nome`);
    if (typeof mv.habilitado !== "boolean") throw new Error(`mcp ${mv.id} sem habilitado`);

    const temCommand = mv.command !== undefined;
    const temUrl = mv.url !== undefined;
    if (temCommand) {
      if (typeof mv.command !== "string" || !mv.command) throw new Error(`mcp stdio ${mv.id} sem command`);
      if (mv.args !== undefined && (!Array.isArray(mv.args) || !mv.args.every((a) => typeof a === "string"))) {
        throw new Error(`mcp ${mv.id} com args inválidos`);
      }
    } else if (temUrl) {
      if (typeof mv.url !== "string" || !mv.url) throw new Error(`mcp http ${mv.id} sem url`);
    } else {
      throw new Error(`mcp ${mv.id} precisa de command (stdio) ou url (http)`);
    }

    if (mv.credencial_ref !== undefined && typeof mv.credencial_ref !== "string") {
      throw new Error(`mcp ${mv.id} com credencial_ref inválida`);
    }
  }

  return obj as unknown as PaineisConfig;
}

export function validarEstado(raw: unknown): PaineisEstado {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("estado deve ser objeto");
  }
  const obj = raw as Record<string, unknown>;

  if (typeof obj.revisao !== "number" || !Number.isInteger(obj.revisao) || obj.revisao < 0) {
    throw new Error("revisao deve ser inteiro >= 0");
  }
  if (typeof obj.estado !== "string" || !ESTADOS_VALIDOS.includes(obj.estado as EstadoFase)) {
    throw new Error(`estado desconhecido: ${obj.estado}`);
  }
  if (obj.ativo_efetivo !== null && typeof obj.ativo_efetivo !== "string") {
    throw new Error("ativo_efetivo deve ser string ou null");
  }
  if (obj.reserva_efetiva !== null && typeof obj.reserva_efetiva !== "string") {
    throw new Error("reserva_efetiva deve ser string ou null");
  }
  if (obj.erro !== undefined && typeof obj.erro !== "string") {
    throw new Error("erro deve ser string quando presente");
  }

  return obj as unknown as PaineisEstado;
}

// --- Leitura / Escrita ---

export function lerPaineis(): PaineisConfig {
  const caminho = caminhoPaineis();
  if (!existsSync(caminho)) return structuredClone(PAINEIS_PADRAO);
  try {
    const txt = readFileSync(caminho, "utf-8");
    return validarPaineis(JSON.parse(txt));
  } catch (e) {
    if ((e as { code?: string }).code === "ENOENT") return structuredClone(PAINEIS_PADRAO);
    throw e;
  }
}

export function gravarPaineis(cfg: PaineisConfig): void {
  validarPaineis(cfg); // valida antes de escrever
  const caminho = caminhoPaineis();
  mkdirSync(dirname(caminho), { recursive: true });
  const tmp = `${caminho}.tmp`;
  writeFileSync(tmp, JSON.stringify(cfg, null, 2), "utf-8");
  renameSync(tmp, caminho);
}

export function lerEstado(): PaineisEstado {
  const caminho = caminhoEstado();
  if (!existsSync(caminho)) return structuredClone(ESTADO_PADRAO);
  try {
    const txt = readFileSync(caminho, "utf-8");
    return validarEstado(JSON.parse(txt));
  } catch (e) {
    if ((e as { code?: string }).code === "ENOENT") return structuredClone(ESTADO_PADRAO);
    throw e;
  }
}

export function gravarEstado(estado: PaineisEstado): void {
  validarEstado(estado);
  const caminho = caminhoEstado();
  mkdirSync(dirname(caminho), { recursive: true });
  const tmp = `${caminho}.tmp`;
  writeFileSync(tmp, JSON.stringify(estado, null, 2), "utf-8");
  renameSync(tmp, caminho);
}