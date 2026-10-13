import type { Config } from "../config/config";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import { ElevenLabs } from "../conectores/nuvem/elevenlabs";
import { VOZES_GEMINI } from "../conectores/nuvem/gemini";
import { Voz } from "../conectores/voz/cliente";
import { FRASE_AMOSTRA, PROVEDORES_VOZ, criarFonteDeVoz, type ProvedorVoz } from "../conectores/voz/escolher";
import { VOZES_KOKORO } from "../conectores/voz/kokoro";

export interface DepsAbaVoz {
  /** Cliente do OpenJarvis no endereço salvo (para ouvir a voz Kokoro). */
  criarOj: () => OpenJarvis;
  /** Velocidade que está no formulário agora. */
  velocidade: () => number;
  dizer: (texto: string, ruim?: boolean) => void;
}

export type CamposVoz = Pick<Config, "voz_provedor" | "voz_propria" | "voz" | "elevenlabs_chave" | "elevenlabs_voz" | "gemini_chave" | "gemini_voz">;

const ROTULO_PROVEDOR: Record<ProvedorVoz, string> = {
  propria: "Voz própria (XTTS, no seu computador)",
  openjarvis: "Voz do OpenJarvis (Kokoro, no seu computador)",
  elevenlabs: "ElevenLabs (nuvem, opcional, precisa de chave)",
  gemini: "Gemini (nuvem, opcional, precisa de chave)",
};
const OUTRO = "__outro__";

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Opções de um select de voz; a voz atual que não está na lista é acrescentada (não se perde em silêncio). */
export function opcoesDeVoz(base: [string, string][], atual: string, rotuloAusente: (v: string) => string = (v) => v): [string, string][] {
  return atual && !base.some(([v]) => v === atual) ? [...base, [atual, rotuloAusente(atual)]] : base;
}

/** Toca um WAV no painel (a janela de configurações tem o próprio AudioContext). */
async function tocarWav(wav: ArrayBuffer): Promise<void> {
  const ctx = new AudioContext();
  try {
    const buf = await ctx.decodeAudioData(wav.slice(0));
    const fonte = ctx.createBufferSource();
    fonte.buffer = buf;
    fonte.connect(ctx.destination);
    await new Promise<void>((ok) => { fonte.onended = () => ok(); fonte.start(); });
  } finally { void ctx.close().catch(() => {}); }
}

/** Aba Voz: provedor (própria, OpenJarvis, ElevenLabs, Gemini), a voz de cada um e o botão Ouvir. Chaves só em campos de senha, nunca em log. */
export class AbaVoz {
  constructor(private raiz: HTMLElement, private cfg: Config, private deps: DepsAbaVoz) {}

  private el(id: string): HTMLInputElement { return this.raiz.querySelector<HTMLInputElement>(`#cfg-${id}`)!; }
  private sel(id: string): HTMLSelectElement { return this.raiz.querySelector<HTMLSelectElement>(`#cfg-${id}`)!; }

