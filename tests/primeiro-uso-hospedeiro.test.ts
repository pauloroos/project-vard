import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Config } from "../src/config/config";
import { CONFIG_PADRAO } from "../src/config/config";
import {
  construirDepsPrimeiroUso,
  abrirAssistenteSeNecessario,
  reabrirAssistente,
  type DepsHospedeiro,
} from "../src/ui/primeiro-uso-hospedeiro";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function depsBase(overrides: Partial<DepsHospedeiro> = {}): DepsHospedeiro {
  return {
    ponteUrl: "http://127.0.0.1:18765",
    salvarNome: vi.fn().mockResolvedValue(undefined),
    audio: {
      config: { ...CONFIG_PADRAO } as Config,
      transcrever: vi.fn().mockResolvedValue("texto"),
      suspenderEscuta: vi.fn().mockResolvedValue(() => {}),
      salvar: vi.fn().mockResolvedValue(undefined),
    },
    cerebro: {},
    ...overrides,
  };
}

describe("primeiro-uso-hospedeiro", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    document.body.innerHTML = "";
  });

  describe("construirDepsPrimeiroUso", () => {
    it("monta deps.audio com as funções do widget e deps.cerebro vazio quando omitido", () => {
      const deps = depsBase();
      delete (deps as unknown as Record<string, unknown>).cerebro;
      const resultado = construirDepsPrimeiroUso(deps);
      expect(resultado.audio).toBeDefined();
      expect(resultado.audio!.transcrever).toBe(deps.audio.transcrever);
      expect(resultado.audio!.suspenderEscuta).toBe(deps.audio.suspenderEscuta);
      expect(resultado.audio!.salvar).toBe(deps.audio.salvar);
      expect(resultado.cerebro).toEqual({});
    });

    it("preserva deps.cerebro fornecido pelo chamador", () => {
      const cerebro = { id: "local" };
      const resultado = construirDepsPrimeiroUso(depsBase({ cerebro }));
      expect(resultado.cerebro).toBe(cerebro);
    });
  });

  describe("abrirAssistenteSeNecessario", () => {
    it("instalação nova abre o assistente e devolve função de limpeza", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "importar", concluido: false, pendencias: [] }),
      });
      const raiz = document.createElement("div");
      const limpar = await abrirAssistenteSeNecessario(depsBase(), { raiz });
      expect(limpar).not.toBeNull();
      expect(raiz.querySelector("#primeiro-uso-etapa")).not.toBeNull();
      limpar?.();
      expect(raiz.querySelector("#primeiro-uso-etapa")).toBeNull();
    });

    it("instalação existente (concluido=true) NÃO abre e devolve null", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ schema: 1, etapa: "resumo", concluido: true, pendencias: [] }),
      });
      const raiz = document.createElement("div");
      const limpar = await abrirAssistenteSeNecessario(depsBase(), { raiz });
      expect(limpar).toBeNull();
      expect(raiz.childElementCount).toBe(0);
    });

    it("ponte ausente não bloqueia e devolve null sem erro", async () => {
      fetchMock.mockRejectedValue(new Error("rede"));
      const raiz = document.createElement("div");
      const limpar = await abrirAssistenteSeNecessario(depsBase(), { raiz });
      expect(limpar).toBeNull();
      expect(raiz.childElementCount).toBe(0);
    });
  });

  describe("reabrirAssistente", () => {
    it("limpa montagem anterior e reabre o assistente", async () => {
      // abrirAssistenteSeNecessario: 1 GET /primeiro-uso (deveMostrar → lerEstado)
      // reabrirAssistente: 1 POST /primeiro-uso/reabrir + 1 GET /primeiro-uso (montar → lerEstado)
      const estadoInicial = { schema: 1, etapa: "importar", concluido: false, pendencias: [] };
      const estadoReaberto = { schema: 1, etapa: "nome", concluido: false, pendencias: [], nome_chamada: "Teste" };
      fetchMock
        .mockResolvedValueOnce({ ok: true, json: async () => estadoInicial })   // abrir: GET deveMostrar
        .mockResolvedValueOnce({ ok: true, json: async () => estadoInicial })   // abrir: GET montar
        .mockResolvedValueOnce({ ok: true, json: async () => estadoReaberto })  // reabrir: POST /reabrir
        .mockResolvedValueOnce({ ok: true, json: async () => estadoReaberto }); // reabrir: GET montar
      const raiz = document.createElement("div");
      const limpar1 = await abrirAssistenteSeNecessario(depsBase(), { raiz });
      expect(limpar1).not.toBeNull();
      expect(raiz.querySelector("#primeiro-uso-etapa")).not.toBeNull();
      const limpar2 = await reabrirAssistente(depsBase(), limpar1, { raiz });
      expect(limpar2).not.toBeNull();
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/primeiro-uso/reabrir"),
        expect.objectContaining({ method: "POST" }),
      );
      limpar2?.();
      expect(raiz.querySelector("#primeiro-uso-etapa")).toBeNull();
    });

    it("suspenderEscuta restaura o estado anterior após o teste", async () => {
      let mudo = false;
      const estaMudo = () => mudo;
      const definirMudo = (v: boolean) => { mudo = v; };
      const suspenderEscuta = async () => {
        const estava = estaMudo();
        if (!estava) definirMudo(true);
        return async () => { if (!estava) definirMudo(false); };
      };
      const deps = depsBase({ audio: { ...depsBase().audio, suspenderEscuta } });
      const resultado = construirDepsPrimeiroUso(deps);
      const restaurar = await resultado.audio!.suspenderEscuta();
      expect(mudo).toBe(true);
      await restaurar();
      expect(mudo).toBe(false);
    });
  });
});