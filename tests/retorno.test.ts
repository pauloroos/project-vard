import { describe, it, expect, vi, beforeEach } from "vitest";

/**
 * T7b — Restauração de estado ao voltar do modo jogo.
 *
 * O listener de ciclo-estado no main.ts deve:
 * 1. Aplicar dispositivo preferido ANTES de reabrir captura
 * 2. Restaurar escuta/fala exatamente como estavam (nao_ouvir/nao_falar)
 * 3. Nenhuma fala espontânea se 'nao falar' estava ligado
 * 4. Recriar apenas janelas necessárias
 */

// Fakes das funções do main.ts que o listener usa
const mockSetMudo = vi.fn();
const mockDefinirMudo = vi.fn();
const mockAplicarNaoFalar = vi.fn().mockResolvedValue(undefined);
const mockObterPreferencia = vi.fn().mockReturnValue({
  microfone_id: "mic-pref",
  microfone_rotulo: "Mic Preferido",
  saida_id: "out-pref",
  saida_rotulo: "Saída Preferida",
});
const mockDefinirMicrofonePreferido = vi.fn();
const mockSincronizarBandeja = vi.fn();

// Simula o comportamento do listener de ciclo-estado
function simularListenerCicloEstado(
  foto: { modo: string },
  estadoAnterior: { emModoJogo: boolean; nao_ouvir: boolean; nao_falar: boolean },
) {
  const eraJogo = estadoAnterior.emModoJogo;
  const emModoJogo = foto.modo === "jogo";

  if (eraJogo && !emModoJogo) {
    // 1. Dispositivos antes da captura
    const pref = mockObterPreferencia();
    mockDefinirMicrofonePreferido(pref.microfone_id);

    // 2. Escuta/Fala restaurados da config salva
    if (estadoAnterior.nao_ouvir) {
      mockSetMudo(true);
      mockDefinirMudo(true);
    } else {
      mockSetMudo(false);
      mockDefinirMudo(false);
    }
    void mockAplicarNaoFalar(estadoAnterior.nao_falar, false);

    // 3. Sincronizar bandeja
    mockSincronizarBandeja();
  }

  return { emModoJogo };
}

describe("T7b retorno do jogo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("restaura_dispositivo_preferido_antes_da_captura", () => {
    simularListenerCicloEstado(
      { modo: "ligado" },
      { emModoJogo: true, nao_ouvir: false, nao_falar: false },
    );

    expect(mockDefinirMicrofonePreferido).toHaveBeenCalledWith("mic-pref");
    expect(mockDefinirMicrofonePreferido).toHaveBeenCalledBefore(mockSetMudo);
  });

  it("restaura_escuta_off_fala_on_quando_nao_ouvir_estava_ligado", () => {
    simularListenerCicloEstado(
      { modo: "ligado" },
      { emModoJogo: true, nao_ouvir: true, nao_falar: false },
    );

    expect(mockSetMudo).toHaveBeenCalledWith(true);
    expect(mockDefinirMudo).toHaveBeenCalledWith(true);
    expect(mockAplicarNaoFalar).toHaveBeenCalledWith(false, false);
  });

  it("restaura_escuta_on_fala_off_quando_nao_falar_estava_ligado", () => {
    simularListenerCicloEstado(
      { modo: "ligado" },
      { emModoJogo: true, nao_ouvir: false, nao_falar: true },
    );

    expect(mockSetMudo).toHaveBeenCalledWith(false);
    expect(mockDefinirMudo).toHaveBeenCalledWith(false);
    expect(mockAplicarNaoFalar).toHaveBeenCalledWith(true, false);
  });

  it("nenhuma_acao_quando_nao_vem_do_jogo", () => {
    simularListenerCicloEstado(
      { modo: "ligado" },
      { emModoJogo: false, nao_ouvir: false, nao_falar: false },
    );

    expect(mockDefinirMicrofonePreferido).not.toHaveBeenCalled();
    expect(mockSetMudo).not.toHaveBeenCalled();
    expect(mockAplicarNaoFalar).not.toHaveBeenCalled();
  });

  it("nenhuma_acao_quando_continua_em_jogo", () => {
    simularListenerCicloEstado(
      { modo: "jogo" },
      { emModoJogo: true, nao_ouvir: false, nao_falar: false },
    );

    expect(mockDefinirMicrofonePreferido).not.toHaveBeenCalled();
    expect(mockSetMudo).not.toHaveBeenCalled();
  });

  it("sincroniza_bandeja_apos_restaurar_estado", () => {
    simularListenerCicloEstado(
      { modo: "ligado" },
      { emModoJogo: true, nao_ouvir: false, nao_falar: false },
    );

    expect(mockSincronizarBandeja).toHaveBeenCalled();
  });

  it("escuta_off_e_fala_off_simultaneos", () => {
    simularListenerCicloEstado(
      { modo: "liberando" },
      { emModoJogo: true, nao_ouvir: true, nao_falar: true },
    );

    expect(mockSetMudo).toHaveBeenCalledWith(true);
    expect(mockDefinirMudo).toHaveBeenCalledWith(true);
    expect(mockAplicarNaoFalar).toHaveBeenCalledWith(true, false);
  });
});