  montar() {
    const c = this.cfg;
    const kokoroConhecida = VOZES_KOKORO.some((v) => v.id === c.voz);
    this.raiz.innerHTML = `
      <fieldset><legend>Provedor</legend>
        ${PROVEDORES_VOZ.map((p) => `<label class="marca"><input type="radio" name="voz_provedor" id="cfg-prov-${p}" value="${p}" ${p === c.voz_provedor ? "checked" : ""}> ${ROTULO_PROVEDOR[p]}</label>`).join("")}
      </fieldset>
      <div data-prov="propria">
        <label>Endereço do serviço de voz (vazio desliga)<input id="cfg-voz_url" type="text" value="${esc(c.voz_url)}"></label>
        <label>Voz<select id="cfg-voz_propria"></select></label>
        <p class="nota" id="cfg-voz_propria_nota"></p>
      </div>
      <div data-prov="openjarvis">
        <label>Voz<select id="cfg-voz_kokoro">${VOZES_KOKORO.map((v) => `<option value="${v.id}" ${v.id === c.voz ? "selected" : ""}>${v.rotulo}</option>`).join("")}<option value="${OUTRO}" ${kokoroConhecida ? "" : "selected"}>Outro id...</option></select></label>
        <label id="cfg-voz_outro_rotulo">Id da voz<input id="cfg-voz_outro" type="text" value="${kokoroConhecida ? "" : esc(c.voz)}"></label>
      </div>
      <div data-prov="elevenlabs">
        <label>Chave da API<input id="cfg-elevenlabs_chave" type="password" autocomplete="off" value="${esc(c.elevenlabs_chave)}"></label>
        <label>Voz da conta<select id="cfg-elevenlabs_voz"><option value="">${c.elevenlabs_voz ? esc(c.elevenlabs_voz) : "(carregue as vozes)"}</option></select></label>
        <button id="cfg-elevenlabs_carregar" type="button">Carregar vozes</button>
        <label>Ou o id da voz<input id="cfg-elevenlabs_voz_id" type="text" value="${esc(c.elevenlabs_voz)}"></label>
        <p class="nota">Só fala com a ElevenLabs quando este provedor está escolhido; o texto das falas vai para a nuvem.</p>
      </div>
      <div data-prov="gemini">
        <label>Chave da API<input id="cfg-gemini_chave" type="password" autocomplete="off" value="${esc(c.gemini_chave)}"></label>
        <label>Voz<select id="cfg-gemini_voz"></select></label>
        <p class="nota">Só fala com o Google quando este provedor está escolhido; o Gemini ignora a velocidade.</p>
      </div>
      <button id="cfg-ouvir" type="button">Ouvir</button>`;
    // Semeia já na montagem: um Salvar antes de o /vozes responder não apaga a escolha.
    this.preencher(this.sel("voz_propria"), opcoesDeVoz([["", "A voz atual do serviço"]], c.voz_propria), c.voz_propria);
    this.preencher(this.sel("gemini_voz"), opcoesDeVoz(VOZES_GEMINI.map((v): [string, string] => [v, v]), c.gemini_voz, (v) => `${v} (fora da lista)`), c.gemini_voz);
    for (const r of this.raiz.querySelectorAll<HTMLInputElement>('input[name="voz_provedor"]')) r.addEventListener("change", () => this.mostrar());
    this.sel("voz_kokoro").addEventListener("change", () => this.mostrar());
    this.sel("elevenlabs_voz").addEventListener("change", () => { const v = this.sel("elevenlabs_voz").value; if (v) this.el("elevenlabs_voz_id").value = v; });
    this.el("voz_url").addEventListener("change", () => { void this.carregarPropria(); });
    this.raiz.querySelector("#cfg-elevenlabs_carregar")!.addEventListener("click", () => { void this.carregarElevenLabs(); });
    this.raiz.querySelector("#cfg-ouvir")!.addEventListener("click", () => { void this.ouvir(); });
    this.mostrar();
    void this.carregarPropria();
  }

