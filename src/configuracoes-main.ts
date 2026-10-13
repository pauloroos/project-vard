/// <reference types="vite/client" />
import { invoke } from "@tauri-apps/api/core";
import { emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { URL_RELEASE } from "./atualizacao/release";
import { carregarConfig, lerTopoCompacto } from "./config/config";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Ponte } from "./conectores/ponte/cliente";
import { Configuracoes, type Aba } from "./ui/configuracoes";

const ABAS: Aba[] = ["geral", "voz", "atalhos", "modelos", "sistema", "reuniao", "avisos", "atualizacao"];

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  const painel = new Configuracoes(cfg, document.getElementById("painel") as HTMLElement, {
    // No `tauri dev` o OpenJarvis recusa a origem do Vite: o painel passa pelo mesmo proxy /oj do widget.
    criarOj: (url, modelo = "") => new OpenJarvis(import.meta.env.DEV ? `${location.origin}/oj` : url, modelo),
    statusPonte: (url) => new Ponte(url).status(),
    modoPonte: (url, verbo) => new Ponte(url).modo(verbo),
    ponte: (url) => new Ponte(url),
    aoSalvar: (c) => { void emitTo("hud", "config-salva", c).catch((erro) => console.warn("não avisei o widget", erro)); },
    fechar: () => { void getCurrentWindow().close(); },
    atualizacao: {
      // Só o build de desenvolvimento aceita outro endereço (harness); o instalado consulta sempre o GitHub oficial.
      url: import.meta.env.DEV ? (import.meta.env.VITE_RELEASE_URL ?? URL_RELEASE) : URL_RELEASE,
      buscar: (url) => invoke<string>("buscar_release", { url }),
      instalar: (s) => invoke<void>("instalar_atualizacao", { url: s.url, nome: s.nome, bytes: s.bytes, sha256: s.sha256 }),
      versao: () => invoke<string>("versao_do_app"),
    },
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
  // O widget clicou na bolinha de avisos: abre a aba pedida (chega mais de uma vez enquanto a janela carrega).
  await listen<unknown>("abrir-aba", (ev) => {
    if (typeof ev.payload !== "string" || !ABAS.includes(ev.payload as Aba)) return;
    painel.abrirAba(ev.payload as Aba);
  });
});
