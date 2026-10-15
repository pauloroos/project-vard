import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Fakes instalados ANTES de importar o módulo sob teste, para que o import veja o stub.
let gumMock: ReturnType<typeof vi.fn>;
let streamFake: MediaStream;
let audioCtxFake: Record<string, unknown>;
let AudioWorkletNodeCtor: ReturnType<typeof vi.fn>;
let warnSpy: ReturnType<typeof vi.spyOn>;

function instalarFakes() {
  gumMock = vi.fn();
  streamFake = {
    getAudioTracks: () => [{ enabled: true }],
    getTracks: () => [{ stop: vi.fn() }],
  } as unknown as MediaStream;
  gumMock.mockResolvedValue(streamFake);

  const md = {
    getUserMedia: gumMock,
    enumerateDevices: async () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
    ondevicechange: null,
  } as unknown as MediaDevices;
  Object.defineProperty(globalThis.navigator, "mediaDevices", {
    configurable: true,
    value: md,
  });

  const gain = { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() };
  const analyser = {
    fftSize: 256,
    smoothingTimeConstant: 0.8,
    connect: vi.fn(),
    getFloatTimeDomainData: vi.fn(),
  };
  const source = { connect: vi.fn(), disconnect: vi.fn() };
  const workletNode = {
    port: { onmessage: null, postMessage: vi.fn() },
    connect: vi.fn(),
    disconnect: vi.fn(),
  };
  const scriptProcessor = {
    onaudioprocess: null as ((e: unknown) => void) | null,
    connect: vi.fn(),
    disconnect: vi.fn(),
  };

  audioCtxFake = {
    state: "running",
    sampleRate: 48000,
    destination: {},
    createGain: () => gain,
    createAnalyser: () => analyser,
    createMediaStreamSource: () => source,
    audioWorklet: { addModule: vi.fn().mockResolvedValue(undefined) },
    createScriptProcessor: vi.fn(() => scriptProcessor),
    close: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
  };
  AudioWorkletNodeCtor = vi.fn(() => workletNode);

  vi.stubGlobal("AudioContext", function () {
    return audioCtxFake;
  });
  vi.stubGlobal("AudioWorkletNode", AudioWorkletNodeCtor);
}

// Spy em console.warn ANTES de qualquer import, para capturar avisos do módulo.
warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

instalarFakes();

// Import dinâmico DEPOIS dos fakes instalados; resetModules garante instância fresca por teste.
async function carregarMicrofone() {
  vi.resetModules();
  instalarFakes();
  return await import("../src/audio/microfone");
}

describe("microfone com preferencia de deviceId", () => {
  let mic: Awaited<ReturnType<typeof carregarMicrofone>>;

  beforeEach(async () => {
    warnSpy.mockClear();
    mic = await carregarMicrofone();
    mic.definirMicrofonePreferido("");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  afterAll(() => {
    warnSpy.mockRestore();
  });

  it("usa deviceId exato quando definido", async () => {
    mic.definirMicrofonePreferido("mic-xyz");
    await mic.abrirMicrofone();
    expect(gumMock).toHaveBeenCalledWith(
      expect.objectContaining({
        audio: expect.objectContaining({ deviceId: { exact: "mic-xyz" } }),
      }),
    );
  });

  it("nao passa deviceId quando preferencia vazia", async () => {
    await mic.abrirMicrofone();
    expect(gumMock).toHaveBeenCalledTimes(1);
    const call = gumMock.mock.calls[0][0] as MediaStreamConstraints;
    const audio = call.audio as MediaTrackConstraints;
    expect(audio.deviceId).toBeUndefined();
  });

  it("cai no padrao e preserva preferencia quando dispositivo some", async () => {
    mic.definirMicrofonePreferido("mic-sumiu");
    const notFound = new DOMException("gone", "NotFoundError");
    gumMock.mockRejectedValueOnce(notFound).mockResolvedValueOnce(streamFake);

    await mic.abrirMicrofone();

    expect(gumMock).toHaveBeenCalledTimes(2);
    const fallbackCall = gumMock.mock.calls[1][0] as MediaStreamConstraints;
    const audio = fallbackCall.audio as MediaTrackConstraints;
    expect(audio.deviceId).toBeUndefined();
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Microfone preferido "mic-sumiu"'),
    );
  });
});