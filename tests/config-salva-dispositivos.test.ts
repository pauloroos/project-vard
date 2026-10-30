import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { CONFIG_PADRAO } from "../src/config/config";

const fakes = vi.hoisted(() => ({
  definirMicrofonePreferido: vi.fn(),
  aplicarSaidaNoContexto: vi.fn(async () => true),
  microfoneAberto: vi.fn(() => false),
  restaurarPreferencia: vi.fn(),
}));

const caixasEvento = vi.hoisted(() => ({
  mapa: new Map<string, ((ev: { payload: unknown }) => void)[]>(),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(async (evento: string, handler: (ev: { payload: unknown }) => void) => {
    const lista = caixasEvento.mapa.get(evento) ?? [];
    lista.push(handler);
    caixasEvento.mapa.set(evento, lista);
    return () => {};
  }),
  emit: vi.fn(async () => {}),
  emitTo: vi.fn(async () => {}),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async (cmd: string) => {
    if (cmd === "ler_config") return { microfone_id: "mic-antigo", microfone_rotulo: "antigo-mic", saida_id: "saida-antiga", saida_rotulo: "antiga-saida" };
    if (cmd === "dock_em_cima") return false;
    if (cmd === "falhas_de_atalho") return [];
    return null;
  }),
}));

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    onMoved: vi.fn(async () => {}),
    setPosition: vi.fn(async () => {}),
  }),
}));

vi.mock("@tauri-apps/api/dpi", () => ({
  PhysicalPosition: class {},
}));

vi.mock("@tauri-apps/api/webviewWindow", () => ({
  WebviewWindow: { getByLabel: vi.fn(async () => null) },
}));

vi.mock("../src/audio/microfone", async (orig) => ({
  ...(await orig<typeof import("../src/audio/microfone")>()),
  definirMicrofonePreferido: fakes.definirMicrofonePreferido,
  microfoneAberto: fakes.microfoneAberto,
}));

vi.mock("../src/audio/boca", async (orig) => ({
  ...(await orig<typeof import("../src/audio/boca")>()),
  aplicarSaidaNoContexto: fakes.aplicarSaidaNoContexto,
}));

vi.mock("../src/audio/dispositivos", async (orig) => ({
  ...(await orig<typeof import("../src/audio/dispositivos")>()),
  restaurarPreferencia: fakes.restaurarPreferencia,
}));

vi.mock("../src/ui/hud", () => ({
  Hud: class {
    constructor(..._a: unknown[]) {}
    setMudo = vi.fn();
    setNaoFalar = vi.fn();
    setEstado = vi.fn();
    setOuvido = vi.fn();
    setResposta = vi.fn();
    dica = vi.fn();
    avisar = vi.fn();
    setPonte = vi.fn();
    setReuniao = vi.fn();
    setEmAndamento = vi.fn();
    setNaoLidos = vi.fn();
    setIndicadorTela = vi.fn();
    setTaxa = vi.fn();
    setLatencia = vi.fn();
    setInvisivel = vi.fn();
    setCompacto = vi.fn();
    atualizarTopo = vi.fn();
    setConversaAberta = vi.fn();
  },
}));

vi.mock("../src/ui/nucleo", () => ({
  Nucleo: class {
    constructor(..._a: unknown[]) {}
    redimensionar = vi.fn();
    iniciar = vi.fn();
    setEstado = vi.fn();
    setAnalisadores = vi.fn();
  },
}));

vi.mock("../src/ui/invisivel", () => ({
  Invisibilidade: class {
    constructor(..._a: unknown[]) {}
    definirModo = vi.fn();
    definirEstado = vi.fn();
    definirCanal = vi.fn();
    alternarRevelacao = vi.fn();
    visivel = vi.fn(() => true);
  },
}));

