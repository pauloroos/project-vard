import type { CarregarSilero } from "./vad-selecionavel";
/** Importação tardia: energia não inicializa ONNX nem solicita outro microfone. */
export const carregarSilero: CarregarSilero = async (mic, quadro) => {
  const { MicVAD } = await import("@ricky0123/vad-web");
  const vad = await MicVAD.new({
    model: "v5", audioContext: mic.contexto, startOnLoad: false,
    getStream: async () => mic.stream,
    pauseStream: async () => {}, resumeStream: async () => mic.stream,
    baseAssetPath: "/vad/", onnxWASMBasePath: "/vad/",
    ortConfig: ort => { ort.env.wasm.numThreads = 1; ort.env.wasm.proxy = false; },
    onFrameProcessed: p => quadro(p.isSpeech),
  });
  try { await vad.start(); } catch (e) { await vad.destroy().catch(() => {}); throw e; }
  return { destruir: () => vad.destroy() };
};
