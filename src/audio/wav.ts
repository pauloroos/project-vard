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
  const txt = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  txt(0, "RIFF"); v.setUint32(4, 36 + dados, true); txt(8, "WAVE");
  txt(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, taxa, true); v.setUint32(28, taxa * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  txt(36, "data"); v.setUint32(40, dados, true);
  for (let i = 0; i < amostras.length; i++) {
    const x = Math.max(-1, Math.min(1, amostras[i]));
    v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return buf;
}
