/// <reference types="vite/client" />
import { listen } from "@tauri-apps/api/event";
import { carregarConfig } from "./config/config";
import { abrirMicrofone, definirMudo, estaMudo, onAmostras, rmsAtual, taxaAtual } from "./audio/microfone";
import { DetectorDeVoz } from "./audio/vad";
import { pcmParaWav, reamostrar } from "./audio/wav";
import { Boca } from "./audio/boca";
import { falaFixa } from "./audio/cache";
import { OpenJarvis } from "./api/openjarvis";
import { Conversa } from "./fala/conversa";
import { FALAS } from "./fala/falas";
import { Hud } from "./ui/hud";
import { Nucleo } from "./ui/nucleo";

const PRE_ROLL_MS = 300;
const MIN_FALA_MS = 300;

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
  const app = document.getElementById("app") as HTMLElement;
  const nucleo = new Nucleo(canvas);
  nucleo.iniciar();
  let interromperTudo = () => {};
  let alternarMicrofone: () => Promise<void> = async () => {};
  const hud = new Hud(cfg, app, {
    aoMudo: () => { void alternarMicrofone(); },
    aoInterromper: () => interromperTudo(),
  });
  hud.dica("clique para ligar o ouvido");

  if (import.meta.env.DEV && import.meta.env.VITE_PROVA) {
    // Só em desenvolvimento: força um estado visual com analisadores sintéticos (para capturas de tela).
    (await import("./prova")).ativarProva(String(import.meta.env.VITE_PROVA), nucleo, hud);
  }

  // No `tauri dev` a origem do webview (localhost:1420) é recusada pelo CORS do OpenJarvis; o Vite faz a ponte em /oj.
  const base = import.meta.env.DEV ? `${location.origin}/oj` : cfg.openjarvis_url;
  const oj = new OpenJarvis(base);

  // A boca só existe depois que o microfone abre (usa o mesmo AudioContext).
  let bocaReal: Boca | null = null;
  // Latência: do fim da fala do usuário até o começo da reprodução da resposta.
  let fimDaFala = 0;
  const boca = {
    get falando() { return bocaReal?.falando ?? false; },
    async tocar(wav: ArrayBuffer) {
      if (!bocaReal) return;
      if (fimDaFala) { hud.setLatencia(performance.now() - fimDaFala); fimDaFala = 0; }
      await bocaReal.tocar(wav);
    },
    parar() { bocaReal?.parar(); },
  };

  // Captura: anel com os últimos ~300 ms (pre-roll) + acúmulo da fala.
  let anel: Float32Array[] = [];
  let anelAmostras = 0;
  let pcm: Float32Array[] = [];
  let capturando = false;
  let pttSegurado = false;
  let ocupado = false; // transcrevendo ou pensando: ignora novos eventos do VAD
  let estavaFalando = false;

  const fixa = (t: string) => falaFixa(t, cfg.voz, () => oj.sintetizar(t, cfg.voz, cfg.velocidade));

  const conversa = new Conversa({
    oj, boca, config: cfg,
    falas: fixa,
    aoEstado: (e, detalhe) => {
      nucleo.setEstado(e); hud.setEstado(e, detalhe);
      // Terminou de falar: descarta o pre-roll, que teria a cauda da própria voz (eco).
      if (estavaFalando && e !== "falando") { anel = []; anelAmostras = 0; }
      estavaFalando = e === "falando";
    },
    aoResposta: (t) => hud.setResposta(t),
  });

  // Saúde do OpenJarvis a cada 5 s; na primeira vez com fala no ar, aquece o cache das falas fixas.
  let aquecido = false;
  const checarSaude = async () => {
    const ok = await oj.saude();
    const falaOk = ok && (await oj.fala());
    await conversa.aoHealth(ok, falaOk);
    if (falaOk && !aquecido) {
      aquecido = true;
      for (const t of [FALAS.saudacao, FALAS.erroModelo, FALAS.erroOuvido, FALAS.openjarvisFora, FALAS.voltei]) {
        fixa(t).catch(() => { aquecido = false; });
      }
    }
  };
  void checarSaude();
  setInterval(() => { void checarSaude(); }, 5000);

  interromperTudo = () => conversa.interromper();
  const detector = new DetectorDeVoz({ limiar: cfg.limiar_vad, inicioMs: 150, fimMs: cfg.finish_ms, tetoMs: 12000 });

  const guardarAmostras = (a: Float32Array) => {
    if (capturando) { pcm.push(a); return; }
    anel.push(a); anelAmostras += a.length;
    const maximo = (taxaAtual() * PRE_ROLL_MS) / 1000;
    while (anel.length > 1 && anelAmostras - anel[0].length >= maximo) anelAmostras -= anel.shift()!.length;
  };

  const comecarCaptura = () => {
    pcm = anel; anel = []; anelAmostras = 0; // o pre-roll vira o começo da fala
    capturando = true;
    nucleo.setEstado("ouvindo"); hud.setEstado("ouvindo");
  };

  const encerrar = async (pushToTalk: boolean) => {
    capturando = false;
    fimDaFala = performance.now();
    const total = pcm.reduce((s, b) => s + b.length, 0);
    const tudo = new Float32Array(total);
    let o = 0;
    for (const b of pcm) { tudo.set(b, o); o += b.length; }
    pcm = [];
    console.log("fala capturada", tudo.length, "amostras a", taxaAtual(), "Hz");
    if (tudo.length < (taxaAtual() * MIN_FALA_MS) / 1000 || conversa.estado === "fora" || conversa.estado === "erro") {
      nucleo.setEstado(conversa.estado); hud.setEstado(conversa.estado, conversa.detalhe);
      return;
    }
    ocupado = true;
    nucleo.setEstado("pensando"); hud.setEstado("pensando");
    try {
      const wav = pcmParaWav(reamostrar(tudo, taxaAtual(), 16000), 16000);
      let texto: string;
      try {
        texto = await oj.transcrever(wav, cfg.idioma);
      } catch (erro) {
        console.warn("transcrição falhou", erro);
        try { await boca.tocar(await fixa(FALAS.erroOuvido)); } catch { /* sem voz, fica só no HUD */ }
        return;
      }
      console.log("ouvi:", texto);
      if (texto) hud.setOuvido(texto);
      await conversa.aoTextoTranscrito(texto, pushToTalk);
    } catch (erro) {
      console.error("ciclo de fala falhou", erro);
    } finally {
      fimDaFala = 0;
      ocupado = false;
      detector.reset();
      nucleo.setEstado(conversa.estado); hud.setEstado(conversa.estado, conversa.detalhe);
    }
  };

  let ligado = false;
  // Botão Mudo e duplo clique no núcleo: a primeira vez abre o microfone; depois só muda o mudo.
  alternarMicrofone = async () => {
    if (ligado) { const novo = !estaMudo(); definirMudo(novo); hud.setMudo(novo); return; }
    try {
      const mic = await abrirMicrofone();
      if (ligado) return;
      ligado = true;
      hud.setMudo(false);
      bocaReal = new Boca(mic.contexto);
      hud.setTaxa(mic.contexto.sampleRate);
      hud.setEstado(conversa.estado, conversa.detalhe);
      nucleo.setAnalisadores(mic.analisador, bocaReal.analisador);
      onAmostras(guardarAmostras);
      setInterval(() => {
        if (boca.falando || ocupado || pttSegurado || estaMudo()) { detector.reset(); return; }
        const ev = detector.alimentar(rmsAtual(), performance.now());
        if (ev === "inicio") comecarCaptura();
        else if (ev === "fim" || ev === "teto") void encerrar(false);
      }, 50);
    } catch (erro) {
      console.error("falha ao abrir o microfone", erro);
      hud.dica(FALAS.microfoneBloqueado);
      nucleo.setEstado("erro");
    }
  };

  // Arrastar a janela inteira (data-tauri-drag-region) e duplo clique no núcleo: o Tauri trataria o duplo clique
  // numa região de arraste como "maximizar"; interceptamos antes dele (captura na window) e usamos como liga/desliga.
  window.addEventListener("mousedown", (ev) => {
    const alvo = ev.target as Element | null;
    if (ev.detail >= 2 && alvo && app.contains(alvo) && !alvo.closest("button")) {
      ev.stopImmediatePropagation(); ev.preventDefault();
      if (ev.detail === 2 && alvo === canvas) void alternarMicrofone();
    }
  }, true);

  await listen("ptt-inicio", () => {
    if (!ligado || ocupado || estaMudo()) return;
    if (boca.falando) conversa.interromper(); // apertar para falar corta a fala em curso
    pttSegurado = true;
    if (!capturando) comecarCaptura(); // se o VAD já estava capturando, segue acumulando o mesmo PCM
  });
  await listen("ptt-fim", () => {
    if (!pttSegurado) return;
    pttSegurado = false;
    if (capturando) void encerrar(true);
  });
  await listen("parar", () => { conversa.interromper(); });
});
