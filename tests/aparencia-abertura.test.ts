import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CONFIG_PADRAO } from "../src/config/config";

const { definirCor, carregar, pararAbertura } = vi.hoisted(() => ({
  definirCor: vi.fn(), carregar: vi.fn(), pararAbertura: new Error("fim da prova de abertura"),
}));
vi.mock("../src/config/config", async (original) => ({ ...await original<object>(), carregarConfig: carregar }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => false) }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ onMoved: vi.fn() }) }));
vi.mock("../src/ui/nucleo", () => ({ Nucleo: class {
  definirCor = definirCor;
  redimensionar() {}
  setAnalisadores() {}
  iniciar() { throw pararAbertura; }
} }));

beforeEach(() => {
  vi.resetModules();
  definirCor.mockClear();
  carregar.mockResolvedValue({ ...CONFIG_PADRAO, cor_elementos: "#ec4899", opacidade_elementos: 0.6 });
  document.body.innerHTML = '<div id="app"><canvas id="nucleo"></canvas></div>';
  document.documentElement.removeAttribute("style");
});
afterEach(() => vi.restoreAllMocks());

it.each(["widget", "sala"])("aplica a aparência salva antes do primeiro quadro do %s", async (janela) => {
  let abrir!: () => Promise<void>;
  vi.spyOn(window, "addEventListener").mockImplementation((tipo, acao) => {
    if (tipo === "DOMContentLoaded") abrir = acao as () => Promise<void>;
  });
  if (janela === "widget") await import("../src/main");
  else await import("../src/sala-main");
  await expect(abrir()).rejects.toBe(pararAbertura);
  expect(definirCor).toHaveBeenCalledWith("#ec4899");
  expect(document.documentElement.style.getPropertyValue("--cor-elementos")).toBe("#ec4899");
  expect(document.documentElement.style.getPropertyValue("--opacidade-elementos")).toBe("0.6");
});
