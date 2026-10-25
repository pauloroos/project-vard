/** @vitest-environment jsdom */
import { describe, it, expect, vi } from "vitest";
import { CicloVoz } from "../src/fala/ciclo-voz";

describe("FR-004: CicloVoz e cancelamento de transcrição", () => {
  it("interromper cancela transcrição em andamento e invalida resultados tardios", async () => {
    let abortado = false;
    let resolverTransicao: ((texto: string) => void) | null = null;
    const transcrever = vi.fn(
      (_wav: ArrayBuffer, sinal?: AbortSignal) =>
        new Promise<string>((resolve, reject) => {
          resolverTransicao = resolve;
          sinal?.addEventListener("abort", () => {
            abortado = true;
            reject(new Error("abortado"));
          });
        })
    );
    const aoTexto = vi.fn();
    const aoMudarOcupado = vi.fn();
    const cicloVoz = new CicloVoz({
      transcrever,
      aoTexto,
      aoMudarOcupado,
    });

    // Inicia execução de um ciclo com wav dummy
    const wav = new ArrayBuffer(100);
    const promessa = cicloVoz.executar(wav, false);

    expect(cicloVoz.ocupado).toBe(true);
    expect(aoMudarOcupado).toHaveBeenCalledWith(true);
    expect(transcrever).toHaveBeenCalled();

    // Interrompe enquanto transcrevendo
    cicloVoz.interromper();

    expect(cicloVoz.ocupado).toBe(false);
    expect(abortado).toBe(true);

    // Se a transcrição eventualmente tentar resolver tardiamente
    if (resolverTransicao) {
      (resolverTransicao as (texto: string) => void)("texto tardio");
    }

    await promessa;

    // Resultado tardio deve ser invalidado/descartado
    expect(aoTexto).not.toHaveBeenCalled();
    expect(cicloVoz.ocupado).toBe(false);
  });

  it("interromper limpa push-to-talk pendente e libera ocupado", () => {
    const cicloVoz = new CicloVoz({
      transcrever: vi.fn(),
      aoTexto: vi.fn(),
    });

    cicloVoz.setPttPendente(true);
    expect(cicloVoz.pttPendente).toBe(true);

    cicloVoz.interromper();

    expect(cicloVoz.pttPendente).toBe(false);
    expect(cicloVoz.ocupado).toBe(false);
  });

  it("chama aoInterromperExterno ao interromper", () => {
    const aoInterromperExterno = vi.fn();
    const cicloVoz = new CicloVoz({
      transcrever: vi.fn(),
      aoTexto: vi.fn(),
      aoInterromper: aoInterromperExterno,
    });

    cicloVoz.interromper();

    expect(aoInterromperExterno).toHaveBeenCalled();
  });
});
