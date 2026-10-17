import { beforeEach, describe, expect, it, vi } from "vitest";
import { Nucleo, type Estado } from "../src/ui/nucleo";
import { Aneis } from "../src/ui/aneis";

describe("cor do holograma", () => {
  beforeEach(() => {
    vi.stubGlobal("Path2D", class { moveTo() {} lineTo() {} arc() {} });
    vi.stubGlobal("requestAnimationFrame", vi.fn());
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  function desenho() {
    const gradiente = { addColorStop: vi.fn() };
    const ctx = new Proxy({ createRadialGradient: () => gradiente }, {
      get: (alvo, chave) => chave in alvo ? alvo[chave as keyof typeof alvo] : vi.fn(),
    });
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
    return new Nucleo(canvas);
  }

  it.each<Estado>(["repouso", "ouvindo", "falando", "fora"])("pinta núcleo, brilho e anéis em %s", (estado) => {
    const nucleo = desenho();
    const aneis = vi.spyOn(Aneis.prototype, "desenhar");
    nucleo.definirCor("#ec4899");
    nucleo.setEstado(estado);
    nucleo.iniciar();
    // O primeiro quadro usa a cor escolhida antes da animação começar.
    const quadro = vi.mocked(requestAnimationFrame).mock.calls.slice(-1)[0][0];
    quadro(100);
    const estilo = aneis.mock.calls.slice(-1)[0][1];
    expect(estilo.cor).toBe("rgba(236,72,153,1)");
    expect(estilo.brilho).toBe("rgba(153,46,99,0.9)");
    nucleo.parar();
  });

  it.each(["", null, "invalida"])("restaura o ciano original com %s", (cor) => {
    const nucleo = desenho();
    const aneis = vi.spyOn(Aneis.prototype, "desenhar");
    nucleo.definirCor("#ec4899");
    nucleo.definirCor(cor);
    nucleo.iniciar();
    vi.mocked(requestAnimationFrame).mock.calls.slice(-1)[0][0](100);
    expect(aneis.mock.calls.slice(-1)[0][1]).toMatchObject({ cor: "rgba(0,240,255,1)", brilho: "rgba(0,162,255,0.9)" });
  });

  it.each(["pensando", "erro", "jogo"] as const)("preserva a cor de estado em %s", (estado) => {
    const nucleo = desenho();
    const aneis = vi.spyOn(Aneis.prototype, "desenhar");
    nucleo.definirCor("#ec4899");
    nucleo.setEstado(estado);
    nucleo.iniciar();
    if (estado !== "jogo") vi.mocked(requestAnimationFrame).mock.calls.slice(-1)[0][0](100);
    expect(aneis.mock.calls.slice(-1)[0][1].cor).toBe({ pensando: "rgba(255,153,0,1)", erro: "rgba(255,56,56,1)", jogo: "rgba(120,124,130,1)" }[estado]);
  });
});
