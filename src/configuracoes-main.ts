/// <reference types="vite/client" />
import { emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { carregarConfig, lerTopoCompacto } from "./config/config";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Ponte } from "./conectores/ponte/cliente";
import { Configuracoes } from "./ui/configuracoes";

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  const painel = new Configuracoes(cfg, document.getElementById("painel") as HTMLElement, {
    // No `tauri dev` o OpenJarvis recusa a origem do Vite: o painel passa pelo mesmo proxy /oj do widget.
    criarOj: (url, modelo = "") => new OpenJarvis(import.meta.env.DEV ? `${location.origin}/oj` : url, modelo),
    statusPonte: (url) => new Ponte(url).status(),
    modoPonte: (url, verbo) => new Ponte(url).modo(verbo),
    aoSalvar: (c) => { void emitTo("hud", "config-salva", c).catch((erro) => console.warn("não avisei o widget", erro)); },
    fechar: () => { void getCurrentWindow().close(); },
  });
  await painel.montar();
  await listen<unknown>("config-mudou-no-widget", (ev) => {
    const v = lerTopoCompacto(ev.payload);
    if (!v) { console.warn("config-mudou-no-widget ignorado: payload inválido"); return; }
    painel.mudouNoWidget(v);
  });
  await listen<unknown>("sempre-no-topo", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("sempre-no-topo ignorado: payload inválido"); return; }
    painel.mudouTopo(ev.payload);
  });
  await listen<unknown>("invisivel", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("invisivel ignorado: payload inválido"); return; }
    painel.mudouInvisivel(ev.payload);
  });
});
