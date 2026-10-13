import { defineConfig } from "vite";
// @ts-expect-error type error without @types/node package
import process from "node:process";
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(() => ({
  // Três páginas: o widget, o painel de configurações e a sala (Tarefa 5).
  build: {
    rollupOptions: {
      input: { hud: "index.html", configuracoes: "configuracoes.html" },
    },
  },


  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    // So no `tauri dev`: o CORS do OpenJarvis recusa a origem localhost:1420, entao o front fala por /oj.
    proxy: {
      "/oj": {
        target: process.env.VITE_OJ_ALVO || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (caminho: string) => caminho.replace(/^\/oj/, ""),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        configure: (proxy: any) => { proxy.on("proxyReq", (req: any) => req.removeHeader("origin")); },
      },
    },
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
