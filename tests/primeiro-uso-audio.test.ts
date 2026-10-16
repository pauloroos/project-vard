import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { capturarTesteMicrofone } from "../src/audio/teste-microfone";
import { montarEtapaAudio, type DepsEtapaAudio } from "../src/ui/primeiro-uso-audio";
import { CONFIG_PADRAO as PADRAO } from "../src/config/config";
import { ouvirTesteVoz } from "../src/conectores/voz/escolher";
import { montarAssistentePrimeiroUso } from "../src/ui/primeiro-uso";

let processador: { onaudioprocess: ((e: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> };
let parar: ReturnType<typeof vi.fn<() => void>>, fechar: ReturnType<typeof vi.fn<() => Promise<void>>>, gum: ReturnType<typeof vi.fn>;
let contextos: number;
function emitir(valor: number) { processador.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(valor) } }); }
beforeEach(() => {
  vi.useFakeTimers(); contextos = 0;
  parar = vi.fn(); fechar = vi.fn().mockResolvedValue(undefined);
  processador = { onaudioprocess: null, connect: vi.fn(), disconnect: vi.fn() };
  gum = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: parar, addEventListener: vi.fn(), removeEventListener: vi.fn() }] });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: gum, enumerateDevices: async () => [
    { kind: "audioinput", deviceId: "mic-teste", label: "Entrada de teste" },
    { kind: "audiooutput", deviceId: "saida-teste", label: "Saída de teste" },
  ], addEventListener: vi.fn(), removeEventListener: vi.fn() } });
  vi.stubGlobal("AudioContext", class {
    constructor() { contextos++; }
    sampleRate = 48000; state = "running"; destination = {};
    createMediaStreamSource = () => ({ connect: vi.fn(), disconnect: vi.fn() });
    createScriptProcessor = () => processador;
    createGain = () => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() });
    close = fechar;
  });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); document.body.replaceChildren(); });

describe("captura curta do primeiro uso", () => {
  it("seleciona entrada exata, limita a cinco segundos e libera tracks/contexto", async () => {
    const nivel = vi.fn();
    const tarefa = capturarTesteMicrofone("mic-teste", new AbortController().signal, nivel);
    await vi.advanceTimersByTimeAsync(1); emitir(0.2);
    await vi.advanceTimersByTimeAsync(5000);
    const resultado = await tarefa;
    expect(gum.mock.calls[0][0].audio.deviceId).toEqual({ exact: "mic-teste" });
    expect(resultado.pico).toBeCloseTo(0.2); expect(nivel).toHaveBeenCalled();
    expect(new DataView(resultado.wav).getUint32(24, true)).toBe(16000);
    expect(parar).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce();
    expect(processador.onaudioprocess).toBeNull();
  });
  it("nega permissão sem criar contexto", async () => {
    gum.mockRejectedValue(new DOMException("", "NotAllowedError"));
    await expect(capturarTesteMicrofone("", new AbortController().signal, () => {})).rejects.toMatchObject({ name: "NotAllowedError" });
    expect(contextos).toBe(0);
  });
  it("não troca por outra entrada se o dispositivo foi removido", async () => {
    gum.mockRejectedValue(new DOMException("", "NotFoundError"));
    await expect(capturarTesteMicrofone("mic-teste", new AbortController().signal, () => {})).rejects.toMatchObject({ name: "NotFoundError" });
    expect(gum).toHaveBeenCalledOnce();
  });
  it("cancelar antes de conceder permissão solta o stream tardio", async () => {
    let resolver!: (v: unknown) => void;
    gum.mockImplementation(() => new Promise((r) => { resolver = r; }));
    const ac = new AbortController();
    const tarefa = capturarTesteMicrofone("", ac.signal, () => {}).catch((e: unknown) => e);
    ac.abort(); resolver({ getTracks: () => [{ stop: parar }] });
    expect(await tarefa).toMatchObject({ name: "AbortError" });
    expect(parar).toHaveBeenCalledOnce(); expect(contextos).toBe(0);
  });
  it("cancelar captura libera recursos imediatamente", async () => {
    const ac = new AbortController();
    const tarefa = capturarTesteMicrofone("", ac.signal, () => {}).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1); ac.abort();
    expect(await tarefa).toMatchObject({ name: "AbortError" });
    expect(parar).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce();
  });
  it("cancelar durante resume pendente também fecha o contexto", async () => {
    vi.stubGlobal("AudioContext", class { state = "suspended"; resume = () => new Promise<void>(() => {}); close = fechar; });
    const ac = new AbortController();
    let erro: unknown;
    void capturarTesteMicrofone("", ac.signal, () => {}).catch((e: unknown) => { erro = e; });
    await vi.advanceTimersByTimeAsync(1); ac.abort(); await vi.advanceTimersByTimeAsync(1);
    expect(erro).toMatchObject({ name: "AbortError" });
    expect(parar).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce();
  });
});

