/**
 * Perfil do agente (T14a): tom, personalidade, instruções e sobre a pessoa.
 *
 * Arquivo: `%LOCALAPPDATA%\rdl-vard\config\perfil.json` (ou VARD_CONFIG/perfil.json),
 * o mesmo que o núcleo lê; a prévia montada vem de `GET /perfil/persona` da ponte.
 * Nome e "como te chamar" continuam no config.json (aba Geral), não aqui.
 */
import { invoke } from "@tauri-apps/api/core";

export interface Perfil {
  versao: 1;
  tom: string;
  personalidade: string;
  instrucoes: string;
  sobre_usuario: string;
}

export const PERFIL_PADRAO: Perfil = {
  versao: 1,
  tom: "",
  personalidade: "",
  instrucoes: "",
  sobre_usuario: "",
};

const CAMPOS = ["tom", "personalidade", "instrucoes", "sobre_usuario"] as const;

export function validarPerfil(raw: unknown): Perfil {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("perfil.json deve ser um objeto");
  }
  const obj = raw as Record<string, unknown>;
  if (obj.versao !== 1) throw new Error(`versão desconhecida: ${obj.versao}`);
  const perfil: Perfil = { ...PERFIL_PADRAO };
  for (const campo of CAMPOS) {
    const bruto = obj[campo];
    if (bruto === undefined) continue;
    if (typeof bruto !== "string") throw new Error(`${campo} deve ser texto`);
    perfil[campo] = bruto;
  }
  return perfil;
}

/** Lê o perfil salvo; sem arquivo, ilegível ou de outra versão volta ao padrão e avisa no console. */
export async function lerPerfil(): Promise<Perfil> {
  try {
    const raw = await invoke<unknown>("ler_perfil");
    if (raw === null || raw === undefined) return { ...PERFIL_PADRAO };
    return validarPerfil(raw);
  } catch (erro) {
    console.warn("perfil ilegível, usando o padrão", erro);
    return { ...PERFIL_PADRAO };
  }
}

/** Grava o perfil (inválidos não passam). */
export async function gravarPerfil(perfil: Perfil): Promise<void> {
  validarPerfil(perfil);
  await invoke("gravar_perfil", { valor: perfil });
}

/**
 * Prévia da persona pela ponte (`GET /perfil/persona?nome=&usuario=`).
 * `null` quando a ponte está vazia ou não responde.
 */
export async function previaPersona(base: string, nome: string, usuario: string): Promise<string | null> {
  const raiz = base.trim().replace(/\/+$/, "");
  if (!raiz) return null;
  const ac = new AbortController();
  const relogio = setTimeout(() => ac.abort(), 5000);
  try {
    const url = new URL("/perfil/persona", raiz.includes("://") ? raiz : `http://${raiz}`);
    if (nome) url.searchParams.set("nome", nome);
    if (usuario) url.searchParams.set("usuario", usuario);
    const resposta = await fetch(url.toString(), { signal: ac.signal });
    if (!resposta.ok) return null;
    const corpo = (await resposta.json()) as { texto?: unknown };
    return typeof corpo.texto === "string" && corpo.texto.trim() ? corpo.texto : null;
  } catch {
    return null;
  } finally {
    clearTimeout(relogio);
  }
}