vi.mock("../src/ui/aparencia", () => ({ aplicarAparencia: vi.fn() }));
vi.mock("../src/ui/dock", () => ({ Adiador: class { constructor(..._a: unknown[]) {} pedir = vi.fn(); } }));
vi.mock("../src/ui/tamanho", () => ({
  ladoDoTamanho: vi.fn(() => 320),
  ladoMudou: vi.fn(() => false),
  medidasDoWidget: vi.fn(() => ({ escala: 1, lado: 320, largura: 320, altura: 320 })),
}));
vi.mock("../src/sala/espelho", () => ({
  ESPELHO_INICIAL: {},
  reduzir: vi.fn((e: unknown) => e),
  salaExiste: vi.fn(() => false),
}));
vi.mock("../src/sala/espectro", () => ({ lerNiveis: vi.fn(() => []) }));
vi.mock("../src/audio/vad-selecionavel", () => ({
  DetectorSelecionavel: class { reset = vi.fn(); fechar = vi.fn(); iniciar = vi.fn(async () => {}); alimentar = vi.fn(() => null); },
  ControleCapturaVoz: class { constructor(..._a: unknown[]) {} bloqueado = vi.fn(() => false); processar = vi.fn(); },
  pareceEco: vi.fn(() => false),
}));
vi.mock("../src/audio/silero", () => ({ carregarSilero: vi.fn(async () => null) }));
vi.mock("../src/audio/cache", () => ({ falaFixa: vi.fn(async () => new ArrayBuffer(0)) }));
vi.mock("../src/conectores/openjarvis/cliente", () => ({ OpenJarvis: class { constructor(..._a: unknown[]) {} definirModelo = vi.fn(); transcrever = vi.fn(async () => ""); sintetizar = vi.fn(async () => new ArrayBuffer(0)); } }));
vi.mock("../src/conectores/ponte/cliente", () => ({ Ponte: class { constructor(..._a: unknown[]) {} status = vi.fn(async () => null); eventos = vi.fn(); } }));
vi.mock("../src/avisos/central", () => ({ CentralAvisos: class { constructor(..._a: unknown[]) {} aoMudar: unknown = null; naoLidos = 0; carregar = vi.fn(async () => {}); aplicarEvento = vi.fn(() => false); } }));
vi.mock("../src/avisos/andamento", () => ({ EmAndamento: class { constructor(..._a: unknown[]) {} aoMudar: unknown = null; total = 0; tarefas: unknown[] = []; carregar = vi.fn(async () => {}); aplicarEvento = vi.fn(() => {}); }, textoDaDica: vi.fn(() => "") }));
vi.mock("../src/avisos/fala", () => ({ deveFalarAviso: vi.fn(() => false), AvisoPorVez: class { executar = vi.fn(async (fn: () => Promise<void>) => { await fn(); }); } }));
vi.mock("../src/avisos/chamada", () => ({ criarFluxoChamada: vi.fn(() => ({ estado: "inativo", avisoRecebido: vi.fn(() => []), usuarioRespondeu: vi.fn(() => []), leituraConcluida: vi.fn(() => []), timeoutEspera: vi.fn(() => []), conversaEncerrada: vi.fn(() => []) })) }));
vi.mock("../src/reuniao/estado", () => ({ EstadoReuniao: class { constructor(..._a: unknown[]) {} aplicarEvento = vi.fn(); atualizarStatus = vi.fn(); } }));
vi.mock("../src/conectores/voz/escolher", () => ({ criarFonteDeVoz: vi.fn(() => null), PROVEDORES_VOZ: ["propria", "openjarvis", "elevenlabs", "gemini"] }));
vi.mock("../src/fala/conversa", () => ({ Conversa: class { constructor(..._a: unknown[]) {} estado = "repouso"; detalhe = ""; interromper = vi.fn(); aoTextoTranscrito = vi.fn(async () => {}); aoHealth = vi.fn(async () => {}); aoStatusPonte = vi.fn(async () => {}); } }));
vi.mock("../src/fala/textoOuvido", () => ({ processarTextoOuvido: vi.fn(async () => {}) }));
vi.mock("../src/conversa/aberta", () => ({ criarMaquinaConversaAberta: vi.fn(() => ({ estado: "desligado", ligar: vi.fn(), desligar: vi.fn(), contextoMudou: vi.fn(), silencioExpirou: vi.fn() })), processamentoConcluido: vi.fn() }));
vi.mock("../src/fala/falas", () => ({ FALAS: { erroModelo: "", erroOuvido: "", openjarvisFora: "", voltei: "", modoJogoAtivado: "", pareiDeOuvir: "", microfoneBloqueado: "" }, saudacaoPara: vi.fn(() => "oi") }));
vi.mock("../src/fala/saude-cerebro", () => ({ criarMemoriaSaude: vi.fn(() => ({})), sondarCerebro: vi.fn(async () => ({ ok: true, falaOk: true })) }));
vi.mock("../src/ui/primeiro-uso-hospedeiro", () => ({ abrirAssistenteSeNecessario: vi.fn(async () => false) }));

