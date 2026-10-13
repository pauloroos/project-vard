/// <reference types="vite/client" />
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { carregarConfig } from "./config/config";
import type { FalhaAtalho } from "./config/atalhos";
import { abrirMicrofone, definirMudo, fecharMicrofone, estaMudo, onAmostras, rmsAtual, taxaAtual } from "./audio/microfone";
import { DetectorDeVoz } from "./audio/vad";
import { pcmParaWav, reamostrar } from "./audio/wav";
import { Boca } from "./audio/boca";
import { falaFixa, type FonteDeFala } from "./audio/cache";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Ponte } from "./conectores/ponte/cliente";
import { Voz } from "./conectores/voz/cliente";
import { Conversa } from "./fala/conversa";
import { FALAS, saudacaoPara } from "./fala/falas";
import { Hud } from "./ui/hud";
import { Configuracoes } from "./ui/configuracoes";
import { Nucleo } from "./ui/nucleo";

const PRE_ROLL_MS = 300;
/** Prazo da voz própria numa fala fixa que não está no cache (o aquecimento usa o prazo normal). */
const PRAZO_FALA_FIXA_MS = 2000;
const MIN_FALA_MS = 300;

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig(); // nunca lança: arquivo ruim cai para o padrão
  const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
  const app = document.getElementById("app") as HTMLElement;
  const nucleo = new Nucleo(canvas);
  nucleo.iniciar();
  let interromperTudo = () => {};
  let alternarMicrofone: () => Promise<void> = async () => {};
  let olharTela = () => {};
  let abrirConfig = () => {};
  const hud = new Hud(cfg, app, {
    aoConfig: () => abrirConfig(),
    aoMudo: () => { void alternarMicrofone(); },
    aoInterromper: () => interromperTudo(),
    aoTela: () => olharTela(),
  });
  hud.dica("clique para ligar o ouvido");
  // Atalhos que o Windows recusou no arranque (outro programa já usa): avisa uma vez na linha de estado.
  try {
    const falhas = await invoke<FalhaAtalho[]>("falhas_de_atalho");
    if (falhas.length) hud.dica(`atalho ${falhas.map((f) => f.combinacao).join(", ")} não registrou; veja Configurações`);
  } catch { /* fora do Tauri */ }

  if (import.meta.env.DEV && import.meta.env.VITE_PROVA) {
    // Só em desenvolvimento: força um estado visual com analisadores sintéticos (para capturas de tela).
    (await import("./prova")).ativarProva(String(import.meta.env.VITE_PROVA), nucleo, hud);
  }

  // No `tauri dev` a origem do webview (localhost:1420) é recusada pelo CORS do OpenJarvis; o Vite faz a ponte em /oj.
  const base = import.meta.env.DEV ? `${location.origin}/oj` : cfg.openjarvis_url;
  const oj = new OpenJarvis(base);
  // Voz própria opcional (docs/voz-propria.md). Vazio desliga: a voz fica sempre a do OpenJarvis.
  const voz = cfg.voz_url.trim() ? new Voz(cfg.voz_url.trim()) : null;

  // Painel de configurações (bandeja ou engrenagem). Com click-through ligado a janela não receberia o clique:
  // ele é suspenso enquanto o painel está aberto.
  const aplicarClickThrough = (ligado: boolean) => { void invoke("definir_click_through", { ligado }).catch(() => {}); };
  const painel = new Configuracoes(cfg, document.getElementById("config") as HTMLElement, {
    criarOj: (url) => new OpenJarvis(import.meta.env.DEV ? `${location.origin}/oj` : url),
    aoSalvar: (c) => {
      void invoke("definir_sempre_no_topo", { ligado: c.sempre_no_topo }).catch(() => {});
      hud.atualizarTopo();
    },
    aoAlternar: (aberto) => { if (cfg.click_through) aplicarClickThrough(!aberto); },
  });
  abrirConfig = () => { void painel.abrir(); };
  if (cfg.click_through) aplicarClickThrough(true);

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
    async tocarFluxo(corpo: ReadableStream<Uint8Array>, taxa: number, sinal?: AbortSignal) {
      if (!bocaReal) { await corpo.cancel().catch(() => {}); return; }
      if (fimDaFala) { hud.setLatencia(performance.now() - fimDaFala); fimDaFala = 0; }
      await bocaReal.tocarFluxo(corpo, taxa, sinal);
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
  let pttPendente = false; // push-to-talk apertado durante a resposta: começa a capturar quando o ciclo terminar
  let estavaFalando = false;

  // Ponte opcional do Vard: sem ela o HUD funciona igual, só sem o botão Tela e sem modo jogo.
  const ponte = new Ponte(cfg.ponte_url);
  let ponteNoAr = true; // desconhecida até a 1ª sondagem (já disparada abaixo): tenta a ponte em vez de dizer que não há
  const espera = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  // Falas fixas: a voz própria primeiro (o cache guarda o WAV dela), o OpenJarvis como reserva.
  const fixa = async (t: string, rapido = true) => {
    const fontes: FonteDeFala[] = [];
    if (voz && (voz.nome || (await voz.saude(), voz.nome))) {
      // Prazo curto: uma voz pendurada não segura "Oi." por 8 s antes da reserva. O aquecimento, que não tem pressa, usa o prazo normal.
      fontes.push({ origem: "voz", voz: voz.nome, sintetizar: () => voz.falarWav(t, cfg.velocidade, rapido ? PRAZO_FALA_FIXA_MS : undefined) });
    }
    fontes.push({ origem: "oj", voz: cfg.voz, sintetizar: () => oj.sintetizar(t, cfg.voz, cfg.velocidade) });
    return falaFixa(t, fontes);
  };

  const conversa = new Conversa({
    oj, boca, config: cfg,
    ...(voz ? { voz } : {}),
    falas: fixa,
    aoEstado: (e, detalhe) => {
      nucleo.setEstado(e); hud.setEstado(e, detalhe);
      // Terminou de falar: descarta o pre-roll, que teria a cauda da própria voz (eco).
      if (estavaFalando && e !== "falando") { anel = []; anelAmostras = 0; }
      estavaFalando = e === "falando";
    },
    aoResposta: (t) => hud.setResposta(t),
    ponte, ponteNoAr: () => ponteNoAr,
    // Indicador vermelho por ~1 s antes de capturar; a captura é direta (sem compartilhamento).
    antesDaCaptura: async () => { hud.setIndicadorTela(true); await espera(1000); },
    depoisDaCaptura: () => hud.setIndicadorTela(false),
    capturar: async () => {
      try { return await invoke<string>("capturar_tela"); } finally { hud.setIndicadorTela(false); }
    },
    abrirMicrofone: () => abrirSeFechado(),
    fecharMicrofone: () => fecharTudoDoMicrofone(),
  });
  olharTela = () => { void conversa.aoTextoTranscrito("olha a tela", true); };

  // Status da ponte a cada 10 s: mostra/esconde o botão Tela e acompanha o modo jogo. Nunca trava a conversa.
  const sondarPonte = async () => {
    const st = await ponte.status();
    ponteNoAr = st !== null;
    hud.setPonte(ponteNoAr);
    try { await conversa.aoStatusPonte(st); } catch (erro) { console.warn("status da ponte falhou", erro); }
  };
  void sondarPonte();
  setInterval(() => { void sondarPonte(); }, 10000);

  // Saúde do OpenJarvis (e da voz própria) a cada 5 s; com a fala no ar, aquece o cache das falas fixas.
  // A voz própria fora não muda nada na tela: a reserva entra sozinha. Quando ela fica pronta, aquece de novo na voz dela.
  let aquecido = false;
  let aquecidoNaVoz = false;
  let vozPronta: boolean | null = null;
  let aquecendo: Promise<void> | null = null; // um aquecimento por vez: dois laços sintetizariam as mesmas falas duas vezes
  const aquecer = (): Promise<void> => {
    aquecendo ??= aquecerFalas().finally(() => { aquecendo = null; });
    return aquecendo;
  };
  const aquecerFalas = async () => {
    for (const t of [saudacaoPara(cfg.usuario), FALAS.erroModelo, FALAS.erroOuvido, FALAS.openjarvisFora, FALAS.voltei, FALAS.modoJogoAtivado]) {
      try { await fixa(t, false); } catch { aquecido = false; } // uma de cada vez: não disputa a GPU com a conversa
    }
  };
  const checarSaude = async () => {
    const ok = await oj.saude();
    const falaOk = ok && (await oj.fala());
    await conversa.aoHealth(ok, falaOk);
    if (voz) {
      const pronta = await voz.saude();
      if (pronta !== vozPronta) console.info(pronta ? `voz própria pronta (${voz.nome})` : "voz própria fora ou aquecendo; uso a reserva");
      vozPronta = pronta;
    }
    const novaVoz = vozPronta === true && !aquecidoNaVoz;
    if ((falaOk && !aquecido) || novaVoz) {
      aquecido = aquecido || falaOk;
      aquecidoNaVoz = aquecidoNaVoz || vozPronta === true;
      void aquecer();
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
      if (pttPendente && pttSegurado && ligado && !capturando) comecarCaptura();
      pttPendente = false;
    }
  };

  let ligado = false;
  let relogioVad = 0;
  let largarAmostras: (() => void) | null = null;
  // Modo jogo: solta o microfone de verdade (a GPU e o ouvido ficam livres); alternarMicrofone reabre sozinho depois.
  const fecharTudoDoMicrofone = (): boolean => {
    if (!ligado) return false; // nunca foi aberto: a volta do jogo não abre sozinha
    clearInterval(relogioVad);
    largarAmostras?.(); largarAmostras = null;
    bocaReal?.parar(); bocaReal = null;
    nucleo.setAnalisadores(null, null);
    fecharMicrofone();
    ligado = false;
    capturando = false; pcm = []; anel = []; anelAmostras = 0; pttSegurado = false;
    detector.reset();
    hud.setMudo(true);
    return true;
  };
  // Volta do modo jogo: abre se estiver fechado e não mexe no mudo se já estiver aberto.
  const abrirSeFechado = async () => { if (!ligado) await alternarMicrofone(); };
  // Botão Mudo e duplo clique no núcleo: a primeira vez abre o microfone; depois só muda o mudo.
  alternarMicrofone = async () => {
    if (ligado) { const novo = !estaMudo(); definirMudo(novo); hud.setMudo(novo); return; }
    try {
      const mic = await abrirMicrofone();
      if (ligado) return;
      ligado = true;
      definirMudo(false);
      hud.setMudo(false);
      bocaReal = new Boca(mic.contexto);
      hud.setTaxa(mic.contexto.sampleRate);
      hud.setEstado(conversa.estado, conversa.detalhe);
      nucleo.setAnalisadores(mic.analisador, bocaReal.analisador);
      largarAmostras = onAmostras(guardarAmostras);
      relogioVad = window.setInterval(() => {
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

  if (import.meta.env.DEV) {
    // Só em desenvolvimento: injeta uma pergunta como se tivesse vindo do microfone (mede a latência sem voz humana).
    // Com o microfone fechado, a boca ganha um AudioContext próprio (sem pedir permissão de microfone).
    (window as unknown as { __vardPergunta?: (t: string) => Promise<void> }).__vardPergunta = async (texto: string) => {
      if (!bocaReal) {
        bocaReal = new Boca(new AudioContext());
        nucleo.setAnalisadores(null, bocaReal.analisador);
      }
      ocupado = true;
      try {
        console.log("ouvi:", texto);
        hud.setOuvido(texto);
        await conversa.aoTextoTranscrito(texto, true);
      } finally {
        ocupado = false;
        detector.reset();
        nucleo.setEstado(conversa.estado); hud.setEstado(conversa.estado, conversa.detalhe);
      }
    };
  }

  await listen("ptt-inicio", () => {
    if (!ligado || estaMudo()) return;
    // Apertar para falar corta a resposta em curso (mesmo caminho do botão Interromper) e depois captura.
    const respondendo = boca.falando || ocupado;
    if (respondendo) conversa.interromper();
    pttSegurado = true;
    if (ocupado) { pttPendente = true; return; } // encerrar() inicia a captura no finally
    if (!capturando) comecarCaptura(); // se o VAD já estava capturando, segue acumulando o mesmo PCM
  });
  await listen("ptt-fim", () => {
    if (!pttSegurado) return;
    pttSegurado = false;
    pttPendente = false;
    if (capturando) void encerrar(true);
  });
  await listen("parar", () => { conversa.interromper(); });
  await listen("abrir-configuracoes", () => { void painel.abrir(); });
  await listen("alternar-escuta", () => { void alternarMicrofone(); });
  await listen("alternar-configuracoes", () => { if (painel.aberto()) painel.fechar(); else void painel.abrir(); });
  await listen<boolean>("sempre-no-topo", (ev) => { cfg.sempre_no_topo = ev.payload; hud.atualizarTopo(); });
});
