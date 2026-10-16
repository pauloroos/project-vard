import { pcmParaWav, reamostrar } from "./wav";

/** Captura isolada: nunca altera a entrada do widget nem grava áudio em disco. */
export async function capturarTesteMicrofone(
  deviceId: string, sinal: AbortSignal, nivel: (rms: number) => void,
): Promise<{ wav: ArrayBuffer; pico: number }> {
  const interrompido = () => new DOMException("Teste cancelado", "AbortError");
  if (sinal.aborted) throw interrompido();
  const stream = await navigator.mediaDevices.getUserMedia({ audio: {
    echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  } });
  let contexto: AudioContext | undefined;
  let fonte: MediaStreamAudioSourceNode | undefined;
  let gravador: ScriptProcessorNode | undefined;
  let mudo: GainNode | undefined;
  let relogio: ReturnType<typeof setTimeout> | undefined;
  let abortar = () => {};
  let removido = () => {};
  try {
    if (sinal.aborted) throw interrompido();
    contexto = new AudioContext();
    if (contexto.state === "suspended") {
      await new Promise<void>((ok, falhar) => {
        const cancelarResume = () => falhar(interrompido());
        sinal.addEventListener("abort", cancelarResume, { once: true });
        void contexto!.resume().then(ok, falhar).finally(() => sinal.removeEventListener("abort", cancelarResume));
      });
    }
    if (sinal.aborted) throw interrompido();
    fonte = contexto.createMediaStreamSource(stream);
    gravador = contexto.createScriptProcessor(4096, 1, 1);
    mudo = contexto.createGain(); mudo.gain.value = 0;
    fonte.connect(gravador); gravador.connect(mudo); mudo.connect(contexto.destination);
    const blocos: Float32Array[] = [];
    const taxa = contexto.sampleRate;
    let total = 0, pico = 0;
    await new Promise<void>((ok, falhar) => {
      abortar = () => falhar(interrompido());
      removido = () => falhar(new DOMException("Microfone removido", "NotFoundError"));
      sinal.addEventListener("abort", abortar, { once: true });
      stream.getTracks().forEach((t) => t.addEventListener("ended", removido));
      relogio = setTimeout(ok, 5000);
      gravador!.onaudioprocess = (e) => {
        if (sinal.aborted) return;
        const entrada = e.inputBuffer.getChannelData(0);
        const bloco = entrada.slice(0, Math.max(0, taxa * 5 - total));
        if (!bloco.length) return;
        blocos.push(bloco); total += bloco.length;
        const rms = Math.sqrt(bloco.reduce((s, x) => s + x * x, 0) / bloco.length);
        pico = Math.max(pico, rms); nivel(rms);
        if (total >= taxa * 5) ok();
      };
    });
    const pcm = new Float32Array(total);
    let pos = 0; for (const bloco of blocos) { pcm.set(bloco, pos); pos += bloco.length; }
    return { wav: pcmParaWav(reamostrar(pcm, taxa, 16000), 16000), pico };
  } finally {
    clearTimeout(relogio); sinal.removeEventListener("abort", abortar);
    stream.getTracks().forEach((t) => { t.removeEventListener?.("ended", removido); t.stop(); });
    if (gravador) { gravador.onaudioprocess = null; gravador.disconnect(); }
    fonte?.disconnect(); mudo?.disconnect();
    await contexto?.close().catch(() => {});
  }
}
