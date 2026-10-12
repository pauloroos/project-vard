// Falas fixas: IndexedDB "openjarvis-hud" / store "falas", chave "voz|texto".
// Qualquer erro do IndexedDB cai para sintetizar sem cache; nunca derruba o ciclo.
const BANCO = "openjarvis-hud";
const LOJA = "falas";

function abrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(BANCO, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(LOJA); };
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

export async function falaFixa(texto: string, voz: string, sintetizar: () => Promise<ArrayBuffer>): Promise<ArrayBuffer> {
  const chave = `${voz}|${texto}`;
  try {
    const guardado = await ler(chave);
    if (guardado && guardado.byteLength > 44) return guardado;
  } catch (erro) { console.warn("cache de falas indisponível", erro); }
  const wav = await sintetizar();
  try { await gravar(chave, wav.slice(0)); } catch (erro) { console.warn("não guardei a fala no cache", erro); }
  return wav;
}
