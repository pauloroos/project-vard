import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { falaFixa } from "../src/audio/cache";

// Sem IndexedDB no Node: o cache sempre erra e a ordem das fontes é o que se prova aqui.
// O bloco "com IndexedDB falso" cobre a chave e a versão do banco.
describe("falaFixa", () => {
  beforeEach(() => { vi.spyOn(console, "warn").mockImplementation(() => {}); });

  it("usa a voz própria quando ela responde", async () => {
    const wavVoz = new ArrayBuffer(60);
    const oj = vi.fn().mockResolvedValue(new ArrayBuffer(50));
    const wav = await falaFixa("Voltei.", [
      { origem: "voz", voz: "Voz Teste", sintetizar: async () => wavVoz },
      { origem: "oj", voz: "pm_alex", sintetizar: oj },
    ]);
    expect(wav).toBe(wavVoz);
    expect(oj).not.toHaveBeenCalled();
  });

  it("voz própria fora: cai na reserva", async () => {
    const wavOj = new ArrayBuffer(50);
    const wav = await falaFixa("Voltei.", [
      { origem: "voz", voz: "Voz Teste", sintetizar: async () => { throw new Error("fora"); } },
      { origem: "oj", voz: "pm_alex", sintetizar: async () => wavOj },
    ]);
    expect(wav).toBe(wavOj);
    expect(console.warn).toHaveBeenCalledWith("voz própria falhou, usei a reserva", expect.any(Error));
  });

  it("todas falham: rejeita com o último erro", async () => {
    await expect(falaFixa("Voltei.", [{ origem: "oj", voz: "pm_alex", sintetizar: async () => { throw new Error("sem fala"); } }]))
      .rejects.toThrow("sem fala");
  });
});

/** IndexedDB mínimo: só o que o cache usa (open com upgrade, loja com get/put, transação). O estado persiste entre aberturas. */
function bancoFalso(versaoInicial = 0, lojaInicial?: Map<string, ArrayBuffer>) {
  const estado = { versao: versaoInicial, loja: lojaInicial as Map<string, ArrayBuffer> | undefined, abriuCom: [] as number[], upgrades: 0 };
  const indexedDB = {
    open(_nome: string, versao: number) {
      estado.abriuCom.push(versao);
      const req: Record<string, unknown> = {};
      const db = {
        objectStoreNames: { contains: () => estado.loja !== undefined },
        deleteObjectStore: () => { estado.loja = undefined; },
        createObjectStore: () => { estado.loja = new Map(); },
        close() {},
        transaction: () => {
          const t: Record<string, unknown> = {};
          return Object.assign(t, {
            objectStore: () => ({
              get: (k: string) => { const r: Record<string, unknown> = { result: estado.loja!.get(k) }; setTimeout(() => (r.onsuccess as () => void)()); return r; },
              put: (v: ArrayBuffer, k: string) => { estado.loja!.set(k, v); setTimeout(() => (t.oncomplete as () => void)()); return {}; },
            }),
          });
        },
      };
      req.result = db;
      setTimeout(() => {
        if (estado.versao < versao) { estado.versao = versao; estado.upgrades++; (req.onupgradeneeded as () => void)(); }
        (req.onsuccess as () => void)();
      });
      return req;
    },
  };
  return { estado, indexedDB };
}

describe("falaFixa com IndexedDB falso", () => {
  beforeEach(() => { vi.spyOn(console, "warn").mockImplementation(() => {}); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("grava e lê pela chave origem|voz|texto", async () => {
    const b = bancoFalso();
    vi.stubGlobal("indexedDB", b.indexedDB);
    const wav = new ArrayBuffer(60);
    const sint = vi.fn(async () => wav);
    await falaFixa("Voltei.", [{ origem: "voz", voz: "Voz Teste", sintetizar: sint }]);
    expect([...b.estado.loja!.keys()]).toEqual(["voz|Voz Teste|Voltei."]);
    // 2ª vez: vem do cache, sem sintetizar
    const de = await falaFixa("Voltei.", [{ origem: "voz", voz: "Voz Teste", sintetizar: sint }]);
    expect(sint).toHaveBeenCalledTimes(1);
    expect(de.byteLength).toBe(60);
    // outra origem ou outra voz não acerta a entrada
    await falaFixa("Voltei.", [{ origem: "oj", voz: "Voz Teste", sintetizar: sint }]);
    await falaFixa("Voltei.", [{ origem: "voz", voz: "Outra", sintetizar: sint }]);
    expect(sint).toHaveBeenCalledTimes(3);
    expect([...b.estado.loja!.keys()].sort()).toEqual(["oj|Voz Teste|Voltei.", "voz|Outra|Voltei.", "voz|Voz Teste|Voltei."]);
  });

  it("banco da versão 1 (chave voz|texto) é recomeçado ao abrir na versão 2", async () => {
    const velho = new Map([["pm_alex|Voltei.", new ArrayBuffer(80)]]);
    const b = bancoFalso(1, velho);
    vi.stubGlobal("indexedDB", b.indexedDB);
    const sint = vi.fn(async () => new ArrayBuffer(60));
    await falaFixa("Voltei.", [{ origem: "oj", voz: "pm_alex", sintetizar: sint }]);
    expect(b.estado.abriuCom.every((v) => v === 2)).toBe(true);
    expect(b.estado.upgrades).toBe(1);
    expect(sint).toHaveBeenCalledTimes(1); // a entrada antiga não serve
    expect([...b.estado.loja!.keys()]).toEqual(["oj|pm_alex|Voltei."]);
  });
});
