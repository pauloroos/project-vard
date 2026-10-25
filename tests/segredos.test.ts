import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

import { invoke } from "@tauri-apps/api/core";
import { cofreExiste, cofreGravar, cofreApagar, cofreLer } from "../src/config/segredos";

const mockInvoke = vi.mocked(invoke);

describe("segredos (cofre generalizado)", () => {
  beforeEach(() => {
    mockInvoke.mockReset();
  });

  describe("cofreExiste", () => {
    it("retorna true quando o cofre confirma existência", async () => {
      mockInvoke.mockResolvedValue(true);
      const resultado = await cofreExiste("provedor", "suad");
      expect(resultado).toBe(true);
      expect(mockInvoke).toHaveBeenCalledWith("cofre_existe", { tipo: "provedor", id: "suad" });
    });

    it("retorna false quando o cofre diz que não existe", async () => {
      mockInvoke.mockResolvedValue(false);
      expect(await cofreExiste("voz", "kokoro-local")).toBe(false);
    });

    it("retorna false para tipo desconhecido sem chamar invoke", async () => {
      expect(await cofreExiste("agente", "claude")).toBe(false);
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("retorna false para id vazio sem chamar invoke", async () => {
      expect(await cofreExiste("provedor", "")).toBe(false);
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("retorna false para id com caractere inválido sem chamar invoke", async () => {
      expect(await cofreExiste("provedor", "com espaço")).toBe(false);
      expect(await cofreExiste("mcp", "com/barra")).toBe(false);
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("retorna false quando invoke falha", async () => {
      mockInvoke.mockRejectedValue(new Error("cofre indisponível"));
      expect(await cofreExiste("provedor", "x")).toBe(false);
    });
  });

  describe("cofreGravar", () => {
    it("chama invoke com tipo e id válidos", async () => {
      mockInvoke.mockResolvedValue(undefined);
      await cofreGravar("mcp", "filesystem", "token-secreto");
      expect(mockInvoke).toHaveBeenCalledWith("cofre_gravar", {
        tipo: "mcp",
        id: "filesystem",
        valor: "token-secreto",
      });
    });

    it("aceita o canal do Telegram (mesmo alvo vard:canal:telegram do núcleo)", async () => {
      mockInvoke.mockResolvedValue(undefined);
      await cofreGravar("canal", "telegram", "123:ficticio");
      expect(mockInvoke).toHaveBeenCalledWith("cofre_gravar", { tipo: "canal", id: "telegram", valor: "123:ficticio" });
    });

    it("recusa tipo desconhecido", async () => {
      await expect(cofreGravar("agente", "claude", "v")).rejects.toThrow("tipo de credencial desconhecido");
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("recusa id vazio", async () => {
      await expect(cofreGravar("provedor", "", "v")).rejects.toThrow("id deve ter");
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("recusa id longo", async () => {
      await expect(cofreGravar("provedor", "a".repeat(129), "v")).rejects.toThrow("id deve ter");
    });

    it("recusa id com caractere inválido", async () => {
      await expect(cofreGravar("provedor", "com espaço", "v")).rejects.toThrow("só aceita");
      await expect(cofreGravar("provedor", "com@arroba", "v")).rejects.toThrow("só aceita");
    });

    it("recusa valor vazio", async () => {
      await expect(cofreGravar("provedor", "x", "")).rejects.toThrow("valor deve ter");
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("recusa valor longo", async () => {
      await expect(cofreGravar("provedor", "x", "a".repeat(4097))).rejects.toThrow("valor deve ter");
    });

    it("recusa valor com caractere de controle", async () => {
      await expect(cofreGravar("provedor", "x", "teste\n")).rejects.toThrow("controle");
      await expect(cofreGravar("provedor", "x", "teste\0")).rejects.toThrow("controle");
    });

    it("aceita id com hífen, sublinhado e ponto", async () => {
      mockInvoke.mockResolvedValue(undefined);
      await cofreGravar("provedor", "meu-provedor_1.0", "valor");
      expect(mockInvoke).toHaveBeenCalled();
    });
  });

  describe("cofreApagar", () => {
    it("chama invoke com tipo e id válidos", async () => {
      mockInvoke.mockResolvedValue(undefined);
      await cofreApagar("voz", "elevenlabs");
      expect(mockInvoke).toHaveBeenCalledWith("cofre_apagar", { tipo: "voz", id: "elevenlabs" });
    });

    it("recusa tipo desconhecido", async () => {
      await expect(cofreApagar("desconhecido", "x")).rejects.toThrow("tipo de credencial desconhecido");
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("recusa id vazio", async () => {
      await expect(cofreApagar("provedor", "")).rejects.toThrow("id deve ter");
    });
  });

  describe("duas entradas isoladas", () => {
    it("grava e consulta alvos diferentes sem interferência", async () => {
      mockInvoke.mockResolvedValue(undefined);
      await cofreGravar("provedor", "a", "va");
      await cofreGravar("provedor", "b", "vb");
      expect(mockInvoke).toHaveBeenCalledTimes(2);
      expect(mockInvoke).toHaveBeenNthCalledWith(1, "cofre_gravar", { tipo: "provedor", id: "a", valor: "va" });
      expect(mockInvoke).toHaveBeenNthCalledWith(2, "cofre_gravar", { tipo: "provedor", id: "b", valor: "vb" });
    });
  });

  describe("cofreLer", () => {
    it("retorna valor quando credencial existe", async () => {
      mockInvoke.mockResolvedValue("chave-secreta");
      const resultado = await cofreLer("provedor", "suad");
      expect(resultado).toBe("chave-secreta");
      expect(mockInvoke).toHaveBeenCalledWith("cofre_ler", { tipo: "provedor", id: "suad" });
    });

    it("retorna null quando credencial não existe", async () => {
      mockInvoke.mockResolvedValue(null);
      expect(await cofreLer("provedor", "inexistente")).toBeNull();
    });

    it("retorna null para tipo desconhecido sem chamar invoke", async () => {
      expect(await cofreLer("agente", "claude")).toBeNull();
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("retorna null para id vazio sem chamar invoke", async () => {
      expect(await cofreLer("provedor", "")).toBeNull();
      expect(mockInvoke).not.toHaveBeenCalled();
    });

    it("retorna null quando invoke falha", async () => {
      mockInvoke.mockRejectedValue(new Error("cofre indisponível"));
      expect(await cofreLer("provedor", "x")).toBeNull();
    });
  });
});