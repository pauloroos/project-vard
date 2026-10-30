export interface Microfone {
  contexto: AudioContext;
  analisador: AnalyserNode;
  fonte: MediaStreamAudioSourceNode;
  stream: MediaStream;
}

type OuvinteAmostras = (amostras: Float32Array) => void;

let atual: Microfone | null = null;
let gravador: AudioWorkletNode | ScriptProcessorNode | null = null;
const ouvintes = new Set<OuvinteAmostras>();
let bufferRms: Float32Array<ArrayBuffer> | null = null;

const CODIGO_WORKLET = `
class Gravador extends AudioWorkletProcessor {
  process(entradas) {
    const c = entradas[0] && entradas[0][0];
    if (c) this.port.postMessage(c.slice(0));
    return true;
  }
}
registerProcessor("gravador", Gravador);
`;

/** Dá ao nó um caminho até o destino (ganho 0) para o Chromium continuar processando-o. */
function ligarMudo(m: Microfone, no: AudioNode): void {
  const mudo = m.contexto.createGain();
  mudo.gain.value = 0;
  no.connect(mudo);
  mudo.connect(m.contexto.destination);
}

async function ligarGravador(m: Microfone): Promise<void> {
  const emitir = (a: Float32Array) => { for (const cb of ouvintes) cb(a); };
  try {
    const url = URL.createObjectURL(new Blob([CODIGO_WORKLET], { type: "text/javascript" }));
    await m.contexto.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const no = new AudioWorkletNode(m.contexto, "gravador");
    no.port.onmessage = (e) => emitir(e.data as Float32Array);
    m.fonte.connect(no);
    ligarMudo(m, no);
    gravador = no;
  } catch (erro) {
    console.warn("AudioWorklet indisponível, usando ScriptProcessorNode", erro);
    const no = m.contexto.createScriptProcessor(4096, 1, 1);
    no.onaudioprocess = (e) => emitir(new Float32Array(e.inputBuffer.getChannelData(0)));
    m.fonte.connect(no);
    ligarMudo(m, no);
    gravador = no;
  }
}

let abrindo: Promise<Microfone> | null = null;

/** Abre o microfone uma só vez: chamadas simultâneas (duplo clique) dividem a mesma Promise. */
export function abrirMicrofone(): Promise<Microfone> {
  if (atual) return Promise.resolve(atual);
  abrindo ??= abrirDeVerdade().catch((e) => { abrindo = null; throw e; });
  return abrindo;
}

/** Define o deviceId preferido para a próxima abertura do microfone. "" = padrão do sistema. */
let microfonePreferidoId = "";
export function definirMicrofonePreferido(deviceId: string): void {
  microfonePreferidoId = deviceId;
}

async function abrirDeVerdade(): Promise<Microfone> {
  const audioConstraints: MediaTrackConstraints = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (microfonePreferidoId) {
    audioConstraints.deviceId = { exact: microfonePreferidoId };
  }
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
  } catch (erro) {
    // Dispositivo preferido indisponível: volta ao padrão sem apagar a preferência.
    if (microfonePreferidoId && erro instanceof DOMException && erro.name === "NotFoundError") {
      console.warn(`Microfone preferido "${microfonePreferidoId}" não encontrado; usando padrão.`);
      delete audioConstraints.deviceId;
      stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
    } else {
      throw erro;
    }
  }
  const contexto = new AudioContext();
  if (contexto.state === "suspended") await contexto.resume();
  const fonte = contexto.createMediaStreamSource(stream);
  const analisador = contexto.createAnalyser();
  analisador.fftSize = 256;
  analisador.smoothingTimeConstant = 0.8;
  fonte.connect(analisador);
  atual = { contexto, analisador, fonte, stream };
  if (mudoPedido) stream.getAudioTracks().forEach((t) => { t.enabled = false; });
  bufferRms = new Float32Array(analisador.fftSize);
  await ligarGravador(atual);
  return atual;
}

export function fecharMicrofone(): void {
  if (!atual) return;
  gravador?.disconnect();
  gravador = null;
  atual.stream.getTracks().forEach((t) => t.stop());
  void atual.contexto.close();
  atual = null;
  abrindo = null;
}

/** Assina os blocos de PCM (Float32, taxa do contexto). Retorna a função de cancelamento. */
export function onAmostras(cb: OuvinteAmostras): () => void {
  ouvintes.add(cb);
  return () => { ouvintes.delete(cb); };
}

export function taxaAtual(): number { return atual?.contexto.sampleRate ?? 48000; }

export function rmsAtual(): number {
  if (!atual || !bufferRms) return 0;
  atual.analisador.getFloatTimeDomainData(bufferRms);
  let soma = 0;
  for (let i = 0; i < bufferRms.length; i++) soma += bufferRms[i] * bufferRms[i];
  return Math.sqrt(soma / bufferRms.length);
}

let mudoPedido = false;

/** Mudo: desliga as faixas do microfone (o contexto e a boca continuam vivos). Vale também para um microfone aberto depois. */
export function definirMudo(mudo: boolean): void {
  mudoPedido = mudo;
  atual?.stream.getAudioTracks().forEach((t) => { t.enabled = !mudo; });
}

export function estaMudo(): boolean { return mudoPedido; }

/** Indica se o microfone está atualmente aberto. */
export function microfoneAberto(): boolean {
  return atual !== null;
}
