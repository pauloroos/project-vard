// Falas fixas: IndexedDB "vard" / store "falas", chave "origem|voz|texto" (origem "voz" ou "oj").
// Qualquer erro do IndexedDB cai para sintetizar sem cache; nunca derruba o ciclo.
const BANCO = "vard";
const LOJA = "falas";

function abrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(BANCO, 2);
    req.onupgradeneeded = () => {
      // Versão 1 usava a chave "voz|texto": recomeça a loja em vez de guardar entradas que ninguém mais lê.
      if (req.result.objectStoreNames.contains(LOJA)) req.result.deleteObjectStore(LOJA);
      req.result.createObjectStore(LOJA);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function ler(chave: string): Promise<ArrayBuffer | undefined> {
  const db = await abrir();
  try {
    return await new Promise((resolve, reject) => {
      const r = db.transaction(LOJA, "readonly").objectStore(LOJA).get(chave);
      r.onsuccess = () => resolve(r.result as ArrayBuffer | undefined);
      r.onerror = () => reject(r.error);
    });
  } finally { db.close(); }
}

async function gravar(chave: string, wav: ArrayBuffer): Promise<void> {
  const db = await abrir();
  try {
    await new Promise<void>((resolve, reject) => {
      const t = db.transaction(LOJA, "readwrite");
      t.objectStore(LOJA).put(wav, chave);
      t.oncomplete = () => resolve();
      t.onerror = () => reject(t.error);
    });
  } finally { db.close(); }
}

/** Uma origem possível para uma fala fixa: o serviço de voz próprio ("voz") ou o OpenJarvis ("oj"). */
export interface FonteDeFala { origem: "voz" | "oj"; voz: string; sintetizar: () => Promise<ArrayBuffer> }

/**
 * Fala fixa pela primeira fonte que der certo, na ordem dada: o cache dela e, sem cache, a síntese (que vai para o cache).
 * Rejeita só se todas falharem.
 */
export async function falaFixa(texto: string, fontes: FonteDeFala[]): Promise<ArrayBuffer> {
  let ultimoErro: unknown = new Error("nenhuma fonte de fala");
  for (const [i, f] of fontes.entries()) {
    const chave = `${f.origem}|${f.voz}|${texto}`;
    try {
      const guardado = await ler(chave);
      if (guardado && guardado.byteLength > 44) return guardado;
    } catch (erro) { console.warn("cache de falas indisponível", erro); }
    try {
      const wav = await f.sintetizar();
      try { await gravar(chave, wav.slice(0)); } catch (erro) { console.warn("não guardei a fala no cache", erro); }
      return wav;
    } catch (erro) {
      ultimoErro = erro;
      if (i < fontes.length - 1) console.warn("voz própria falhou, usei a reserva", erro);
    }
  }
  throw ultimoErro;
}