function montar(extra: Partial<DepsEtapaAudio> = {}) {
  const container = document.createElement("div"); document.body.append(container);
  const restaurar = vi.fn();
  const deps: DepsEtapaAudio = { config: { ...PADRAO, microfone_id: "mic-teste", saida_id: "saida-teste" },
    transcrever: vi.fn().mockResolvedValue("fala sintética"),
    suspenderEscuta: vi.fn().mockResolvedValue(restaurar), salvar: vi.fn().mockResolvedValue(undefined), ...extra };
  const etapa = montarEtapaAudio(container, deps);
  const clicar = (acao: string) => container.querySelector<HTMLButtonElement>(`[data-audio="${acao}"]`)!.click();
  return { container, deps, etapa, clicar, restaurar };
}
describe("etapa de áudio", () => {
  it("silêncio mantém pendência e não envia áudio para transcrição", async () => {
    const t = montar(); await vi.advanceTimersByTimeAsync(1); t.clicar("microfone");
    await vi.advanceTimersByTimeAsync(1); emitir(0); await vi.advanceTimersByTimeAsync(5000);
    expect(t.container.textContent).toContain("silencioso"); expect(t.deps.transcrever).not.toHaveBeenCalled();
    expect(t.restaurar).toHaveBeenCalledOnce(); t.etapa.sair();
  });
  it("nível acima do limite mostra transcrição e salva entrada/saída", async () => {
    const t = montar(); await vi.advanceTimersByTimeAsync(1); t.clicar("microfone");
    await vi.advanceTimersByTimeAsync(1); emitir(0.2); await vi.advanceTimersByTimeAsync(5000);
    expect(t.container.textContent).toContain("fala sintética");
    expect(t.deps.salvar).toHaveBeenLastCalledWith(expect.objectContaining({ microfone_id: "mic-teste", saida_id: "saida-teste", microfone_testado: true, voz_ouvida: false }));
    expect(t.restaurar).toHaveBeenCalledOnce(); t.etapa.sair();
  });
  it("permissão negada orienta configurações do Windows e permite tentar de novo", async () => {
    gum.mockRejectedValue(new DOMException("", "NotAllowedError"));
    const t = montar(); await vi.advanceTimersByTimeAsync(1); t.clicar("microfone"); await vi.advanceTimersByTimeAsync(1);
    expect(t.container.textContent).toContain("Windows");
    expect(t.container.querySelector<HTMLButtonElement>('[data-audio="microfone"]')!.disabled).toBe(false);
    expect(t.restaurar).toHaveBeenCalledOnce(); t.etapa.sair();
  });
  it("saída inexistente impede reprodução e mantém confirmação pendente", async () => {
    const t = montar({ config: { ...PADRAO, saida_id: "removida" } });
    await vi.advanceTimersByTimeAsync(1); t.clicar("voz"); await vi.advanceTimersByTimeAsync(1);
    expect(t.container.textContent).toContain("não encontrada"); expect(contextos).toBe(0); t.etapa.sair();
  });
  it("TTS indisponível não faz fallback nem trava a etapa", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("fora")));
    const t = montar({ config: { ...PADRAO, voz_url: "http://127.0.0.1:18765", saida_id: "" } });
    await vi.advanceTimersByTimeAsync(1); t.clicar("voz"); await vi.advanceTimersByTimeAsync(1);
    expect(t.container.textContent).toContain("indisponível"); expect(t.restaurar).toHaveBeenCalledOnce(); t.etapa.sair();
  });
  it("sair cancela captura, restaura escuta e ignora resultado tardio", async () => {
    const t = montar(); await vi.advanceTimersByTimeAsync(1); t.clicar("microfone");
    await vi.advanceTimersByTimeAsync(1); t.etapa.sair(); await vi.advanceTimersByTimeAsync(1);
    expect(parar).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce();
    expect(t.restaurar).toHaveBeenCalledOnce(); expect(t.deps.transcrever).not.toHaveBeenCalled();
  });
  it("cancelar permite reiniciar sem misturar resultados", async () => {
    const t = montar(); await vi.advanceTimersByTimeAsync(1); t.clicar("microfone");
    await vi.advanceTimersByTimeAsync(1); t.clicar("cancelar"); await vi.advanceTimersByTimeAsync(1);
    t.clicar("microfone"); await vi.advanceTimersByTimeAsync(1); emitir(0.3); await vi.advanceTimersByTimeAsync(5000);
    expect(t.container.textContent).toContain("fala sintética"); expect(parar).toHaveBeenCalledTimes(2); t.etapa.sair();
  });
  it("escolha de voz Kokoro é salva e invalida confirmação anterior", async () => {
    const t = montar({ config: { ...PADRAO, voz_provedor: "openjarvis" } });
    await vi.advanceTimersByTimeAsync(1);
    const voz = t.container.querySelector<HTMLSelectElement>('[data-audio="voz-escolhida"]')!;
    expect(voz).not.toBeNull();
    voz.value = "pf_dora"; voz.dispatchEvent(new Event("change")); await vi.advanceTimersByTimeAsync(1);
    expect(t.deps.salvar).toHaveBeenLastCalledWith(expect.objectContaining({ voz_id: "pf_dora", voz_ouvida: false }));
    t.etapa.sair();
  });
});

