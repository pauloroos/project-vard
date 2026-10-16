import type { Config } from "../config/config";
import { listarDispositivos } from "../audio/dispositivos";
import { capturarTesteMicrofone } from "../audio/teste-microfone";
import { ouvirTesteVoz } from "../conectores/voz/escolher";
import { Voz } from "../conectores/voz/cliente";
import { VOZES_KOKORO } from "../conectores/voz/kokoro";
import { VOZES_GEMINI } from "../conectores/nuvem/gemini";
import { opcoesDeVoz } from "./aba-voz";

export interface ResultadoEtapaAudio {
  microfone_id: string; saida_id: string; voz_id: string;
  microfone_testado: boolean; voz_ouvida: boolean;
}
export interface DepsEtapaAudio {
  config: Config;
  /** O mesmo ouvido da aplicação, sem disparar comandos por nome de chamada. */
  transcrever: (wav: ArrayBuffer, sinal: AbortSignal) => Promise<string>;
  /** Retorna uma restauração do estado anterior, sem persistir mudo na configuração. */
  suspenderEscuta: () => Promise<() => void>;
  salvar: (resultado: ResultadoEtapaAudio) => Promise<void>;
  resultadoInicial?: Pick<ResultadoEtapaAudio, "microfone_testado" | "voz_ouvida">;
}

