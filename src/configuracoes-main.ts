/// <reference types="vite/client" />
import { invoke } from "@tauri-apps/api/core";
import { emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { URL_RELEASE } from "./atualizacao/release";
import { carregarConfig, lerNaoOuvirFalar, lerTopoCompacto, salvarConfig } from "./config/config";
import { deveMostrarAssistente } from "./config/primeiro-uso";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Ponte } from "./conectores/ponte/cliente";
import { Configuracoes, type Aba } from "./ui/configuracoes";
import { montarImportacaoComPonte, resumirHudAtual } from "./ui/primeiro-uso-importacao";
import { montarAssistentePrimeiroUso, type DepsPrimeiroUso } from "./ui/primeiro-uso";

const ABAS: Aba[] = ["geral", "voz", "atalhos", "modelos", "paineis-provedores", "paineis-vozes", "paineis-mcps", "paineis-agentes", "sistema", "reuniao", "avisos", "atualizacao"];

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
  // T7 (0.9): caixa de importação da instalação anterior, na aba Sistema, pela ponte do campo.
  const caixaImportacao = document.querySelector<HTMLElement>("#cfg-importacao");
  if (caixaImportacao) {
    const ponteDoCampo = () => new Ponte(document.querySelector<HTMLInputElement>("#cfg-ponte_url")?.value?.trim() ?? "");
    montarImportacaoComPonte(caixaImportacao, ponteDoCampo, () => cfg, async (c) => {
      Object.assign(cfg, resumirHudAtual(c));
      await salvarConfig(cfg);
    });
  }
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
  // O widget mudou "não ouvir"/"não falar" (HUD, atalho ou bandeja): o painel acompanha as duas caixas.
  await listen<unknown>("nao-ouvir-falar-mudou", (ev) => {
    const v = lerNaoOuvirFalar(ev.payload);
    if (!v) { console.warn("nao-ouvir-falar-mudou ignorado: payload inválido"); return; }
    painel.mudouNaoOuvirFalar(v);
  });
  // O widget clicou na bolinha de avisos: abre a aba pedida (chega mais de uma vez enquanto a janela carrega).
  await listen<unknown>("abrir-aba", (ev) => {
    if (typeof ev.payload !== "string" || !ABAS.includes(ev.payload as Aba)) return;
    painel.abrirAba(ev.payload as Aba);
  });

  // Assistente de primeiro uso: monta na própria janela de Configurações quando necessário.
  const containerPU = document.getElementById("primeiro-uso-container") as HTMLElement | null;
  let limparAssistente: (() => void) | null = null;
  const depsPU: DepsPrimeiroUso = {
    ponteUrl: cfg.ponte_url,
    salvarNome: async (nome, variantes) => {
      cfg.nome = nome;
      cfg.variantes = variantes;
      await salvarConfig(cfg);
    },
    audio: {
      config: cfg,
      transcrever: async (wav, sinal) => {
        const oj = new OpenJarvis(import.meta.env.DEV ? `${location.origin}/oj` : cfg.openjarvis_url, cfg.modelo);
        return oj.transcrever(wav, cfg.idioma, sinal);
      },
      suspenderEscuta: async () => {
        // Pede ao widget para silenciar o microfone enquanto o teste de áudio roda.
        await emitTo("main", "pedir-mudo").catch(() => {});
        return async () => {
          await emitTo("main", "restaurar-mudo").catch(() => {});
        };
      },
      salvar: async (resultado) => {
        cfg.microfone_id = resultado.microfone_id;
        cfg.saida_id = resultado.saida_id;
        await salvarConfig(cfg);
      },
    },
    cerebro: {},
  };
  const montarSeNecessario = async () => {
    if (!containerPU) return;
    limparAssistente?.();
    limparAssistente = null;
    const deve = await deveMostrarAssistente(cfg.ponte_url);
    if (!deve) {
      containerPU.hidden = true;
      return;
    }
    containerPU.hidden = false;
    limparAssistente = await montarAssistentePrimeiroUso(containerPU, depsPU);
  };
  await montarSeNecessario();

  // Botão "Configurar primeiro uso" agora reabre o assistente nesta janela (não emite para o widget).
  const btnPU = document.getElementById("cfg-primeiro-uso") as HTMLButtonElement | null;
  if (btnPU) {
    // Remove listeners antigos que emitiam para o widget (desenho do Configuracoes já adicionou um).
    const clone = btnPU.cloneNode(true) as HTMLButtonElement;
    btnPU.parentNode?.replaceChild(clone, btnPU);
    clone.addEventListener("click", () => { void montarSeNecessario(); });
  }

  // Se o widget pedir para reabrir o assistente, faz aqui.
  await listen("reabrir-primeiro-uso", () => { void montarSeNecessario(); });
});
