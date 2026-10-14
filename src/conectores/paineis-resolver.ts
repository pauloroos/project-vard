/**
 * Resolvedor de credenciais dos painéis (0.6).
 *
 * Conecta o cofre generalizado (T1) com a configuração de painéis (T2):
 * - `resolverCredencial(ref)` → lê do cofre sem expor valor em log/erro
 * - `verificarPaineis(cfg)` → lista refs ausentes no cofre
 * - `criarFonteDeVozComCofre(cfg, buscar?)` → factory que resolve credencial lazy
 *
 * Nada aqui imprime segredos.
 */
import { cofreExiste, cofreLer } from "../config/segredos";
import type { PaineisConfig, Provedor, Mcp } from "../config/paineis";
import type { FonteDeVoz } from "./voz/fonte";
import type { FalaEmFluxo } from "../fala/conversa";
import { ErroVoz } from "./voz/cliente";

/** Formato aceito: "tipo:id" onde tipo ∈ {provedor, voz, mcp}. */
export function parseRef(ref: string): { tipo: string; id: string } | null {
  if (typeof ref !== "string") return null;
  const idx = ref.indexOf(":");
  if (idx < 1) return null;
  const tipo = ref.slice(0, idx);
  const id = ref.slice(idx + 1);
  if (!["provedor", "voz", "mcp"].includes(tipo) || !id) return null;
  return { tipo, id };
}

/** Verifica se uma credencial existe no cofre. Nunca imprime valor. */
export async function credencialExiste(ref: string): Promise<boolean> {
  const p = parseRef(ref);
  if (!p) return false;
  try {
    return await cofreExiste(p.tipo, p.id);
  } catch {
    return false;
  }
}

/** Lista as refs de credencial ausentes no cofre para um config de painéis. */
export async function verificarPaineis(cfg: PaineisConfig): Promise<{ ok: boolean; faltantes: string[] }> {
  const faltantes: string[] = [];
  for (const prov of cfg.provedores) {
    if (prov.credencial_ref && !(await credencialExiste(prov.credencial_ref))) {
      faltantes.push(prov.credencial_ref);
    }
  }
  for (const mcp of cfg.mcps) {
    if (mcp.credencial_ref && !(await credencialExiste(mcp.credencial_ref))) {
      faltantes.push(mcp.credencial_ref);
    }
  }
  return { ok: faltantes.length === 0, faltantes };
}

/** Fonte de voz que falha claramente quando a credencial está ausente. */
class FonteSemCredencial implements FonteDeVoz {
  readonly nome: string;
  constructor(private provedor: string, private ref: string) {
    this.nome = `${provedor}:sem-credencial`;
  }
  async saude(): Promise<boolean> {
    return false;
  }
  async falar(): Promise<FalaEmFluxo> {
    throw new ErroVoz(`credencial ausente para ${this.provedor} (ref: ${this.ref})`, false);
  }
  async falarWav(): Promise<ArrayBuffer> {
    throw new ErroVoz(`credencial ausente para ${this.provedor} (ref: ${this.ref})`, false);
  }
}

/** Cria fonte de voz resolvendo credencial pelo cofre quando necessário. */
export async function criarFonteDeVozComCofre(
  provedorNome: string,
  credencialRef: string | undefined,
  factory: (chave: string) => FonteDeVoz,
  _cfg?: PaineisConfig,
): Promise<FonteDeVoz> {
  if (!credencialRef) {
    return new FonteSemCredencial(provedorNome, "(nenhuma ref informada)");
  }
  const p = parseRef(credencialRef);
  if (!p) return new FonteSemCredencial(provedorNome, credencialRef);
  try {
    const valor = await cofreLer(p.tipo, p.id);
    if (!valor) return new FonteSemCredencial(provedorNome, credencialRef);
    return factory(valor);
  } catch {
    return new FonteSemCredencial(provedorNome, credencialRef);
  }
}

/** Resolve Bearer/token de MCP via cofre antes do handshake. */
export async function resolverCredencialMcp(mcp: Mcp): Promise<string | null> {
  if (!mcp.credencial_ref) return null;
  const p = parseRef(mcp.credencial_ref);
  if (!p) return null;
  try {
    return await cofreLer(p.tipo, p.id);
  } catch {
    return null;
  }
}