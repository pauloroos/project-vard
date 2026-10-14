import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation((cmd: string, args?: Record<string, unknown>) => {
    if (cmd === "ler_paineis") return Promise.resolve(null);
    if (cmd === "gravar_paineis") return Promise.resolve(undefined);
    return Promise.resolve(null);
  }),
}));

import {
  lerPaineis,
  gravarPaineis,
  lerEstado,
  gravarEstado,
  validarPaineis,
  validarEstado,
  PAINEIS_PADRAO,
  ESTADO_PADRAO,
  type PaineisConfig,
  type PaineisEstado,
} from "../src/config/paineis";

describe("paineis (configuração externa 0.6)", () => {
  let dir: string;
  let configDir: string;
  let dadosDir: string;
  const origConfig = process.env.VARD_CONFIG;
  const origDados = process.env.VARD_DADOS;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "vard-paineis-"));
    configDir = join(dir, "config");
    dadosDir = join(dir, "dados");
    process.env.VARD_CONFIG = configDir;
    process.env.VARD_DADOS = dadosDir;
  });

  afterEach(() => {
    if (origConfig === undefined) delete process.env.VARD_CONFIG;
    else process.env.VARD_CONFIG = origConfig;
    if (origDados === undefined) delete process.env.VARD_DADOS;
    else process.env.VARD_DADOS = origDados;
    rmSync(dir, { recursive: true, force: true });
  });

  describe("leitura", () => {
    it("retorna padrão quando invoke retorna null", async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      vi.mocked(invoke).mockResolvedValueOnce(null);
      expect(await lerPaineis()).toEqual(PAINEIS_PADRAO);
    });

    it("lê e valida configuração existente via invoke", async () => {
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        provedores: [{ id: "suad", nome: "Suad", tipo: "local", url_base: "http://127.0.0.1:8000", modelo: "gemma" }],
      };
      const { invoke } = await import("@tauri-apps/api/core");
      vi.mocked(invoke).mockResolvedValueOnce(cfg);
      expect(await lerPaineis()).toEqual(cfg);
    });
  });

  describe("escrita", () => {
    it("chama invoke com arquivo=config e valor validado", async () => {
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        ativo: "suad",
        provedores: [{ id: "suad", nome: "Suad", tipo: "local", url_base: "http://127.0.0.1:8000", modelo: "gemma" }],
      };
      const { invoke } = await import("@tauri-apps/api/core");
      const mockInvoke = vi.mocked(invoke);
      await gravarPaineis(cfg);
      expect(mockInvoke).toHaveBeenCalledWith("gravar_paineis", { arquivo: "config", valor: cfg });
    });

    it("valida antes de escrever (rejeita config inválida)", async () => {
      const invalida = { ...PAINEIS_PADRAO, versao: 99 } as unknown as PaineisConfig;
      await expect(gravarPaineis(invalida)).rejects.toThrow("versão desconhecida");
    });
  });

  describe("validação paineis", () => {
    it("recusa versão desconhecida", () => {
      expect(() => validarPaineis({ versao: 2 })).toThrow("versão desconhecida");
    });

    it("recusa provedor sem id", () => {
      expect(() =>
        validarPaineis({
          ...PAINEIS_PADRAO,
          provedores: [{ nome: "X", tipo: "t", url_base: "u", modelo: "m" } as any],
        })
      ).toThrow("provedor sem id");
    });

    it("recusa provedor sem tipo", () => {
      expect(() =>
        validarPaineis({
          ...PAINEIS_PADRAO,
          provedores: [{ id: "x", nome: "X", url_base: "u", modelo: "m" } as any],
        })
      ).toThrow("sem tipo");
    });

    it("recusa mcp stdio sem command", () => {
      expect(() =>
        validarPaineis({
          ...PAINEIS_PADRAO,
          mcps: [{ id: "m", nome: "M", habilitado: true } as any],
        })
      ).toThrow("precisa de command");
    });

    it("recusa mcp http sem url", () => {
      expect(() =>
        validarPaineis({
          ...PAINEIS_PADRAO,
          mcps: [{ id: "m", nome: "M", habilitado: true, command: undefined, url: "" } as any],
        })
      ).toThrow("sem url");
    });

    it("aceita mcp stdio válido", () => {
      const cfg = {
        ...PAINEIS_PADRAO,
        mcps: [{ id: "fs", nome: "FS", habilitado: true, command: "node", args: ["server.js"] }],
      };
      expect(validarPaineis(cfg)).toEqual(cfg);
    });

    it("aceita mcp http válido", () => {
      const cfg = {
        ...PAINEIS_PADRAO,
        mcps: [{ id: "api", nome: "API", habilitado: false, url: "https://exemplo.com/mcp" }],
      };
      expect(validarPaineis(cfg)).toEqual(cfg);
    });
  });

  describe("estado", () => {
    it("retorna padrão quando arquivo não existe", async () => {
      expect(await lerEstado()).toEqual(ESTADO_PADRAO);
    });

    it("valida transições de estado (pendente → aplicando → aplicado)", () => {
      // A máquina de estados é validada pela função pura validarEstado;
      // a persistência via invoke é coberta pelo mock roundtrip abaixo.
      const e1: PaineisEstado = { ...ESTADO_PADRAO, estado: "pendente" };
      expect(validarEstado(e1).estado).toBe("pendente");

      const e2: PaineisEstado = { ...e1, estado: "aplicando", revisao: 1 };
      expect(validarEstado(e2).estado).toBe("aplicando");

      const e3: PaineisEstado = { ...e2, estado: "aplicado", revisao: 2, ativo_efetivo: "suad" };
      expect(validarEstado(e3)).toEqual(e3);
    });

    it("valida transição para erro com mensagem", () => {
      const e: PaineisEstado = { ...ESTADO_PADRAO, estado: "erro", erro: "falha na recarga" };
      expect(validarEstado(e).erro).toBe("falha na recarga");
    });

    it("recusa estado desconhecido", () => {
      expect(() => validarEstado({ ...ESTADO_PADRAO, estado: "desconhecido" })).toThrow("estado desconhecido");
    });

    it("recusa revisao negativa", () => {
      expect(() => validarEstado({ ...ESTADO_PADRAO, revisao: -1 })).toThrow("revisao deve ser inteiro >= 0");
    });
  });

  describe("invoke roundtrip", () => {
    it("gravarPaineis e lerPaineis chamam invoke com os argumentos corretos", async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      const mockInvoke = vi.mocked(invoke);

      // gravarPaineis chama invoke com arquivo=config
      await gravarPaineis(PAINEIS_PADRAO);
      expect(mockInvoke).toHaveBeenCalledWith("gravar_paineis", {
        arquivo: "config",
        valor: PAINEIS_PADRAO,
      });

      // lerPaineis chama invoke com arquivo=config e retorna null → padrão
      mockInvoke.mockResolvedValueOnce(null);
      const lido = await lerPaineis();
      expect(mockInvoke).toHaveBeenCalledWith("ler_paineis", { arquivo: "config" });
      expect(lido).toEqual(PAINEIS_PADRAO);
    });

    it("gravarEstado e lerEstado chamam invoke com arquivo=estado", async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      const mockInvoke = vi.mocked(invoke);

      await gravarEstado(ESTADO_PADRAO);
      expect(mockInvoke).toHaveBeenCalledWith("gravar_paineis", {
        arquivo: "estado",
        valor: ESTADO_PADRAO,
      });

      mockInvoke.mockResolvedValueOnce(null);
      const lido = await lerEstado();
      expect(mockInvoke).toHaveBeenCalledWith("ler_paineis", { arquivo: "estado" });
      expect(lido).toEqual(ESTADO_PADRAO);
    });
  });
});