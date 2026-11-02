import { beforeEach, describe, expect, it, vi } from "vitest";
import { Nucleo } from "../src/ui/nucleo";

describe("Cadência e visibilidade do Núcleo", () => {
  beforeEach(() => {
    vi.stubGlobal("Path2D", class { moveTo() {} lineTo() {} arc() {} });
    vi.stubGlobal("requestAnimationFrame", vi.fn());
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  function criarNucleo() {
    const gradiente = { addColorStop: vi.fn() };
    const ctx = new Proxy({ createRadialGradient: () => gradiente }, {
      get: (alvo, chave) => chave in alvo ? alvo[chave as keyof typeof alvo] : vi.fn(),
    });
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
    return new Nucleo(canvas);
  }

  it("iniciar agenda requestAnimationFrame quando visível", () => {
    const nucleo = criarNucleo();
    nucleo.iniciar();
    expect(requestAnimationFrame).toHaveBeenCalled();
  });

  it("quando oculto, parar é chamado e laço não roda", () => {
    const nucleo = criarNucleo();
    nucleo.iniciar();
    vi.mocked(requestAnimationFrame).mockClear();

    nucleo.definirOculto(true);
    expect(cancelAnimationFrame).toHaveBeenCalled();

    // Mudar de estado enquanto oculto não deve religar o laço
    nucleo.setEstado("ouvindo");
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    nucleo.setEstado("falando");
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    // Ao voltar a ficar visível, retoma o laço
    nucleo.definirOculto(false);
    expect(requestAnimationFrame).toHaveBeenCalled();
  });

  it("em jogo, voltar a ficar visível desenha quadro estático sem ligar animação contínua", () => {
    const nucleo = criarNucleo();
    const desenharSpy = vi.spyOn(nucleo as unknown as { desenhar: (t: number) => void }, "desenhar");
    nucleo.iniciar();
    nucleo.setEstado("jogo");
    nucleo.definirOculto(true);
    vi.mocked(requestAnimationFrame).mockClear();
    desenharSpy.mockClear();

    nucleo.definirOculto(false);
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(desenharSpy).toHaveBeenCalledTimes(1);
  });

  it("movimento reduzido pode ser ativado e desativado", () => {
    const nucleo = criarNucleo();
    nucleo.definirMovimentoReduzido(true);
    nucleo.iniciar();
    // Primeiro quadro desenha com movimento reduzido
    const quadro1 = vi.mocked(requestAnimationFrame).mock.calls.slice(-1)[0][0];
    expect(() => quadro1(100)).not.toThrow();

    // Desativa movimento reduzido e verifica próximo quadro no caminho de desenho
    nucleo.definirMovimentoReduzido(false);
    const quadro2 = vi.mocked(requestAnimationFrame).mock.calls.slice(-1)[0][0];
    expect(() => quadro2(200)).not.toThrow();
  });
});
