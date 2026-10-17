import { afterEach, expect, it, vi } from "vitest";
import { aplicarAparencia } from "../src/ui/aparencia";
import { Nucleo } from "../src/ui/nucleo";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("style");
});

it("aplicarAparencia passa a cor ao núcleo na abertura e após salvar", () => {
  vi.stubGlobal("Path2D", class { moveTo() {} lineTo() {} arc() {} });
  // O método real permanece ativo: o spy observa o limite entre aparência e desenho.
  const canvas = document.createElement("canvas");
  vi.spyOn(canvas, "getContext").mockReturnValue({ setTransform() {} } as unknown as CanvasRenderingContext2D);
  const nucleo = new Nucleo(canvas);
  const definirCor = vi.spyOn(nucleo, "definirCor");

  aplicarAparencia({ cor_elementos: "#1e3a5f", opacidade_elementos: 0.8 }, nucleo);
  expect(definirCor).toHaveBeenNthCalledWith(1, "#1e3a5f");
  expect(document.documentElement.style.getPropertyValue("--cor-elementos")).toBe("#1e3a5f");
  expect(document.documentElement.style.getPropertyValue("--opacidade-elementos")).toBe("0.8");

  aplicarAparencia({ cor_elementos: "#00f0ff", opacidade_elementos: 0.3 }, nucleo);
  expect(definirCor).toHaveBeenNthCalledWith(2, "#00f0ff");
  expect(document.documentElement.style.getPropertyValue("--cor-elementos")).toBe("#00f0ff");
  expect(document.documentElement.style.getPropertyValue("--opacidade-elementos")).toBe("0.3");

  aplicarAparencia({ cor_elementos: "", opacidade_elementos: 1 }, nucleo);
  expect(definirCor).toHaveBeenNthCalledWith(3, null);
  expect(document.documentElement.style.getPropertyValue("--cor-elementos")).toBe("var(--ciano)");
});