describe("reprodução e confirmação humana", () => {
  function instalarSaida() {
    const eventos: string[] = [];
    let terminar!: () => void;
    const fonte = { buffer: null, onended: null as (() => void) | null,
      connect: vi.fn(), disconnect: vi.fn(), start: () => { eventos.push("tocando"); terminar = () => fonte.onended?.(); }, stop: vi.fn() };
    const sink = vi.fn().mockImplementation(async (id: string) => { eventos.push(id); });
    vi.stubGlobal("AudioContext", class {
      state = "running"; destination = {};
      setSinkId = sink; createBufferSource = () => fonte;
      decodeAudioData = async () => ({});
      close = async () => { this.state = "closed"; fechar(); };
    });
    const buscar = vi.fn().mockResolvedValue(new Response(new Uint8Array([0, 0, 1, 0]), { headers: { "X-Taxa": "24000" } }));
    vi.stubGlobal("fetch", buscar);
    return { eventos, fonte, sink, buscar, terminar: () => terminar() };
  }
  it("PCM usa voz escolhida e setSinkId antes de tocar, sem presumir ouvido", async () => {
    const audio = instalarSaida();
    const t = montar({ config: { ...PADRAO, voz_provedor: "propria", voz_propria: "voz-teste", voz_url: "http://127.0.0.1:18765", saida_id: "saida-teste" } });
    await vi.advanceTimersByTimeAsync(1); t.clicar("voz"); await vi.advanceTimersByTimeAsync(1);
    expect(audio.eventos).toEqual(["saida-teste", "tocando"]);
    expect(JSON.parse(audio.buscar.mock.calls[0][1].body)).toMatchObject({ texto: "O teste de voz está funcionando", voz: "voz-teste" });
    audio.terminar(); await vi.advanceTimersByTimeAsync(1);
    expect(t.deps.salvar).toHaveBeenLastCalledWith(expect.objectContaining({ voz_ouvida: false }));
    t.clicar("confirmar"); await vi.advanceTimersByTimeAsync(1);
    expect(t.deps.salvar).toHaveBeenLastCalledWith(expect.objectContaining({ voz_ouvida: true }));
    expect(fechar).toHaveBeenCalledOnce(); t.etapa.sair();
  });
  it("falha no setSinkId fecha contexto e não toca no padrão", async () => {
    const audio = instalarSaida(); audio.sink.mockRejectedValue(new Error("removido"));
    await expect(ouvirTesteVoz({ ...PADRAO, voz_url: "http://127.0.0.1:18765" }, "saida-teste", new AbortController().signal)).rejects.toThrow();
    expect(audio.eventos).toEqual([]); expect(fechar).toHaveBeenCalledOnce();
  });
  it("cancelar reprodução para a fonte e fecha contexto", async () => {
    const audio = instalarSaida(); const ac = new AbortController();
    const p = ouvirTesteVoz({ ...PADRAO, voz_url: "http://127.0.0.1:18765" }, "", ac.signal).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1); ac.abort();
    expect(await p).toMatchObject({ name: "AbortError" });
    expect(audio.fonte.stop).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce();
  });
  it("provedor de nuvem sem chave não chama outro provedor", async () => {
    const audio = instalarSaida();
    await expect(ouvirTesteVoz({ ...PADRAO, voz_provedor: "gemini", gemini_chave: "" }, "", new AbortController().signal)).rejects.toThrow();
    expect(audio.buscar).not.toHaveBeenCalled();
  });
});

