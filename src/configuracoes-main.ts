/// <reference types="vite/client" />
import { emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { carregarConfig, type Config } from "./config/config";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Configuracoes } from "./ui/configuracoes";

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  const painel = new Configuracoes(cfg, document.getElementById("painel") as HTMLElement, {
    // No `tauri dev` o OpenJarvis recusa a origem do Vite: o painel passa pelo mesmo proxy /oj do widget.
    criarOj: (url) => new OpenJarvis(import.meta.env.DEV ? `${location.origin}/oj` : url),
    aoSalvar: (c) => { void emitTo("hud", "config-salva", c).catch((erro) => console.warn("não avisei o widget", erro)); },
    fechar: () => { void getCurrentWindow().close(); },
  });
  await painel.montar();
  await listen<Pick<Config, "sempre_no_topo" | "compacto">>("config-mudou-no-widget", (ev) => painel.mudouNoWidget(ev.payload));
});
