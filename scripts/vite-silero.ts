import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Plugin } from "vite";

/** Serve/empacota os mesmos assets fixados no lockfile, sem CDN em tempo de uso. */
export function assetsSilero(): Plugin {
  const arquivos = new Map([
    ["silero_vad_v5.onnx", "@ricky0123/vad-web/dist/silero_vad_v5.onnx"],
    ["vad.worklet.bundle.min.js", "@ricky0123/vad-web/dist/vad.worklet.bundle.min.js"],
    ["ort-wasm-simd-threaded.mjs", "onnxruntime-web/dist/ort-wasm-simd-threaded.mjs"],
    ["ort-wasm-simd-threaded.wasm", "onnxruntime-web/dist/ort-wasm-simd-threaded.wasm"],
  ]);
  const ler = (caminho: string) => readFileSync(resolve("node_modules", caminho));
  return {
    name: "assets-silero-locais",
    configureServer(servidor) {
      servidor.middlewares.use((req, res, next) => {
        const nome = req.url?.split("?")[0].replace(/^\/vad\//, "");
        const caminho = nome && arquivos.get(nome);
        if (!caminho || !req.url?.startsWith("/vad/")) { next(); return; }
        res.setHeader("Content-Type", nome.endsWith(".wasm") ? "application/wasm" : nome.endsWith(".onnx") ? "application/octet-stream" : "text/javascript");
        res.end(ler(caminho));
      });
    },
    generateBundle() {
      for (const [nome, caminho] of arquivos) this.emitFile({ type: "asset", fileName: `vad/${nome}`, source: ler(caminho) });
    },
  };
}