describe("ligação da etapa no assistente", () => {
  function servidorEstado(concluido = false) {
    let estado = { schema: 1, etapa: "audio", concluido, pendencias: ["microfone_nao_testado", "voz_nao_testada"] };
    const buscar = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") estado = { ...estado, ...JSON.parse(String(init.body)) };
      return { ok: true, json: async () => ({ ...estado }) };
    });
    vi.stubGlobal("fetch", buscar); return buscar;
  }
  it("monta áudio, persiste pendências e libera recursos ao avançar", async () => {
    const buscar = servidorEstado();
    const restaurar = vi.fn(); const salvar = vi.fn().mockResolvedValue(undefined);
    const raiz = document.createElement("div"); document.body.append(raiz);
    const limpar = await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:18765", audio: {
      config: { ...PADRAO }, transcrever: async () => "frase de teste", suspenderEscuta: async () => restaurar, salvar,
    } });
    await vi.advanceTimersByTimeAsync(1);
    expect(raiz.querySelector('[data-audio="microfone"]')).not.toBeNull();
    raiz.querySelector<HTMLButtonElement>('[data-audio="microfone"]')!.click();
    await vi.advanceTimersByTimeAsync(1);
    raiz.querySelector<HTMLButtonElement>('#primeiro-uso-proximo')!.click(); await vi.advanceTimersByTimeAsync(1);
    expect(parar).toHaveBeenCalledOnce(); expect(fechar).toHaveBeenCalledOnce(); expect(restaurar).toHaveBeenCalledOnce();
    expect(raiz.querySelector('#primeiro-uso-resumo')!.textContent).toContain("microfone_nao_testado");
    expect(buscar.mock.calls.some((c) => String(c[1]?.body).includes("voz_nao_testada"))).toBe(true);
    limpar?.();
  });
  it("instalação configurada não monta nem consulta áudio e não salva configuração", async () => {
    servidorEstado(true); const salvar = vi.fn(); const suspender = vi.fn();
    const raiz = document.createElement("div");
    const limpar = await montarAssistentePrimeiroUso(raiz, { ponteUrl: "http://127.0.0.1:18765", audio: {
      config: { ...PADRAO }, transcrever: vi.fn(), suspenderEscuta: suspender, salvar,
    } });
    expect(limpar).toBeNull(); expect(raiz.childElementCount).toBe(0);
    expect(suspender).not.toHaveBeenCalled(); expect(salvar).not.toHaveBeenCalled(); expect(gum).not.toHaveBeenCalled();
  });
});
