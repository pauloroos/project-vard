/**
 * Acessor de credenciais via cofre Windows (Rust/Tauri).
 *
 * Expõe apenas presença, gravação e remoção; o valor nunca chega ao webview.
 * Comandos Tauri: cofre_existe, cofre_gravar, cofre_apagar.
 */
import { invoke } from "@tauri-apps/api/core";

const TIPOS_VALIDOS = ["provedor", "voz", "mcp"] as const;
export type TipoCredencial = (typeof TIPOS_VALIDOS)[number];

function validarTipo(tipo: string): TipoCredencial {
  if (!TIPOS_VALIDOS.includes(tipo as TipoCredencial)) {
    throw new Error(`tipo de credencial desconhecido: ${tipo}`);
  }
  return tipo as TipoCredencial;
}

function validarId(id: string): void {
  if (!id || id.length > 128) {
    throw new Error("id deve ter de 1 a 128 caracteres");
  }
  if (!/^[a-zA-Z0-9\-_.]+$/.test(id)) {
    throw new Error("id só aceita letras, dígitos, hífen, sublinhado e ponto");
  }
}

/** Verifica se uma credencial existe no cofre sem ler o valor. */
export async function cofreExiste(tipo: string, id: string): Promise<boolean> {
  try {
    const t = validarTipo(tipo);
    validarId(id);
    return await invoke<boolean>("cofre_existe", { tipo: t, id });
  } catch {
    return false;
  }
}

/** Grava uma credencial no cofre. Valor nunca é retornado ao webview. */
export async function cofreGravar(tipo: string, id: string, valor: string): Promise<void> {
  const t = validarTipo(tipo);
  validarId(id);
  if (!valor || valor.length > 4096) {
    throw new Error("valor deve ter de 1 a 4096 caracteres");
  }
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f]/.test(valor)) {
    throw new Error("valor não pode conter caracteres de controle");
  }
  await invoke("cofre_gravar", { tipo: t, id, valor });
}

/** Remove uma credencial do cofre. */
export async function cofreApagar(tipo: string, id: string): Promise<void> {
  const t = validarTipo(tipo);
  validarId(id);
  await invoke("cofre_apagar", { tipo: t, id });
}

/** Lê o valor de uma credencial. Apenas a janela de configurações pode chamar.
 * O valor nunca é logado ou impresso em erros. */
export async function cofreLer(tipo: string, id: string): Promise<string | null> {
  try {
    const t = validarTipo(tipo);
    validarId(id);
    return await invoke<string | null>("cofre_ler", { tipo: t, id });
  } catch {
    return null;
  }
}