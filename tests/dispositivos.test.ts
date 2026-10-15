import { describe, it, expect, beforeEach } from "vitest";
import {
  normalizarRotulo,
  resolverPreferencia,
  constraintsComMicrofone,
  obterPreferencia,
  definirPreferencia,
  restaurarPreferencia,
  preferenciaParaConfig,
  type DispositivoInfo,
} from "../src/audio/dispositivos";

describe("normalizarRotulo", () => {
  it("lowercase_trim_e_colapsa_espacos", () => {
    expect(normalizarRotulo("  Microfone  USB  ")).toBe("microfone usb");
  });
  it("vazia_retorna_vazia", () => {
    expect(normalizarRotulo("")).toBe("");
  });
});

describe("resolverPreferencia", () => {
  const dispositivos: DispositivoInfo[] = [
    { deviceId: "d1", label: "Microfone USB", kind: "audioinput" },
    { deviceId: "d2", label: "Fone Bluetooth", kind: "audiooutput" },
    { deviceId: "d3", label: "Microfone Webcam", kind: "audioinput" },
  ];

  it("sem_preferencia_retorna_padrao", () => {
    const r = resolverPreferencia("", "", dispositivos);
    expect(r.deviceId).toBe("");
    expect(r.aviso).toBeUndefined();
  });

  it("encontra_por_deviceId_exato", () => {
    const r = resolverPreferencia("d1", "Outro Nome", dispositivos);
    expect(r.deviceId).toBe("d1");
    expect(r.aviso).toBeUndefined();
  });

  it("fallback_por_rotulo_normalizado", () => {
    const r = resolverPreferencia("d-antigo", "microfone usb", dispositivos);
    expect(r.deviceId).toBe("d1");
  });

  it("ambiguo_retorna_padrao_com_aviso", () => {
    const dupl: DispositivoInfo[] = [
      { deviceId: "x1", label: "Mic Generico", kind: "audioinput" },
      { deviceId: "x2", label: "Mic Generico", kind: "audioinput" },
    ];
    const r = resolverPreferencia("", "mic generico", dupl);
    expect(r.deviceId).toBe("");
    expect(r.aviso).toContain("Ambíguo");
  });

  it("nao_encontrado_usa_padrao_com_aviso", () => {
    const r = resolverPreferencia("d-sumiu", "Mic Sumiu", dispositivos);
    expect(r.deviceId).toBe("");
    expect(r.aviso).toContain("não encontrado");
  });
});

describe("constraintsComMicrofone", () => {
  it("sem_microfone_id_retorna_base_inalterada", () => {
    const base = { audio: true };
    const r = constraintsComMicrofone(base, { microfone_id: "", microfone_rotulo: "", saida_id: "", saida_rotulo: "" });
    expect(r).toEqual(base);
  });

  it("com_microfone_id_adiciona_exact", () => {
    const r = constraintsComMicrofone(
      { audio: true },
      { microfone_id: "d1", microfone_rotulo: "Mic", saida_id: "", saida_rotulo: "" },
    );
    expect((r.audio as MediaTrackConstraints).deviceId).toEqual({ exact: "d1" });
  });

  it("preserva_constraints_existentes", () => {
    const r = constraintsComMicrofone(
      { audio: { echoCancellation: true } },
      { microfone_id: "d1", microfone_rotulo: "", saida_id: "", saida_rotulo: "" },
    );
    const a = r.audio as MediaTrackConstraints;
    expect(a.echoCancellation).toBe(true);
    expect(a.deviceId).toEqual({ exact: "d1" });
  });
});

describe("preferencia estado", () => {
  beforeEach(() => {
    restaurarPreferencia({});
  });

  it("obter_retorna_padrao_inicial", () => {
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("");
    expect(p.saida_id).toBe("");
  });

  it("definir_atualiza_estado", () => {
    // onDeviceChange não é testado aqui pois depende do navigator.mediaDevices real;
    // testamos apenas que definirPreferencia atualiza o estado.
    definirPreferencia({ microfone_id: "d1", microfone_rotulo: "Mic" });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("d1");
    expect(p.microfone_rotulo).toBe("Mic");
    // saida permanece padrão
    expect(p.saida_id).toBe("");
  });

  it("restaurar_sobrescreve_tudo", () => {
    definirPreferencia({ microfone_id: "d1" });
    restaurarPreferencia({ saida_id: "s1", saida_rotulo: "Fone" });
    const p = obterPreferencia();
    expect(p.microfone_id).toBe("");
    expect(p.saida_id).toBe("s1");
  });

  it("preferenciaParaConfig_retorna_copia", () => {
    definirPreferencia({ microfone_id: "d1" });
    const cfg = preferenciaParaConfig();
    cfg.microfone_id = "alterado";
    expect(obterPreferencia().microfone_id).toBe("d1");
  });
});