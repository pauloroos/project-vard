import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { it, expect } from "vitest";
import { assetsSilero } from "../scripts/vite-silero";
it("build inclui modelo, worklet e WASM locais do lockfile", () => {
  const arquivos: { fileName: string; source: unknown }[] = [];
  const plugin = assetsSilero();
  const gerar = plugin.generateBundle as Function;
  gerar.call({ emitFile: (a: { fileName: string; source: unknown }) => arquivos.push(a) });
  expect(arquivos.map(a => a.fileName)).toEqual(["vad/silero_vad_v5.onnx", "vad/vad.worklet.bundle.min.js", "vad/ort-wasm-simd-threaded.mjs", "vad/ort-wasm-simd-threaded.wasm"]);
  const hash = (dados: unknown) => createHash("sha256").update(dados as Uint8Array).digest("hex");
  expect(hash(arquivos[0].source)).toBe(hash(readFileSync("node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx")));
});