/** Etapa reutilizável nas telas de voz e teste do assistente. Sair é obrigatório ao navegar. */
export function montarEtapaAudio(container: HTMLElement, deps: DepsEtapaAudio) {
  container.innerHTML = `<p>Escolha os dispositivos. O teste de microfone dura até 5 segundos.</p>
    <label>Microfone<select data-audio="entrada"></select></label>
    <label>Saída de áudio<select data-audio="saida"></select></label>
    <label>Voz<select data-audio="voz-escolhida"></select></label>
    <button type="button" data-audio="listar-vozes">Carregar vozes do serviço próprio</button>
    <p>A voz selecionada nas configurações será usada. Provedores na nuvem recebem a frase somente quando escolhidos.</p>
    <button type="button" data-audio="microfone">Testar microfone</button>
    <meter data-audio="nivel" min="0" max="1" aria-label="Nível do microfone"></meter>
    <button type="button" data-audio="voz">Ouvir teste</button>
    <button type="button" data-audio="confirmar" disabled>Sim, ouvi o teste</button>
    <button type="button" data-audio="cancelar">Cancelar teste</button>
    <p role="status" data-audio="status">Microfone e saída ainda não testados. Você pode pular esta etapa.</p>`;
  const el = <T extends HTMLElement>(id: string) => container.querySelector<T>(`[data-audio="${id}"]`)!;
  const entrada = el<HTMLSelectElement>("entrada"), saida = el<HTMLSelectElement>("saida");
  const voz = el<HTMLSelectElement>("voz-escolhida");
  const provedor = deps.config.voz_provedor;
  const vozInicial = provedor === "propria" ? deps.config.voz_propria : provedor === "gemini" ? deps.config.gemini_voz || "Kore"
    : provedor === "elevenlabs" ? deps.config.elevenlabs_voz : deps.config.voz;
  const vozesBase: [string, string][] = provedor === "openjarvis" ? VOZES_KOKORO.map((v) => [v.id, v.rotulo])
    : provedor === "gemini" ? VOZES_GEMINI.map((v) => [v, v]) : [["", "Voz atual do serviço"]];
  const preencherVozes = (base: [string, string][], atual: string) => {
    voz.replaceChildren(...opcoesDeVoz(base, atual).map(([id, rotulo]) => new Option(rotulo, id)));
    voz.value = atual;
  };
  preencherVozes(vozesBase, vozInicial);
  el<HTMLButtonElement>("listar-vozes").hidden = provedor !== "propria";
  const confirmar = el<HTMLButtonElement>("confirmar");
  const status = (texto: string) => { if (!saiu) el("status").textContent = texto; };
  let saiu = false, operacao: AbortController | null = null;
  let microfoneTestado = deps.resultadoInicial?.microfone_testado ?? false;
  let vozOuvida = deps.resultadoInicial?.voz_ouvida ?? false;
  let restaurarAtual: (() => void) | null = null;
  const restaurar = () => { const f = restaurarAtual; restaurarAtual = null; f?.(); };
  const resultado = (): ResultadoEtapaAudio => ({ microfone_id: entrada.value, saida_id: saida.value,
    voz_id: voz.value, microfone_testado: microfoneTestado, voz_ouvida: vozOuvida });
  const salvar = async () => { if (!saiu) await deps.salvar(resultado()); };
  function preencher(sel: HTMLSelectElement, id: string, lista: { deviceId: string; label: string }[]) {
    sel.replaceChildren(new Option("Padrão do sistema", ""), ...lista.map((d) => new Option(d.label, d.deviceId)));
    if (id && !lista.some((d) => d.deviceId === id)) sel.add(new Option("Dispositivo não encontrado", id));
    sel.value = id;
  }
  preencher(entrada, deps.config.microfone_id, []); preencher(saida, deps.config.saida_id, []);
  void Promise.all([listarDispositivos("audioinput"), listarDispositivos("audiooutput")]).then(([m, s]) => {
    if (!saiu) { preencher(entrada, entrada.value, m); preencher(saida, saida.value, s); }
  });
  function cancelar() {
    operacao?.abort(); operacao = null; restaurar();
    confirmar.disabled = true;
    el<HTMLButtonElement>("microfone").disabled = false; el<HTMLButtonElement>("voz").disabled = false;
  }
  async function testar(tipo: "microfone" | "voz") {
    cancelar(); const ac = new AbortController(); operacao = ac;
    const vigente = () => !saiu && operacao === ac && !ac.signal.aborted;
    confirmar.disabled = true;
    el<HTMLButtonElement>("microfone").disabled = true; el<HTMLButtonElement>("voz").disabled = true;
    if (tipo === "microfone") microfoneTestado = false; else vozOuvida = false;
    try {
      await salvar();
      if (!vigente()) return;
      const volta = await deps.suspenderEscuta();
      if (!vigente()) { volta(); return; }
      restaurarAtual = volta;
      // Seleção explícita nunca cai silenciosamente no dispositivo padrão.
      const id = tipo === "microfone" ? entrada.value : saida.value;
      const lista = await listarDispositivos(tipo === "microfone" ? "audioinput" : "audiooutput");
      if (!vigente()) return;
      if (id && !lista.some((d) => d.deviceId === id)) throw new DOMException("", "NotFoundError");
      if (tipo === "microfone") {
        status("Fale uma frase curta. Capturando por até 5 segundos…");
        const captura = await capturarTesteMicrofone(id, ac.signal, (n) => { if (vigente()) el<HTMLMeterElement>("nivel").value = n; });
        if (!vigente()) return;
        if (captura.pico < Math.max(0.001, deps.config.limiar_vad)) { status("Microfone silencioso. Confira o nível e a permissão nas configurações do Windows."); return; }
        status("Transcrevendo o teste…");
        const texto = await deps.transcrever(captura.wav, ac.signal);
        if (!vigente()) return;
        microfoneTestado = !!texto.trim();
        status(microfoneTestado ? `Transcrição: ${texto}` : "Não houve transcrição. Tente novamente ou pule.");
      } else {
        status("Sintetizando e reproduzindo na saída escolhida…");
        const campoVoz = provedor === "propria" ? "voz_propria" : provedor === "gemini" ? "gemini_voz" : provedor === "elevenlabs" ? "elevenlabs_voz" : "voz";
        await ouvirTesteVoz({ ...deps.config, [campoVoz]: voz.value }, id, ac.signal);
        if (!vigente()) return;
        status("Reprodução concluída. Você ouviu o teste? A confirmação humana continua pendente.");
        confirmar.disabled = false;
      }
      await salvar();
    } catch (erro) {
      if (!vigente()) return;
      const nome = erro && typeof erro === "object" && "name" in erro ? erro.name : "";
      status(nome === "NotAllowedError" ? "Permissão negada. Libere o microfone nas configurações de privacidade do Windows."
        : nome === "NotFoundError" ? "Entrada ou saída não encontrada. Conecte o dispositivo, confira as configurações do Windows ou pule."
        : tipo === "voz" ? "Voz indisponível. Confira o provedor nas configurações ou pule."
        : "Não consegui testar o microfone. Confira as configurações do Windows ou pule.");
    } finally {
      if (operacao === ac) { restaurar(); operacao = null;
        el<HTMLButtonElement>("microfone").disabled = false; el<HTMLButtonElement>("voz").disabled = false; }
    }
  }
  el("microfone").onclick = () => { void testar("microfone"); };
  el("voz").onclick = () => { void testar("voz"); };
  el("cancelar").onclick = () => { cancelar(); status("Teste cancelado. Você pode reiniciar ou pular."); };
  confirmar.onclick = () => { vozOuvida = true; confirmar.disabled = true; status("Saída confirmada por você."); void salvar().catch(() => status("Não consegui salvar a confirmação. Tente novamente.")); };
  entrada.onchange = () => { cancelar(); microfoneTestado = false; void salvar().catch(() => status("Não consegui salvar a seleção.")); };
  saida.onchange = () => { cancelar(); vozOuvida = false; void salvar().catch(() => status("Não consegui salvar a seleção.")); };
  voz.onchange = () => { cancelar(); vozOuvida = false; void salvar().catch(() => status("Não consegui salvar a voz.")); };
  el("listar-vozes").onclick = () => {
    if (!deps.config.voz_url) { status("Configure o serviço de voz nas configurações ou pule."); return; }
    void new Voz(deps.config.voz_url).vozes().then(({ vozes }) => {
      if (saiu) return;
      preencherVozes([["", "Voz atual do serviço"], ...vozes.map((v): [string, string] => [v, v])], voz.value);
      if (!vozes.length) status("Voz indisponível. Confira o serviço nas configurações ou pule.");
    });
  };
  return { cancelar, sair: () => { saiu = true; cancelar(); }, resultado };
}
