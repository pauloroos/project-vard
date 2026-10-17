import { expect, it, vi } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
import casos from "./fixtures/ajustes/contrato.json";
import { validarDocumento } from "../src/config/ajustes";

it.each(casos)("contrato compartilhado $arquivo ($valido): $valor", (caso) => {
  if (caso.valido) expect(() => validarDocumento(caso.arquivo, caso.valor)).not.toThrow();
  else expect(() => validarDocumento(caso.arquivo, caso.valor)).toThrow();
});

it("validar perfil preserva dados de versões futuras", () => {
  expect(validarDocumento("perfil", { versao: 1, tom: "direto", futuro: 3 })).toMatchObject({ futuro: 3 });
});
