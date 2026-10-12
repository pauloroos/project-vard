/** Reamostragem linear simples (suficiente para voz). */
export function reamostrar(amostras: Float32Array, de: number, para: number): Float32Array {
  if (de === para) return amostras;
  const n = Math.floor((amostras.length * para) / de);
  const saida = new Float32Array(n);
  const passo = de / para;
  for (let i = 0; i < n; i++) {
    const pos = i * passo;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, amostras.length - 1);
    const f = pos - i0;
    saida[i] = amostras[i0] * (1 - f) + amostras[i1] * f;
  }
  return saida;
}

/** WAV PCM 16 bits mono com cabeçalho RIFF de 44 bytes. */
export function pcmParaWav(amostras: Float32Array, taxa: number): ArrayBuffer {
  const dados = amostras.length * 2;
  const buf = new ArrayBuffer(44 + dados);
  const v = new DataView(buf);
  cabecalhoWav(v, dados, taxa);
  for (let i = 0; i < amostras.length; i++) {
    const x = Math.max(-1, Math.min(1, amostras[i]));
    v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return buf;
}

function cabecalhoWav(v: DataView, bytesDeDados: number, taxa: number): void {
  const txt = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  txt(0, "RIFF"); v.setUint32(4, 36 + bytesDeDados, true); txt(8, "WAVE");
  txt(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, taxa, true); v.setUint32(28, taxa * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  txt(36, "data"); v.setUint32(40, bytesDeDados, true);
}

/**
 * PCM 16 bits little-endian (bytes crus de um fluxo) para Float32.
 * Um pedaço pode terminar no meio de uma amostra: o byte solto volta em `sobra` e entra na frente do próximo.
 */
export function pcm16ParaFloat(bytes: Uint8Array, sobra?: Uint8Array): { amostras: Float32Array; sobra: Uint8Array } {
  let dados = bytes;
  if (sobra && sobra.length) {
    dados = new Uint8Array(sobra.length + bytes.length);
    dados.set(sobra); dados.set(bytes, sobra.length);
  }
  const n = dados.length >> 1;
  const v = new DataView(dados.buffer, dados.byteOffset, n * 2);
  const amostras = new Float32Array(n);
  for (let i = 0; i < n; i++) amostras[i] = v.getInt16(i * 2, true) / 32768;
  return { amostras, sobra: dados.slice(n * 2) };
}

/** Envolve PCM 16 bits mono cru num WAV de 44 bytes de cabeçalho (o byte ímpar no fim, se houver, é descartado). */
export function pcm16ParaWav(pcm: Uint8Array, taxa: number): ArrayBuffer {
  const dados = pcm.length - (pcm.length % 2);
  const buf = new ArrayBuffer(44 + dados);
  cabecalhoWav(new DataView(buf), dados, taxa);
  new Uint8Array(buf, 44).set(pcm.subarray(0, dados));
  return buf;
}

/** Lê um fluxo de PCM 16 bits até o fim e devolve o WAV inteiro (para guardar no cache e tocar de novo). */
export async function fluxoParaWav(corpo: ReadableStream<Uint8Array>, taxa: number): Promise<ArrayBuffer> {
  const leitor = corpo.getReader();
  const pedacos: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    if (value?.length) { pedacos.push(value); total += value.length; }
  }
  const pcm = new Uint8Array(total);
  let o = 0;
  for (const p of pedacos) { pcm.set(p, o); o += p.length; }
  return pcm16ParaWav(pcm, taxa);
}