const CONTEXTO = { setSinkId: vi.fn(async () => {}) } as unknown as AudioContext;
const AVISO_MIC = "Reinicie para aplicar o microfone";
const AVISO_SAIDA = "Reinicie para aplicar o dispositivo";

function payload(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    ...CONFIG_PADRAO,
    microfone_id: "mic-antigo",
    microfone_rotulo: "antigo-mic",
    saida_id: "saida-antiga",
    saida_rotulo: "antiga-saida",
    ...overrides,
  };
}

async function dispararConfigSalva(p: Record<string, unknown>): Promise<void> {
  const handlers = caixasEvento.mapa.get("config-salva") ?? [];
  for (const h of handlers) {
    const r: unknown = h({ payload: p });
    if (r && typeof (r as Promise<unknown>).then === "function") await (r as Promise<unknown>);
  }
  await new Promise((res) => setTimeout(res, 20));
}

describe("config-salva troca de dispositivo via evento Tauri", () => {
  let mainMod: typeof import("../src/main");
  let erro: ReturnType<typeof vi.spyOn>;

  beforeAll(async () => {
    document.body.innerHTML = `<div id="app"><canvas id="nucleo"></canvas><div id="dica"></div><div id="botoes"></div><div id="resposta"></div></div>`;
    const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
    // jsdom sem canvaskit
    (canvas as unknown as { getContext: unknown }).getContext = (() => ({
      fillRect: () => {}, clearRect: () => {}, save: () => {}, restore: () => {},
      translate: () => {}, scale: () => {}, setTransform: () => {},
      createRadialGradient: () => ({ addColorStop: () => {} }),
      beginPath: () => {}, arc: () => {}, fill: () => {}, stroke: () => {},
      moveTo: () => {}, lineTo: () => {},
    })) as unknown as typeof canvas.getContext;
    mainMod = await import("../src/main");
    window.dispatchEvent(new Event("DOMContentLoaded"));
    await new Promise((res) => setTimeout(res, 40));
  });

  beforeEach(() => {
    vi.clearAllMocks();
    fakes.aplicarSaidaNoContexto.mockResolvedValue(true);
    fakes.microfoneAberto.mockReturnValue(false);
    // restaura cfg base
    const cfg = mainMod.__obterCfg();
    if (cfg) {
      cfg.microfone_id = "mic-antigo";
      cfg.microfone_rotulo = "antigo-mic";
      cfg.saida_id = "saida-antiga";
      cfg.saida_rotulo = "antiga-saida";
    }
    mainMod.__setCtxAudio(CONTEXTO);
    mainMod.__ultimoEstado.estado = null;
    mainMod.__ultimoEstado.detalhe = null;
    erro = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    erro.mockRestore();
  });

  it("troca de microfone com captura aberta -> aviso de reinicio", async () => {
    fakes.microfoneAberto.mockReturnValue(true);
    await dispararConfigSalva(payload({ microfone_id: "mic-novo", microfone_rotulo: "novo" }));
    expect(fakes.definirMicrofonePreferido).toHaveBeenCalledWith("mic-novo");
    expect(fakes.restaurarPreferencia).toHaveBeenCalledWith(expect.objectContaining({ microfone_id: "mic-novo" }));
    expect(mainMod.__ultimoEstado).toEqual({ estado: "erro", detalhe: AVISO_MIC });
    expect(mainMod.__obterCfg()?.microfone_id).toBe("mic-novo");
  });

  it("troca de microfone com captura fechada -> define sem aviso", async () => {
    fakes.microfoneAberto.mockReturnValue(false);
    await dispararConfigSalva(payload({ microfone_id: "mic-novo2", microfone_rotulo: "novo2" }));
    expect(fakes.definirMicrofonePreferido).toHaveBeenCalledWith("mic-novo2");
    expect(mainMod.__ultimoEstado.estado).not.toBe("erro");
    expect(mainMod.__obterCfg()?.microfone_id).toBe("mic-novo2");
  });

  it("troca de saida para dispositivo especifico -> aplica no contexto", async () => {
    await dispararConfigSalva(payload({ saida_id: "saida-nova", saida_rotulo: "nova" }));
    expect(fakes.aplicarSaidaNoContexto).toHaveBeenCalledWith(CONTEXTO);
    expect(fakes.restaurarPreferencia).toHaveBeenCalledWith(expect.objectContaining({ saida_id: "saida-nova" }));
    expect(mainMod.__ultimoEstado.estado).not.toBe("erro");
    expect(mainMod.__obterCfg()?.saida_id).toBe("saida-nova");
  });

  it("troca de saida para padrao ('') -> aplica setSinkId('') no contexto", async () => {
    await dispararConfigSalva(payload({ saida_id: "", saida_rotulo: "" }));
    expect(fakes.aplicarSaidaNoContexto).toHaveBeenCalledWith(CONTEXTO);
    expect(mainMod.__ultimoEstado.estado).not.toBe("erro");
  });

  it("falha de setSinkId (false) -> estado de erro visivel", async () => {
    fakes.aplicarSaidaNoContexto.mockResolvedValue(false);
    await dispararConfigSalva(payload({ saida_id: "saida-ruim", saida_rotulo: "ruim" }));
    expect(mainMod.__ultimoEstado).toEqual({ estado: "erro", detalhe: AVISO_SAIDA });
    expect(erro).toHaveBeenCalled();
  });

  it("saida recusada por excecao -> estado de erro visivel", async () => {
    fakes.aplicarSaidaNoContexto.mockRejectedValue(new Error("sem dispositivo"));
    await dispararConfigSalva(payload({ saida_id: "saida-ruim2", saida_rotulo: "ruim2" }));
    expect(mainMod.__ultimoEstado).toEqual({ estado: "erro", detalhe: AVISO_SAIDA });
    expect(erro).toHaveBeenCalled();
  });

  it("sem microfone aberto a saida fica para a proxima captura (contexto null)", async () => {
    mainMod.__setCtxAudio(null);
    await dispararConfigSalva(payload({ saida_id: "saida-nova", saida_rotulo: "nova" }));
    expect(fakes.aplicarSaidaNoContexto).not.toHaveBeenCalled();
    expect(mainMod.__ultimoEstado.estado).not.toBe("erro");
    expect(fakes.restaurarPreferencia).toHaveBeenCalled();
    expect(mainMod.__obterCfg()?.saida_id).toBe("saida-nova");
  });

  it("sem troca de dispositivo nao mexe em nada", async () => {
    await dispararConfigSalva(payload({}));
    expect(fakes.definirMicrofonePreferido).not.toHaveBeenCalled();
    expect(fakes.aplicarSaidaNoContexto).not.toHaveBeenCalled();
    expect(fakes.restaurarPreferencia).not.toHaveBeenCalled();
    expect(mainMod.__ultimoEstado.estado).toBeNull();
  });
});
