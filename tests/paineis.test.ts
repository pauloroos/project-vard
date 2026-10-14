import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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
    it("retorna padrão quando arquivo não existe", () => {
      expect(lerPaineis()).toEqual(PAINEIS_PADRAO);
    });

    it("lê e valida arquivo existente", () => {
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        provedores: [{ id: "suad", nome: "Suad", tipo: "local", url_base: "http://127.0.0.1:8000", modelo: "gemma" }],
      };
      gravarPaineis(cfg);
      expect(lerPaineis()).toEqual(cfg);
    });
  });

  describe("escrita", () => {
    it("cria arquivo e confirma leitura", () => {
      const cfg: PaineisConfig = {
        ...PAINEIS_PADRAO,
        ativo: "suad",
        provedores: [{ id: "suad", nome: "Suad", tipo: "local", url_base: "http://127.0.0.1:8000", modelo: "gemma" }],
      };
      gravarPaineis(cfg);
      expect(existsSync(join(configDir, "paineis.json"))).toBe(true);
      expect(lerPaineis()).toEqual(cfg);
    });

    it("escrita é atômica (tmp + rename)", () => {
      gravarPaineis(PAINEIS_PADRAO);
      expect(existsSync(join(configDir, "paineis.json.tmp"))).toBe(false);
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
    it("retorna padrão quando arquivo não existe", () => {
      expect(lerEstado()).toEqual(ESTADO_PADRAO);
    });

    it("transições pendente → aplicando → aplicado", () => {
      const e1: PaineisEstado = { ...ESTADO_PADRAO, estado: "pendente" };
      gravarEstado(e1);
      expect(lerEstado().estado).toBe("pendente");

      const e2: PaineisEstado = { ...e1, estado: "aplicando", revisao: 1 };
      gravarEstado(e2);
      expect(lerEstado().estado).toBe("aplicando");

      const e3: PaineisEstado = { ...e2, estado: "aplicado", revisao: 2, ativo_efetivo: "suad" };
      gravarEstado(e3);
      expect(lerEstado()).toEqual(e3);
    });

    it("transição para erro com mensagem", () => {
      const e: PaineisEstado = { ...ESTADO_PADRAO, estado: "erro", erro: "falha na recarga" };
      gravarEstado(e);
      expect(lerEstado().erro).toBe("falha na recarga");
    });

    it("recusa estado desconhecido", () => {
      expect(() => validarEstado({ ...ESTADO_PADRAO, estado: "desconhecido" })).toThrow("estado desconhecido");
    });

    it("recusa revisao negativa", () => {
      expect(() => validarEstado({ ...ESTADO_PADRAO, revisao: -1 })).toThrow("revisao deve ser inteiro >= 0");
    });
  });

  describe("respeita VARD_CONFIG e VARD_DADOS", () => {
    it("usa caminhos das variáveis de ambiente", () => {
      gravarPaineis(PAINEIS_PADRAO);
      gravarEstado(ESTADO_PADRAO);
      expect(existsSync(join(configDir, "paineis.json"))).toBe(true);
      expect(existsSync(join(dadosDir, "paineis-estado.json"))).toBe(true);
    });
  });
});