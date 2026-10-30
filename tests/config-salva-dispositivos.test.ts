import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { Mock } from "vitest";

/**
 * T005 — `config-salva` com dispositivo trocado no painel.
 *
 * O handler `aplicarConfigSalva` do main.ts precisa reaplicar microfone e saída no áudio vivo,
 * e mostrar estado de erro quando a saída escolhida não pôde ser aplicada (setSinkId falhou).
 */

const fakes = vi.hoisted(() => ({
  definirMicrofonePreferido: vi.fn(),
  aplicarSaidaNoContexto: vi.fn(),
}));

vi.mock("../src/audio/microfone", async (original) => ({
  ...(await original<typeof import("../src/audio/microfone")>()),
  definirMicrofonePreferido: fakes.definirMicrofonePreferido,
}));
vi.mock("../src/audio/boca", async (original) => ({
  ...(await original<typeof import("../src/audio/boca")>()),
  aplicarSaidaNoContexto: fakes.aplicarSaidaNoContexto,
}));

import { aplicarDispositivosSalvos } from "../src/main";
import type { Estado } from "../src/fala/conversa";

const CONTEXTO = {} as AudioContext;
const AVISO = "Reinicie para aplicar o dispositivo";

describe("config-salva troca de dispositivo", () => {
  let avisar: Mock<(estado: Estado, detalhe: string) => void>;
  let erro: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    fakes.aplicarSaidaNoContexto.mockResolvedValue(true);
    avisar = vi.fn<(estado: Estado, detalhe: string) => void>();
    erro = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => { erro.mockRestore(); });

  it("microfone_trocado_define_o_preferido", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "mic-novo", saida_id: "" }, { microfone: true, saida: false }, CONTEXTO, avisar);

    expect(fakes.definirMicrofonePreferido).toHaveBeenCalledWith("mic-novo");
    expect(avisar).not.toHaveBeenCalled();
  });

  it("saida_trocada_aplica_no_contexto_atual", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-nova" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(fakes.aplicarSaidaNoContexto).toHaveBeenCalledWith(CONTEXTO);
    expect(avisar).not.toHaveBeenCalled();
  });

  it("saida_recusada_pelo_sistema_mostra_estado_de_erro", async () => {
    fakes.aplicarSaidaNoContexto.mockResolvedValue(false);

    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-nova" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(avisar).toHaveBeenCalledWith("erro", AVISO);
    expect(erro).toHaveBeenCalled();
  });

  it("erro_ao_aplicar_saida_mostra_estado_de_erro", async () => {
    fakes.aplicarSaidaNoContexto.mockRejectedValue(new Error("sem dispositivo"));

    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-nova" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(avisar).toHaveBeenCalledWith("erro", AVISO);
    expect(erro).toHaveBeenCalled();
  });

  it("saida_para_o_padrao_do_sistema_nao_avisa", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "" }, { microfone: false, saida: true }, CONTEXTO, avisar);

    expect(fakes.aplicarSaidaNoContexto).not.toHaveBeenCalled();
    expect(avisar).not.toHaveBeenCalled();
  });

  it("sem_microfone_aberto_a_saida_fica_para_a_proxima_captura", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "", saida_id: "saida-nova" }, { microfone: false, saida: true }, null, avisar);

    expect(fakes.aplicarSaidaNoContexto).not.toHaveBeenCalled();
    expect(avisar).not.toHaveBeenCalled();
  });

  it("sem_troca_de_dispositivo_nao_mexe_em_nada", async () => {
    await aplicarDispositivosSalvos({ microfone_id: "mic-antigo", saida_id: "saida-antiga" }, { microfone: false, saida: false }, CONTEXTO, avisar);

    expect(fakes.definirMicrofonePreferido).not.toHaveBeenCalled();
    expect(fakes.aplicarSaidaNoContexto).not.toHaveBeenCalled();
    expect(avisar).not.toHaveBeenCalled();
  });
});