  private preencher(sel: HTMLSelectElement, opcoes: [string, string][], marcada: string) {
    sel.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor, false, valor === marcada)));
  }

  /** Endereço do serviço de voz como está no formulário. */
  vozUrl(): string { return this.el("voz_url").value.trim(); }

  private provedor(): ProvedorVoz {
    const r = this.raiz.querySelector<HTMLInputElement>('input[name="voz_provedor"]:checked');
    return (PROVEDORES_VOZ as readonly string[]).includes(r?.value ?? "") ? (r!.value as ProvedorVoz) : this.cfg.voz_provedor;
  }

  private mostrar() {
    const p = this.provedor();
    for (const d of this.raiz.querySelectorAll<HTMLElement>("div[data-prov]")) d.hidden = d.dataset.prov !== p;
    this.raiz.querySelector<HTMLElement>("#cfg-voz_outro_rotulo")!.hidden = this.sel("voz_kokoro").value !== OUTRO;
  }

  /** Preenche a lista de vozes do serviço próprio; fora do ar, deixa uma nota. */
  private async carregarPropria() {
    const sel = this.sel("voz_propria");
    const nota = this.raiz.querySelector<HTMLElement>("#cfg-voz_propria_nota")!;
    const escolhida = sel.options.length ? sel.value : this.cfg.voz_propria;
    const url = this.vozUrl();
    const { vozes, atual } = url ? await new Voz(url).vozes() : { vozes: [], atual: "" };
    this.preencher(sel, opcoesDeVoz([["", atual ? `A voz atual do serviço (${atual})` : "A voz atual do serviço"], ...vozes.map((v): [string, string] => [v, v])], escolhida), escolhida);
    nota.textContent = vozes.length ? "" : "Voz própria fora do ar; a lista aparece quando ela subir.";
  }

  private async carregarElevenLabs() {
    const chave = this.el("elevenlabs_chave").value.trim();
    if (!chave) { this.deps.dizer("Informe a chave do ElevenLabs para carregar as vozes.", true); return; }
    try {
      const lista = await new ElevenLabs(chave, "x").vozes();
      const atual = this.el("elevenlabs_voz_id").value.trim();
      this.sel("elevenlabs_voz").replaceChildren(...lista.map((v) => new Option(v.nome || v.id, v.id, false, v.id === atual)));
      if (!atual && lista[0]) this.el("elevenlabs_voz_id").value = lista[0].id;
      this.deps.dizer(`${lista.length} vozes carregadas.`);
    } catch (erro) { this.deps.dizer(`Não consegui carregar as vozes: ${erro instanceof Error ? erro.message : "falha"}`, true); }
  }

  /** O que o formulário diz sobre a voz; no OpenJarvis, o id escolhido vai em `voz`. */
  ler(): CamposVoz {
    const kok = this.sel("voz_kokoro").value;
    const voz = kok === OUTRO ? (this.el("voz_outro").value.trim() || this.cfg.voz) : kok;
    return {
      voz_provedor: this.provedor(), voz_propria: this.sel("voz_propria").value, voz,
      elevenlabs_chave: this.el("elevenlabs_chave").value.trim(), elevenlabs_voz: this.el("elevenlabs_voz_id").value.trim(),
      gemini_chave: this.el("gemini_chave").value.trim(), gemini_voz: this.sel("gemini_voz").value,
    };
  }

  /** Motivo para não salvar (provedor de nuvem sem chave ou voz), ou null. */
  erro(): string | null {
    const c = this.ler();
    if (c.voz_provedor === "elevenlabs" && (!c.elevenlabs_chave || !c.elevenlabs_voz)) return "Informe a chave do ElevenLabs e a voz, ou escolha outro provedor.";
    if (c.voz_provedor === "gemini" && !c.gemini_chave) return "Informe a chave do Gemini, ou escolha outro provedor.";
    return null;
  }

  private async ouvir() {
    const falha = this.erro();
    if (falha) { this.deps.dizer(falha, true); return; }
    const c = this.ler();
    const vel = this.deps.velocidade();
    this.deps.dizer("Sintetizando...");
    try {
      const fonte = c.voz_provedor === "openjarvis" ? null : criarFonteDeVoz({ ...c, voz_url: this.vozUrl() });
      if (c.voz_provedor !== "openjarvis" && !fonte) { this.deps.dizer("Esse provedor está desligado (sem endereço ou chave).", true); return; }
      const wav = fonte ? await fonte.falarWav(FRASE_AMOSTRA, vel, 20000) : await this.deps.criarOj().sintetizar(FRASE_AMOSTRA, c.voz, vel);
      this.deps.dizer("Tocando.");
      await tocarWav(wav);
      this.deps.dizer("");
    } catch (erro) { this.deps.dizer(`Não consegui ouvir: ${erro instanceof Error ? erro.message : "falha"}`, true); }
  }
}
