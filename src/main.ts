/// <reference types="vite/client" />
import { invoke } from "@tauri-apps/api/core";
import { emit, emitTo, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { aplicarAoVivo, aplicarVozAoVivo, atualizarConfig, carregarConfig, lerConfigAoVivo, normalizarConfig } from "./config/config";
import type { FalhaAtalho } from "./config/atalhos";
import { abrirMicrofone, definirMudo, fecharMicrofone, estaMudo, onAmostras, rmsAtual, taxaAtual, definirMicrofonePreferido } from "./audio/microfone";
import { DetectorSelecionavel, ControleCapturaVoz, pareceEco } from "./audio/vad-selecionavel";
import { carregarSilero } from "./audio/silero";
import { pcmParaWav, reamostrar } from "./audio/wav";
import { Boca, aplicarSaidaNoContexto } from "./audio/boca";
import { falaFixa, type FonteDeFala } from "./audio/cache";
import { OpenJarvis } from "./conectores/openjarvis/cliente";
import { Ponte } from "./conectores/ponte/cliente";
import { CentralAvisos } from "./avisos/central";
import { EmAndamento, textoDaDica as dicaDeAndamento } from "./avisos/andamento";
import { deveFalarAviso, AvisoPorVez } from "./avisos/fala";
import { criarFluxoChamada } from "./avisos/chamada";
import { EstadoReuniao } from "./reuniao/estado";
import { criarFonteDeVoz, type ProvedorVoz } from "./conectores/voz/escolher";
import type { FonteDeVoz } from "./conectores/voz/fonte";
import { Conversa, type Estado } from "./fala/conversa";
import { processarTextoOuvido } from "./fala/textoOuvido";
import { criarMaquinaConversaAberta, processamentoConcluido } from "./conversa/aberta";
import { FALAS, saudacaoPara } from "./fala/falas";
import { sondarCerebro } from "./fala/saude-cerebro";
import { Adiador } from "./ui/dock";
import { Hud } from "./ui/hud";
import { Invisibilidade } from "./ui/invisivel";
import { Nucleo } from "./ui/nucleo";
import { aplicarAparencia } from "./ui/aparencia";
import { restaurarPreferencia, onDeviceChange, obterPreferencia } from "./audio/dispositivos";
import { ladoDoTamanho, ladoMudou, medidasDoWidget } from "./ui/tamanho";
import { ESPELHO_INICIAL, reduzir, salaExiste, type Espelho, type EventoEspelho } from "./sala/espelho";
import { lerNiveis } from "./sala/espectro";
import { abrirAssistenteSeNecessario, type DepsHospedeiro } from "./ui/primeiro-uso-hospedeiro";

const PRE_ROLL_MS = 300;
/** Prazo da voz própria numa fala fixa que não está no cache (o aquecimento usa o prazo normal). */
const PRAZO_FALA_FIXA_MS = 2000;
const MIN_FALA_MS = 300;

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig(); // nunca lança: arquivo ruim cai para o padrão
  const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
  const app = document.getElementById("app") as HTMLElement;
  const nucleo = new Nucleo(canvas, ladoDoTamanho(cfg));
  aplicarAparencia(cfg, nucleo);
  // Dock: a barra de botões abre do lado oposto à borda do monitor em que o widget está. Decidido pelo Rust 200 ms depois de parar de arrastar.
  const aplicarDock = async () => {
    try { app.classList.toggle("dock-cima", await invoke<boolean>("dock_em_cima")); } catch { /* fora do Tauri */ }
  };
  const dock = new Adiador(200, () => { void aplicarDock(); });
  // Tamanho do widget: uma escala para o CSS, o núcleo no lado real e a janela do mesmo tamanho (canto superior esquerdo fixo).
  const aplicarTamanho = async () => {
    const m = medidasDoWidget(ladoDoTamanho(cfg));
    document.documentElement.style.setProperty("--escala", String(m.escala));
    nucleo.redimensionar(m.lado);
    try { await invoke("redimensionar_janela", { largura: m.largura, altura: m.altura }); }
    catch (erro) { console.warn("não consegui redimensionar a janela", erro); }
    dock.pedir();
  };
  await aplicarTamanho();
  await aplicarDock();
  try { await getCurrentWindow().onMoved(() => dock.pedir()); } catch { /* fora do Tauri */ }
  nucleo.iniciar();
  let interromperTudo = () => {};
  let alternarMicrofone: () => Promise<void> = async () => {};
  let alternarNaoOuvir: () => Promise<void> = async () => {};
  let alternarNaoFalar: () => Promise<void> = async () => {};
  let olharTela = () => {};
  let abrirConfig = () => {};
  const hud = new Hud(cfg, app, {
    aoConfig: () => abrirConfig(),
    aoAvisos: () => {
      abrirConfig();
      // A janela do painel pode estar sendo criada agora: repete o pedido da aba até o painel ouvir.
      for (const atraso of [300, 1000, 2500]) setTimeout(() => { void emitTo("configuracoes", "abrir-aba", "avisos").catch(() => {}); }, atraso);
    },
    aoMudo: () => { void alternarNaoOuvir(); },
    aoNaoFalar: () => { void alternarNaoFalar(); },
    aoInterromper: () => interromperTudo(),
    aoTela: () => olharTela(),
    aoConfigMudou: (c) => { void emitTo("configuracoes", "config-mudou-no-widget", { sempre_no_topo: c.sempre_no_topo, compacto: c.compacto }).catch(() => {}); },
  });
  // Dispositivos de áudio: restaura a preferência salva e aplica o microfone escolhido.
  restaurarPreferencia({
    microfone_id: cfg.microfone_id,
    microfone_rotulo: cfg.microfone_rotulo,
    saida_id: cfg.saida_id,
    saida_rotulo: cfg.saida_rotulo,
  });
  definirMicrofonePreferido(cfg.microfone_id);
  // devicechange: revalida a preferência quando dispositivo reaparece ou some.
  // No modo jogo o microfone está solto; não reabre captura aqui — alternarMicrofone já cuida disso ao sair do jogo.
  let emModoJogo = false;
  onDeviceChange(() => {
    if (emModoJogo) return;
    const pref = obterPreferencia();
    definirMicrofonePreferido(pref.microfone_id);
    // A reabertura da captura com o novo deviceId acontece naturalmente na próxima fala;
    // não fechamos o microfone aqui para evitar cortes em conversas ativas.
  });

  // "Não ouvir" salvo: o widget nasce com o microfone desligado (é assim que ele abre; o botão Mudo fica aceso).
  if (cfg.nao_ouvir) hud.setMudo(true);
  // Bandeja (comando do Rust): espelha os dois estados; erro ignorado enquanto ele não existe.
  const sincronizarBandeja = () => {
    void invoke("sincronizar_bandeja", { naoOuvir: cfg.nao_ouvir, naoFalar: cfg.nao_falar }).catch(() => {});
  };
  // Modo invisível: o widget só aparece durante a conversa (ou revelado à mão). Nunca esconde a janela: o WebView2 estrangularia os timers do VAD.
  const invisibilidade = new Invisibilidade((visivel) => {
    hud.setInvisivel(!visivel);
    void invoke("definir_invisivel", { ligado: !visivel || cfg.click_through }).catch(() => {});
  });
  invisibilidade.definirModo(cfg.invisivel);
  // Sala (tela cheia): espelho do que o widget mostra. O widget guarda o mesmo espelho para mandar o retrato quando ela abre.
  let salaAberta = false;
  let espelho: Espelho = ESPELHO_INICIAL;
  const paraSala = (ev: EventoEspelho) => {
    espelho = reduzir(espelho, ev);
    if (salaAberta) void emitTo("sala", "sala:espelho", ev).catch(() => {});
  };
  // `revela`: false no "pensando" da transcrição sem push-to-talk; antes do nome ser dito o modo invisível não pode aparecer.
  const mostrarEstado = (e: Estado, detalhe = "", revela = true) => { if (revela) invisibilidade.definirEstado(e); nucleo.setEstado(e); hud.setEstado(e, detalhe); paraSala({ tipo: "estado", estado: e, detalhe }); };
  const mostrarOuvido = (t: string) => { hud.setOuvido(t); paraSala({ tipo: "ouvido", texto: t }); };
  const mostrarResposta = (t: string) => { hud.setResposta(t); paraSala({ tipo: "resposta", texto: t }); };
  hud.dica("clique para ligar o ouvido");
  // Atalhos que o Windows recusou no arranque (outro programa já usa): avisa uma vez na linha de estado.
  try {
    const falhas = await invoke<FalhaAtalho[]>("falhas_de_atalho");
    if (falhas.length) hud.avisar(`atalho ${falhas.map((f) => f.combinacao).join(", ")} não registrou; veja Configurações`);
  } catch { /* fora do Tauri */ }

  if (import.meta.env.DEV && import.meta.env.VITE_PROVA) {
    // Só em desenvolvimento: força um estado visual com analisadores sintéticos (para capturas de tela).
    (await import("./prova")).ativarProva(String(import.meta.env.VITE_PROVA), nucleo, hud);
  }

  // Assistente de primeiro uso: abre na janela de Configurações (não no widget).
  // Se deveMostrarAssistente for true, abre a janela de configurações automaticamente.
  const depsHospedeiro: DepsHospedeiro = {
    ponteUrl: cfg.ponte_url,
    salvarNome: async (nome: string, variantes: string[]) => {
      await atualizarConfig({ nome, variantes });
    },
    audio: {
      config: cfg,
      transcrever: (wav: ArrayBuffer, sinal: AbortSignal) => transcreverFala(wav, sinal),
      suspenderEscuta: async () => {
        const estavaMudo = estaMudo();
        if (!estavaMudo) definirMudo(true);
        return async () => {
          if (!estavaMudo) definirMudo(false);
        };
      },
      salvar: async (resultado: { microfone_id: string; saida_id: string; voz_id: string }) => {
        await atualizarConfig({
          microfone_id: resultado.microfone_id,
          saida_id: resultado.saida_id,
        });
      },
    },
    cerebro: {}, // T3c injeta o resto quando estiver pronta
  };
  // Verifica se o assistente deve aparecer e abre a janela de configurações automaticamente.
  const deveAbrir = await abrirAssistenteSeNecessario(depsHospedeiro, { raiz: app, apenasVerificar: true });
  if (deveAbrir) {
    void invoke("abrir_configuracoes").catch((erro) => console.warn("não abri o painel para o assistente", erro));
  }
  // Evento de reabertura agora é tratado na janela de configurações; aqui só mantemos compatibilidade.
  listen("reabrir-primeiro-uso", async () => {
    void invoke("abrir_configuracoes").catch(() => {});
  }).catch(() => {});

  // No `tauri dev` a origem do webview (localhost:1420) é recusada pelo CORS do OpenJarvis; o Vite faz a ponte em /oj.
  // Quando o cérebro é próprio e o toggle "Usar OpenJarvis" está desligado, o cliente OJ fica nulo:
  // nenhuma chamada ao OpenJarvis deve acontecer nesse modo (sem-openjarvis.md).
  const deveUsarOj = () => cfg.cerebro === "openjarvis" || cfg.usar_openjarvis;
  const base = import.meta.env.DEV ? `${location.origin}/oj` : cfg.openjarvis_url;
  const clienteOj = new OpenJarvis(base, cfg.modelo, deveUsarOj);
  let oj: OpenJarvis | null = deveUsarOj() ? clienteOj : null;

/** Transcrição pelo serviço de voz do Vard (mesmo formato /v1/speech/transcribe); o OpenJarvis é só reserva. */
async function transcreverFala(wav: ArrayBuffer, sinal?: AbortSignal): Promise<string> {
  const voz = cfg.voz_url?.trim();
  if (voz) {
    try { return await new OpenJarvis(voz).transcrever(wav, cfg.idioma, sinal); }
    catch (erro) { if (!oj || sinal?.aborted) throw erro; console.warn("transcrição no serviço de voz falhou; tentando o OpenJarvis", erro); }
  }
  if (!oj) throw new Error("Sem transcrição: o serviço de voz não respondeu e o OpenJarvis está desligado.");
  return oj.transcrever(wav, cfg.idioma, sinal);
}
  // Voz própria opcional (docs/voz-propria.md). Vazio desliga: a voz fica sempre a do OpenJarvis.
  let voz: FonteDeVoz | null = criarFonteDeVoz(cfg);
  // Voz de reserva configurada pelo usuário; usada automaticamente quando a principal falhar.
  const criarReserva = (): FonteDeVoz | null => cfg.voz_reserva_provedor && cfg.voz_reserva_provedor !== "nenhuma"
    ? criarFonteDeVoz({
        voz_provedor: cfg.voz_reserva_provedor as ProvedorVoz,
        voz_url: cfg.voz_url,
        voz_motor: cfg.voz_reserva_motor ?? "",
        voz_propria: cfg.voz_reserva_id ?? "",
        elevenlabs_chave: cfg.elevenlabs_chave,
        elevenlabs_voz: cfg.voz_reserva_provedor === "elevenlabs" ? (cfg.voz_reserva_id ?? "") : "",
        gemini_chave: cfg.gemini_chave,
        gemini_voz: cfg.voz_reserva_provedor === "gemini" ? (cfg.voz_reserva_id ?? "") : "",
      })
    : null;
  let vozReserva = criarReserva();

  // Painel de configurações: janela própria (engrenagem, bandeja ou atalho). Aqui só o clique atravessando a janela.
  const aplicarClickThrough = (ligado: boolean) => { void invoke("definir_click_through", { ligado }).catch(() => {}); };
  abrirConfig = () => { void invoke("abrir_configuracoes").catch((erro) => console.warn("não abri o painel", erro)); };
  if (cfg.click_through) aplicarClickThrough(true);

  // A boca só existe depois que o microfone abre (usa o mesmo AudioContext).
  let bocaReal: Boca | null = null;
  // "Não falar" ligado: nenhuma síntese nem áudio passa daqui (nem a fala fixa, nem a resposta, nem os avisos).
  let naoFalar = cfg.nao_falar;
  // Latência: do fim da fala do usuário até o começo da reprodução da resposta.
  let fimDaFala = 0;
  const boca = {
    get falando() { return bocaReal?.falando ?? false; },
    async tocar(wav: ArrayBuffer) {
      if (naoFalar) return;
      if (!bocaReal) return;
      if (fimDaFala) { hud.setLatencia(performance.now() - fimDaFala); fimDaFala = 0; }
      await bocaReal.tocar(wav);
    },
    async tocarFluxo(corpo: ReadableStream<Uint8Array>, taxa: number, sinal?: AbortSignal) {
      if (naoFalar) { await corpo.cancel().catch(() => {}); return; }
      if (!bocaReal) { await corpo.cancel().catch(() => {}); return; }
      if (fimDaFala) { hud.setLatencia(performance.now() - fimDaFala); fimDaFala = 0; }
      await bocaReal.tocarFluxo(corpo, taxa, sinal);
    },
    parar() { bocaReal?.parar(); },
  };
  // "Não ouvir" = o que o Mudo já faz (fecha ou mudo o microfone), gravado na config e espelhado na bandeja.
  const aplicarNaoOuvir = async (valor: boolean, gravar: boolean) => {
    cfg.nao_ouvir = valor;
    if (valor) {
      if (ligado) definirMudo(true);
      hud.setMudo(true);
    } else if (!ligado) {
      await alternarMicrofone(); // primeira vez: abre sem mudo
    } else {
      definirMudo(false); hud.setMudo(false);
    }
    if (gravar) {
      try { await atualizarConfig({ nao_ouvir: valor }); } catch (erro) { console.warn("não consegui gravar o não ouvir", erro); }
    }
    sincronizarBandeja();
    // O painel aberto precisa acompanhar (senão um Salvar dele restauraria o valor antigo).
    void emitTo("configuracoes", "nao-ouvir-falar-mudou", { nao_ouvir: cfg.nao_ouvir, nao_falar: cfg.nao_falar }).catch(() => {});
  };
  // "Não falar" = a resposta só em texto: corta o áudio em curso sem abortar a pergunta que já está no ar.
  const aplicarNaoFalar = async (valor: boolean, gravar: boolean) => {
    naoFalar = valor; cfg.nao_falar = valor;
    hud.setNaoFalar(valor);
    if (valor) boca.parar();
    if (gravar) {
      try { await atualizarConfig({ nao_falar: valor }); } catch (erro) { console.warn("não consegui gravar o não falar", erro); }
    }
    sincronizarBandeja();
    void emitTo("configuracoes", "nao-ouvir-falar-mudou", { nao_ouvir: cfg.nao_ouvir, nao_falar: cfg.nao_falar }).catch(() => {});
  };
  alternarNaoOuvir = async () => { await aplicarNaoOuvir(ligado && !estaMudo(), true); };
  alternarNaoFalar = async () => { await aplicarNaoFalar(!naoFalar, true); };

  // Captura: anel com os últimos ~300 ms (pre-roll) + acúmulo da fala.
  let anel: Float32Array[] = [];
  let anelAmostras = 0;
  let pcm: Float32Array[] = [];
  let capturando = false;
  let pttSegurado = false;
  let cicloVoz = 0;
  let ocupado = false; // transcrevendo ou pensando: ignora novos eventos do VAD
  let pttPendente = false; // push-to-talk apertado durante a resposta: começa a capturar quando o ciclo terminar
  let estavaFalando = false;

  // Ponte opcional do Vard: sem ela o HUD funciona igual, só sem o botão Tela e sem modo jogo.
  const ponte = new Ponte(cfg.ponte_url);
  // Central de avisos: lista a cada status (10 s) e os eventos ao vivo entram sozinhos.
  const avisos = new CentralAvisos(ponte);
  avisos.aoMudar = () => hud.setNaoLidos(avisos.naoLidos);
  // Tarefas em andamento: sinal discreto no HUD e na dica da bandeja (o indicador some no modo invisível).
  const emAndamento = new EmAndamento(ponte);
  emAndamento.aoMudar = () => {
    hud.setEmAndamento(emAndamento.total, dicaDeAndamento(emAndamento.tarefas));
    void invoke("definir_tarefas_bandeja", { n: emAndamento.total }).catch(() => {});
  };
  // Reunião: o widget fica mudo enquanto ela corre (o serviço da reunião é quem manda; aqui só escutamos).
  let reuniaoAtiva = false;
  let aoReuniao: (ativa: boolean) => void = () => {};
  const estadoReuniao = new EstadoReuniao((ativa) => aoReuniao(ativa));
  if (cfg.ponte_url) ponte.eventos((tipo, dados) => {
    if (tipo === "oficina" || tipo === "reuniao") {
      // aplicarEvento retorna true apenas se o aviso foi realmente adicionado (id novo + estado final).
      // Estados intermediários (em_andamento, iniciada) e duplicatas retornam false e não devem disparar fala nem chamada.
      const avisoNovo = avisos.aplicarEvento(tipo, dados);
      // Evita fala dupla: com "me chamar quando algo ficar pronto" ligado, a chamada proativa já fala o resumo;
      // falarAviso só toca quando a opção está desligada.
      if (!chamarQuandoPronto) void falarAviso(tipo, dados);
      if (tipo === "oficina") {
        void emAndamento.aplicarEvento(tipo); // qualquer estado recarrega a lista
        // T14/CDP item 2: emite evento Tauri "aviso" APENAS para avisos novos de verdade,
        // evitando chamar "Paulo?" a cada mudança de estado intermediário.
        if (avisoNovo) {
          const d = typeof dados === "object" && dados !== null ? (dados as Record<string, unknown>) : {};
          const resumo = typeof d.resumo === "string" ? d.resumo : JSON.stringify(dados ?? {});
          void emit("aviso", resumo).catch(() => {});
        }
      }
    }
    if (tipo === "reuniao") estadoReuniao.aplicarEvento(dados);
    // Cérebro próprio: repassa eventos de pedido via MessageEvent para a conversa consumir.
    if (tipo === "pedido") {
      window.dispatchEvent(new MessageEvent("vard-evento-pedido", { data: JSON.stringify(dados) }));
    }
  });
  let ponteNoAr = true; // desconhecida até a 1ª sondagem (já disparada abaixo): tenta a ponte em vez de dizer que não há
  const espera = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  // Falas fixas: a voz própria primeiro (o cache guarda o WAV dela), o OpenJarvis como reserva.
  const fixa = async (t: string, rapido = true) => {
    const fontes: FonteDeFala[] = [];
    const fonteAtual = voz;
    if (fonteAtual && (fonteAtual.nome || (await fonteAtual.saude(), fonteAtual.nome))) {
      // Prazo curto: uma voz pendurada não segura "Oi." por 8 s antes da reserva. O aquecimento, que não tem pressa, usa o prazo normal.
      fontes.push({ origem: "voz", voz: fonteAtual.nome, sintetizar: () => fonteAtual.falarWav(t, cfg.velocidade, rapido ? PRAZO_FALA_FIXA_MS : undefined) });
    }
    // OpenJarvis só entra como reserva de fala quando está ativo; com cerebro=proprio e toggle desligado, oj é null.
    const ojAtual = oj;
    if (ojAtual) {
      fontes.push({ origem: "oj", voz: cfg.voz, sintetizar: () => ojAtual.sintetizar(t, cfg.voz, cfg.velocidade) });
    }
    return falaFixa(t, fontes);
  };
  // Aviso falado (só com "falar avisos" ligado): o resumo que a ponte mandou, pela mesma rota das frases fixas.
  // Nunca interrompe o que estiver falando (ou transcrevendo): com a boca ocupada o aviso só fica na tela.
  const avisosPorVez = new AvisoPorVez();
  const falarAviso = async (tipo: string, dados: unknown) => {
    const d = typeof dados === "object" && dados !== null ? (dados as Record<string, unknown>) : {};
    const resumo = typeof d.resumo === "string" ? d.resumo.trim() : "";
    const ev = { tipo: tipo === "oficina" ? "tarefa" : tipo, estado: typeof d.estado === "string" ? d.estado : undefined };
    if (!resumo || !deveFalarAviso(cfg, ev, ocupado || boca.falando, reuniaoAtiva)) return;
    await avisosPorVez.executar(async () => {
      const wav = await fixa(resumo); // sintetizar pode demorar: enquanto isso a reunião pode começar, o "não falar" pode ligar ou uma resposta pode começar a falar
      if (!deveFalarAviso(cfg, ev, ocupado || boca.falando, reuniaoAtiva)) return;
      try { await boca.tocar(wav); } catch { /* sem voz, o aviso já está na tela */ }
    });
  };

  let sessaoVozId = crypto.randomUUID();
  const conversa = new Conversa({
    get oj() { return oj; }, boca, config: cfg,
    get voz() { return voz ?? undefined; },
    get vozReserva() { return vozReserva ?? undefined; },
    falas: fixa,
    reuniaoAtiva: () => reuniaoAtiva,
    falarPermitida: () => !naoFalar,
    get cerebro() { return cfg.cerebro; },
    sessaoVoz: () => sessaoVozId,
    aoEstado: (e, detalhe) => {
      mostrarEstado(e, detalhe);
      // Terminou de falar: descarta o pre-roll, que teria a cauda da própria voz (eco).
      if (estavaFalando && e !== "falando") { anel = []; anelAmostras = 0; }
      estavaFalando = e === "falando";
      // T13: modo jogo desliga a conversa aberta automaticamente
      if (e === "jogo" && conversaAberta.estado !== "desligado") {
        conversaAberta.contextoMudou("jogo");
        hud.setConversaAberta(false);
        if (timerSilencioAberta) { clearTimeout(timerSilencioAberta); timerSilencioAberta = null; }
        console.info("conversa aberta: desligada por jogo");
      }
    },
    aoResposta: (t) => mostrarResposta(t),
    ponte, ponteNoAr: () => ponteNoAr,
    // Indicador vermelho por ~1 s antes de capturar; a captura é direta (sem compartilhamento).
    antesDaCaptura: async () => { hud.setIndicadorTela(true); await espera(1000); },
    depoisDaCaptura: () => hud.setIndicadorTela(false),
    capturar: async () => {
      try { return await invoke<string>("capturar_tela"); } finally { hud.setIndicadorTela(false); }
    },
    abrirMicrofone: () => abrirSeFechado(),
    fecharMicrofone: () => fecharTudoDoMicrofone(),
    mutar: () => { definirMudo(true); hud.setMudo(true); },
    aoCanal: (aberto) => {
      invisibilidade.definirCanal(aberto);
      console.info("modo conversa:", aberto ? "aberto" : "fechado");
    },
    aoDesligarConversaAberta: () => {
      if (conversaAberta.estado !== "desligado") alternarConversaAberta();
    },
    aoLigarConversaAberta: () => {
      if (conversaAberta.estado === "desligado") alternarConversaAberta();
    },
    aoProcessamentoConcluido: () => {
      processamentoConcluido(conversaAberta);
      rearmarTimerSilencioAberta();
    },
  });
  olharTela = () => { void conversa.aoTextoTranscrito("olha a tela", true); };

  // T13 — Conversa aberta contínua: máquina de estados pura ligada ao fluxo de transcrição.
  const conversaAberta = criarMaquinaConversaAberta();
  let timerSilencioAberta: ReturnType<typeof setTimeout> | null = null;
  const rearmarTimerSilencioAberta = () => {
    if (timerSilencioAberta) clearTimeout(timerSilencioAberta);
    if (conversaAberta.estado !== "ouvindo") return;
    timerSilencioAberta = setTimeout(() => {
      conversaAberta.silencioExpirou();
      hud.setConversaAberta(false);
      console.info("conversa aberta: silêncio expirou");
    }, 300_000); // 5 min padrão
  };
  const alternarConversaAberta = () => {
    if (conversaAberta.estado === "desligado") {
      conversaAberta.ligar();
      hud.setConversaAberta(true);
      rearmarTimerSilencioAberta();
      console.info("conversa aberta: ligada");
    } else {
      conversaAberta.desligar();
      hud.setConversaAberta(false);
      if (timerSilencioAberta) { clearTimeout(timerSilencioAberta); timerSilencioAberta = null; }
      console.info("conversa aberta: desligada");
    }
  };
  await listen("alternar-conversa", () => alternarConversaAberta());

  const detector = new DetectorSelecionavel(cfg.vad, { limiar: cfg.limiar_vad, inicioMs: cfg.interromper_ao_falar ? 250 : 150, fimMs: cfg.finish_ms, tetoMs: 12000 }, carregarSilero);
  // Descarta a captura em curso: a reunião que começa no meio dela (o VAD pararia de finalizar e o PCM
  // cresceria a reunião inteira) e o modo jogo que solta o microfone usam o mesmo caminho.
  const descartarCaptura = () => {
    capturando = false;
    pcm = []; anel = []; anelAmostras = 0;
    pttSegurado = false;
    detector.reset();
  };
  // Reunião começou: corta o que estiver falando e acende o chip; quando termina, o widget volta ao estado do usuário.
  aoReuniao = (ativa) => {
    reuniaoAtiva = ativa;
    hud.setReuniao(ativa);
    if (ativa) {
      descartarCaptura();
      conversa.interromper();
      // T13: reunião desliga a conversa aberta automaticamente
      if (conversaAberta.estado !== "desligado") {
        conversaAberta.contextoMudou("reuniao");
        hud.setConversaAberta(false);
        if (timerSilencioAberta) { clearTimeout(timerSilencioAberta); timerSilencioAberta = null; }
        console.info("conversa aberta: desligada por reunião");
      }
    }
  };

  // Status da ponte a cada 10 s: mostra/esconde o botão Tela e acompanha o modo jogo. Nunca trava a conversa.
  const sondarPonte = async () => {
    const st = await ponte.status();
    ponteNoAr = st !== null;
    hud.setPonte(ponteNoAr);
    estadoReuniao.atualizarStatus(st ? st.reuniao ?? "ausente" : null);
    void avisos.carregar(); // falha em silêncio com a ponte fora
    void emAndamento.carregar(); // falha em silêncio com a ponte fora
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
    for (const t of [saudacaoPara(cfg.usuario), FALAS.erroModelo, FALAS.erroOuvido, FALAS.openjarvisFora, FALAS.voltei, FALAS.modoJogoAtivado, FALAS.pareiDeOuvir]) {
      try { await fixa(t, false); } catch { aquecido = false; } // uma de cada vez: não disputa a GPU com a conversa
    }
  };
  const checarSaude = async () => {
    // Com cerebro=proprio e toggle desligado, oj é null: quem responde é o núcleo (o /status da ponte).
    const { ok, falaOk } = await sondarCerebro(oj, ponte);
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

  const guardarAmostras = (a: Float32Array) => {
    if (capturando) { pcm.push(a); return; }
    anel.push(a); anelAmostras += a.length;
    const maximo = (taxaAtual() * PRE_ROLL_MS) / 1000;
    while (anel.length > 1 && anelAmostras - anel[0].length >= maximo) anelAmostras -= anel.shift()!.length;
  };

  const comecarCaptura = () => {
    pcm = anel; anel = []; anelAmostras = 0; // o pre-roll vira o começo da fala
    capturando = true;
    mostrarEstado("ouvindo");
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
      mostrarEstado(conversa.estado, conversa.detalhe);
      return;
    }
    const ciclo = ++cicloVoz;
    ocupado = true;
    mostrarEstado("pensando", "", pushToTalk);
    try {
      const wav = pcmParaWav(reamostrar(tudo, taxaAtual(), 16000), 16000);
      let texto: string;
      try {
        texto = await transcreverFala(wav);
      } catch (erro) {
        if (ciclo !== cicloVoz || estaMudo() || reuniaoAtiva) return;
        console.warn("transcrição falhou", erro);
        if (!naoFalar) { try { await boca.tocar(await fixa(FALAS.erroOuvido)); } catch { /* sem voz, fica só no HUD */ } }
        return;
      }
      if (ciclo !== cicloVoz || estaMudo() || reuniaoAtiva) return;
      console.log("ouvi:", texto);
      if (texto) mostrarOuvido(texto);
      // Roteamento único (T14 + T13): fluxo de chamada tem prioridade; nome dispensado quando pushToTalk OU conversa aberta ligada.
      await processarTextoOuvido(
        {
          fluxoChamada,
          conversa,
          executarAcoesChamada,
          conversaAbertaEstado: () => conversaAberta.estado,
        },
        texto,
        pushToTalk,
      );
    } catch (erro) {
      console.error("ciclo de fala falhou", erro);
    } finally {
      if (ciclo !== cicloVoz) return;
      fimDaFala = 0;
      ocupado = false;
      detector.reset();
      mostrarEstado(conversa.estado, conversa.detalhe);
      if (pttPendente && pttSegurado && ligado && !capturando) comecarCaptura();
      pttPendente = false;
    }
  };

  const controleVoz = new ControleCapturaVoz(cfg.interromper_ao_falar, {
    interromper: () => {
      ++cicloVoz;
      // A transicao de estado limpa a cauda da boca; nesta interrupcao o anel ja contem a nova fala.
      const preRoll = anel; const amostras = anelAmostras;
      conversa.interromper();
      anel = preRoll; anelAmostras = amostras;
      ocupado = false; fimDaFala = 0;
    },
    capturar: () => { if (!capturando) comecarCaptura(); },
    encerrar: () => { if (capturando) void encerrar(false); },
  });
  const referenciasSaida: Float32Array[] = [];
  const entradaEco = new Float32Array(256);
  let ligado = false;
  let analisadorEntrada: AnalyserNode | null = null; // o do microfone, para a sala
  let relogioVad = 0;
  let tiques = 0; // prova em dev: o laço do VAD não pode ser estrangulado com o widget invisível
  if (import.meta.env.DEV) setInterval(() => { console.info(`vad: ${tiques} tiques em 10 s`); tiques = 0; }, 10000);
  let largarAmostras: (() => void) | null = null;
  // Modo jogo: solta o microfone de verdade (a GPU e o ouvido ficam livres); alternarMicrofone reabre sozinho depois.
  const fecharTudoDoMicrofone = (): boolean => {
    if (!ligado) return false; // nunca foi aberto: a volta do jogo não abre sozinha
    clearInterval(relogioVad);
    detector.fechar(); referenciasSaida.length = 0;
    largarAmostras?.(); largarAmostras = null;
    bocaReal?.parar(); bocaReal = null;
    nucleo.setAnalisadores(null, null);
    analisadorEntrada = null;
    fecharMicrofone();
    ligado = false;
    descartarCaptura();
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
      analisadorEntrada = mic.analisador;
      definirMudo(false);
      hud.setMudo(false);
      bocaReal = new Boca(mic.contexto);
      void aplicarSaidaNoContexto(mic.contexto).catch(() => {});
      hud.setTaxa(mic.contexto.sampleRate);
      mostrarEstado(conversa.estado, conversa.detalhe);
      nucleo.setAnalisadores(mic.analisador, bocaReal.analisador);
      largarAmostras = onAmostras(guardarAmostras);
      void detector.iniciar(mic);
      relogioVad = window.setInterval(() => {
        tiques++;
        // Reunião em andamento conta como mudo (sem gravar nada na config e sem mexer no botão Mudo do usuário).
        if (cfg.interromper_ao_falar && bocaReal) {
          const saida = new Float32Array(256);
          bocaReal.analisador.getFloatTimeDomainData(saida);
          referenciasSaida.push(saida);
          if (referenciasSaida.length > 6) referenciasSaida.shift();
        }
        mic.analisador.getFloatTimeDomainData(entradaEco);
        const contexto = {
          falando: boca.falando, ocupado, mudo: estaMudo(), reuniao: reuniaoAtiva,
          jogo: conversa.estado === "jogo", ptt: pttSegurado,
          eco: cfg.interromper_ao_falar && !capturando && pareceEco(entradaEco, referenciasSaida),
        };
        if (controleVoz.bloqueado(contexto)) { detector.reset(); return; }
        controleVoz.processar(detector.alimentar(rmsAtual(), performance.now()), contexto);
      }, 50);
    } catch (erro) {
      console.error("falha ao abrir o microfone", erro);
      mostrarEstado("erro", FALAS.microfoneBloqueado);
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
    const injetar = async (texto: string, pushToTalk: boolean) => {
      if (!bocaReal) {
        const ctxDev = new AudioContext();
        void aplicarSaidaNoContexto(ctxDev).catch(() => {});
        bocaReal = new Boca(ctxDev);
        nucleo.setAnalisadores(null, bocaReal.analisador);
      }
      ocupado = true;
      try {
        console.log("ouvi:", texto);
        mostrarOuvido(texto);
        // Roteamento único (T14 + T13): igual ao caminho real do VAD.
        await processarTextoOuvido(
          {
            fluxoChamada,
            conversa,
            executarAcoesChamada,
            conversaAbertaEstado: () => conversaAberta.estado,
          },
          texto,
          pushToTalk,
        );
      } finally {
        ocupado = false;
        detector.reset();
        mostrarEstado(conversa.estado, conversa.detalhe);
      }
    };
    (window as unknown as { __vardPergunta?: (t: string) => Promise<void> }).__vardPergunta = (texto: string) => injetar(texto, true);
    // Gancho de dev sem push-to-talk: passa pushToTalk=false e depende da regra unificada
    // (nome dispensado quando conversa aberta ligada), igual ao caminho real do VAD.
    (window as unknown as { __vardOuvido?: (t: string) => Promise<void> }).__vardOuvido = (texto: string) => injetar(texto, false);
    // Prova do dock: move a janela para uma posição física.
    (window as unknown as { __vardMover?: (x: number, y: number) => Promise<void> }).__vardMover = (x: number, y: number) => getCurrentWindow().setPosition(new PhysicalPosition(x, y));
  }

  await listen("ptt-inicio", () => {
    if (!ligado || estaMudo() || reuniaoAtiva) return; // reunião: o widget está mudo (sem tocar no mudo do usuário)
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
  await listen("alternar-revelacao", () => invisibilidade.alternarRevelacao());
  await listen<unknown>("invisivel", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("invisivel ignorado: payload inválido"); return; }
    cfg.invisivel = ev.payload; invisibilidade.definirModo(ev.payload);
  });
  await listen("alternar-escuta", () => { void alternarNaoOuvir(); });
  // "Não falar": o atalho global alterna; a bandeja manda o valor já decidido.
  await listen("alternar-fala", () => { void alternarNaoFalar(); });
  await listen<unknown>("nao-ouvir", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("nao-ouvir ignorado: payload inválido"); return; }
    void aplicarNaoOuvir(ev.payload, false);
  });
  await listen<unknown>("nao-falar", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("nao-falar ignorado: payload inválido"); return; }
    void aplicarNaoFalar(ev.payload, false);
  });
  // Sala aberta: retrato na hora e níveis a 20 Hz (o vórtice dela reage como o daqui). Fechada: nada vai para lá.
  let relogioSala = 0;
  const retomarSala = () => {
    salaAberta = true;
    void emitTo("sala", "sala:espelho", { tipo: "retrato", espelho }).catch(() => {});
    clearInterval(relogioSala);
    relogioSala = window.setInterval(() => {
      void emitTo("sala", "sala:niveis", { entrada: lerNiveis(analisadorEntrada), saida: lerNiveis(bocaReal?.analisador ?? null) }).catch(() => {});
    }, 50);
  };
  await listen("sala:pronta", retomarSala);
  // Widget recarregado com a sala já aberta: ela não avisa de novo, então pergunta se existe.
  try { if (salaExiste(await WebviewWindow.getByLabel("sala"))) retomarSala(); } catch { /* sem sala */ }
  await listen("sala-fechada", () => { salaAberta = false; clearInterval(relogioSala); });
  // T14 — Chamada proativa: quando um aviso chega e o contexto permite, a Aurora chama o usuário.
  let chamarQuandoPronto = true; // padrão ligado; atualizado pelo checkbox da aba Avisos via gravar_config
  await listen<{ chamar_quando_pronto?: boolean }>("config-salva", (ev) => {
    if (typeof ev.payload?.chamar_quando_pronto === "boolean") chamarQuandoPronto = ev.payload.chamar_quando_pronto;
  });
  const fluxoChamada = criarFluxoChamada();
  let timerChamada: ReturnType<typeof setTimeout> | null = null;
  const executarAcoesChamada = async (acoes: { tipo: string; texto?: string }[]) => {
    for (const acao of acoes) {
      if (acao.tipo === "sintetizar" && acao.texto) {
        try {
          const wav = await fixa(acao.texto);
          await boca.tocar(wav);
        } catch { /* sem voz, o aviso já está na tela */ }
        // Transiciona para conversando após leitura do aviso (mesmo se a fala falhar).
        // O estado já foi mudado para lendo_aviso por usuarioRespondeu antes de retornar as ações.
        if (fluxoChamada.estado === "lendo_aviso") {
          const acoesLeitura = fluxoChamada.leituraConcluida();
          void executarAcoesChamada(acoesLeitura);
        }
      } else if (acao.tipo === "abrir_escuta") {
        // Abre escuta curta para resposta de presença ou conversa pós-aviso.
        // O VAD já está ativo; aqui só sinalizamos que o próximo texto transcrito
        // deve ser roteado para o fluxo de chamada.
        console.info("chamada proativa: escuta aberta");
      } else if (acao.tipo === "fechar_escuta") {
        console.info("chamada proativa: escuta fechada");
      }
    }
  };
  await listen<unknown>("aviso", (ev) => {
    if (typeof ev.payload !== "string") { console.warn("aviso ignorado: payload inválido"); return; }
    hud.avisar(ev.payload);
    // T14: alimenta o fluxo de chamada proativa (respeita o checkbox da aba Avisos)
    if (chamarQuandoPronto && (fluxoChamada.estado === "inativo" || fluxoChamada.estado === "conversando")) {
      const acoes = fluxoChamada.avisoRecebido(
        { id: Date.now().toString(), resumo: ev.payload },
        { falarLiberado: !naoFalar && !cfg.nao_falar, emReuniao: reuniaoAtiva },
      );
      void executarAcoesChamada(acoes);
      // O estado pode ter mudado dentro de avisoRecebido; lemos novamente sem narrowing.
      const estadoPosAviso: string = fluxoChamada.estado;
      // Arma timeout de espera se entrou em aguardando_resposta
      if (estadoPosAviso === "aguardando_resposta") {
        if (timerChamada) clearTimeout(timerChamada);
        timerChamada = setTimeout(() => {
          const acoesTimeout = fluxoChamada.timeoutEspera();
          void executarAcoesChamada(acoesTimeout);
          timerChamada = null;
        }, 30_000);
      }
      // Arma timeout de conversa se entrou em conversando após leitura
      if (estadoPosAviso === "conversando") {
        if (timerChamada) clearTimeout(timerChamada);
        timerChamada = setTimeout(() => {
          const acoesEncerra = fluxoChamada.conversaEncerrada();
          void executarAcoesChamada(acoesEncerra);
          timerChamada = null;
        }, 15_000);
      }
    }
  });
  await listen<unknown>("sempre-no-topo", (ev) => {
    if (typeof ev.payload !== "boolean") { console.warn("sempre-no-topo ignorado: payload inválido"); return; }
    cfg.sempre_no_topo = ev.payload; hud.atualizarTopo();
  });

  // Painel salvou (janela configuracoes): aplica na hora só o que o widget sabe aplicar; o resto espera o reinício.
  const aplicarConfigSalva = async (payload: unknown) => {
    const recebido = normalizarConfig(payload);
    const novo = lerConfigAoVivo(recebido);
    if (!novo) { console.warn("config-salva ignorada: payload inválido"); return; }
    const antes = { tamanho: cfg.tamanho, tamanho_px: cfg.tamanho_px };
    const mudou = aplicarAoVivo(cfg, novo);
    if (mudou.includes("cerebro") || mudou.includes("usar_openjarvis")) oj = deveUsarOj() ? clienteOj : null;
    if (aplicarVozAoVivo(cfg, recebido)) { voz = criarFonteDeVoz(cfg); vozReserva = criarReserva(); }
    if (ladoMudou(antes, cfg)) await aplicarTamanho(); // só quando o lado de fato mudou
    if (mudou.includes("compacto")) hud.setCompacto(cfg.compacto);
    if (mudou.includes("sempre_no_topo")) {
      try { await invoke("definir_sempre_no_topo", { ligado: cfg.sempre_no_topo }); } catch (erro) { console.warn("topo", erro); }
      hud.atualizarTopo();
    }
    if (mudou.includes("click_through")) aplicarClickThrough(cfg.click_through || !invisibilidade.visivel()); // invisível segue sem cliques
    if (mudou.includes("invisivel")) {
      invisibilidade.definirModo(cfg.invisivel);
      void invoke("marcar_invisivel_na_bandeja", { ligado: cfg.invisivel }).catch(() => {});
    }
    if (mudou.includes("modelo")) clienteOj.definirModelo(cfg.modelo);
    if (mudou.includes("usuario")) void fixa(saudacaoPara(cfg.usuario), false).catch(() => {}); // aquece a saudação nova
    if (mudou.includes("nao_ouvir")) await aplicarNaoOuvir(cfg.nao_ouvir, false); // o painel já gravou
    if (mudou.includes("nao_falar")) await aplicarNaoFalar(cfg.nao_falar, false);
    if (mudou.includes("cor_elementos") || mudou.includes("opacidade_elementos")) {
      aplicarAparencia(cfg, nucleo);
    }
  };
  await listen<unknown>("config-salva", (ev) => { void aplicarConfigSalva(ev.payload); });
  // As seleções e receitas são consultadas pelo núcleo a cada pedido; o widget acompanha seu arquivo.
  await listen("paineis-mudaram", () => { void carregarConfig().then(aplicarConfigSalva); });
  await listen("habilidades-mudaram", () => { void carregarConfig().then(aplicarConfigSalva); });

  // T7b — Restaurar estado ao voltar do modo jogo: escuta/fala/dispositivos/janelas.
  await listen<{ modo: string; servicos_ligados?: string[] }>("ciclo-estado", (ev) => {
    const foto = ev.payload;
    if (!foto || typeof foto.modo !== "string") return;
    const eraJogo = emModoJogo;
    emModoJogo = foto.modo === "jogo";
    // Ao sair do jogo (transição jogo -> ligado/liberando): restaurar preferências salvas.
    if (eraJogo && !emModoJogo) {
      // 1. Dispositivos: aplicar preferência ANTES de reabrir captura.
      const pref = obterPreferencia();
      definirMicrofonePreferido(pref.microfone_id);
      // 2. Escuta/Fala: restaurar exatamente como estavam na config salva.
      // A config já tem os valores corretos (não foram alterados durante o jogo).
      if (cfg.nao_ouvir) {
        hud.setMudo(true);
        definirMudo(true);
      } else {
        hud.setMudo(false);
        definirMudo(false);
      }
      // naoFalar é variável local capturada no closure; aplicarNaoFalar atualiza tudo.
      void aplicarNaoFalar(cfg.nao_falar, false);
      // 3. Sincronizar bandeja com os estados restaurados.
      sincronizarBandeja();
      console.info("retorno do jogo: escuta/fala/dispositivos restaurados");
    }
  });
});
