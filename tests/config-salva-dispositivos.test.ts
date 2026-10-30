import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";
import type { Estado } from "../src/fala/conversa";

const fakes = vi.hoisted(() => ({
  definirMicrofonePreferido: vi.fn(),
  aplicarSaidaNoContexto: vi.fn(),
  microfoneAberto: vi.fn(() => false),
  restaurarPreferencia: vi.fn(),
}));

vi.mock("../src/audio/microfone", async (original) => ({
  ...(await original<typeof import("../src/audio/microfone")>()),
  definirMicrofonePreferido: fakes.definirMicrofonePreferido,
  microfoneAberto: fakes.microfoneAberto,
}));

vi.mock("../src/audio/boca", async (original) => ({
  ...(await original<typeof import("../src/audio/boca")>()),
  aplicarSaidaNoContexto: fakes.aplicarSaidaNoContexto,
}));

import { aplicarDispositivosSalvos } from "../src/main";

const CONTEXTO = {} as AudioContext;
const AVISO_REINICIE_DISPOSITIVO = "Reinicie para aplicar o dispositivo";
const AVISO_REINICIE_MIC = "Reinicie para aplicar o microfone";

describe("config-salva troca de dispositivo", () => {
  let avisar: Mock<(estado: Estado, detalhe: string) => void>;
  let erro: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    fakes.aplicarSaidaNoContexto.mockResolvedValue(true);
    fakes.microfoneAberto.mockReturnValue(false);
    avisar = vi.fn<(estado: Estado, detalhe: string) => void>();
    erro = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("troca de microfone com captura aberta -> espera aviso de reinicio", async () => {
    fakes.microfoneAberto.mockReturnValue(true);
    await aplicarDispositivosSalvos({ microfone_id: "mic-novo", saida_id: "" }, { microfone: true, saida: false }, CONTEXTO, avisar);

    expect(fakes.definirMicrofonePreferido).toHaveBeenCalledWith("mic-novo");
    expect(avisar).toHaveBeenCalledWith("erro", "Reinicie para aplicar o microfone");
  });

  it("troca de microfone com captura fechada -> define preferencia sem aviso", async () => {
    fakes.microfoneAberto.mockReturnValue(false);
    await aplicarDispositivosSalvos({ microfone_id: "mic-novo2", saida_id: "" }, { microfone: true, saida: false }, CONTEXTO, avisar);

    expect(fakes.definirMicrofonePreferido).toHaveBeenCalledWith("mic-novo2");
    expect(avisar).not.toHaveBeenCalled();
  });

  it("troca de saida para dispositivo especifico -> aplica no contexto", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-nova" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(fakes.aplicarSaidaNoContexto).toHaveBeenCalledWith(CONTEXTO);
    expect(avisar).not.toHaveBeenCalled();
  });

  it("troca de saida para padrao ('') -> aplica setSinkId('') no contexto", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(fakes.aplicarSaidaNoContexto).toHaveBeenCalledWith(CONTEXTO);
    expect(avisar).not.toHaveBeenCalled();
  });

  it("falha de setSinkId -> estado de erro visivel", async () => {
    fakes.aplicarSaidaNoContexto.mockResolvedValue(false);

    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-ruim" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(avisar).toHaveBeenCalledWith("erro", AVISO_REINICIE_DISPOSITIVO);
    expect(erro).toHaveBeenCalled();
  });
});
