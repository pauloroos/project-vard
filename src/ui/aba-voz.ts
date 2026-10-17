/**
 * Seção Voz (0.9.4): lista de seleção para voz principal e reserva com botão Ouvir amostra,
 * blocos de serviço claros (local, ElevenLabs, Gemini) e cadastro em modal.
 * Reserva automática: se a principal falhar, o Vard fala pela reserva configurada.
 */
import type { Config } from "../config/config";
import { PAINEIS_PADRAO, gravarPaineis, lerPaineis, type PaineisConfig } from "../config/paineis";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import { ElevenLabs } from "../conectores/nuvem/elevenlabs";
import { VOZES_GEMINI } from "../conectores/nuvem/gemini";
import { Voz } from "../conectores/voz/cliente";
import { FRASE_AMOSTRA, type ProvedorVoz } from "../conectores/voz/escolher";
import { VOZES_KOKORO, VOZES_EDGE_PT_BR, VOZES_PIPER_PT_BR } from "../conectores/voz/kokoro";
import { listarDispositivos, definirPreferencia, obterPreferencia } from "../audio/dispositivos";
import { abrirModalVoz, motorDoTipo, vozesCadastradas, type CamposVozCadastrada, type VozCadastrada } from "./paineis-vozes";
import "./estilos/voz.css";

export interface DepsAbaVoz {
  criarOj: () => OpenJarvis;
  velocidade: () => number;
  dizer: (texto: string, ruim?: boolean) => void;
}

export type CamposVoz = Pick<Config,
  | "vad" | "interromper_ao_falar"
  | "voz_provedor" | "voz_motor" | "voz_propria" | "voz"
  | "elevenlabs_chave" | "elevenlabs_voz"
  | "gemini_chave" | "gemini_voz"
  | "voz_reserva_provedor" | "voz_reserva_motor" | "voz_reserva_id"
>;

export const MOTORES_PROPRIA = [
  { id: "", rotulo: "Automático (o serviço escolhe)" },
  { id: "kokoro", rotulo: "Kokoro (local, sem rede)" },
  { id: "edge", rotulo: "Edge (internet, Microsoft)" },
  { id: "piper", rotulo: "Piper (local, CPU)" },
  { id: "xtts", rotulo: "XTTS (local, GPU)" },
] as const;

export const VOZES_POR_MOTOR: Record<string, readonly { id: string; rotulo: string }[]> = {
  kokoro: VOZES_KOKORO,
  edge: VOZES_EDGE_PT_BR,
  piper: VOZES_PIPER_PT_BR,
};

const AVISO_SERVICOS = "Os serviços do Vard estão desligados — abra pelo atalho do Vard ou ligue em Sistema.";
type EstadoServico = "no-ar" | "fora" | "desligado";

interface OpcaoVoz {
  valor: string;
  rotulo: string;
  grupo: string;
  provedor: ProvedorVoz | "openjarvis";
  motor?: string;
}

/** Cópia descartável do padrão. */
function paineisEmBranco(): PaineisConfig {
  return { ...PAINEIS_PADRAO, provedores: [], mcps: [], agentes: { ...PAINEIS_PADRAO.agentes } };
}

/** Voz do Gemini que o select marca: a salva ou, vazia, a Kore. */
export function vozGeminiMarcada(salva: string): string { return salva.trim() || "Kore"; }

/** Motivo para não salvar e os campos a marcar; null quando está tudo certo. */
export function problemaDeVoz(c: Pick<CamposVoz, "voz_provedor" | "elevenlabs_chave" | "elevenlabs_voz" | "gemini_chave">): { texto: string; campos: string[] } | null {
  if (c.voz_provedor === "elevenlabs" && (!c.elevenlabs_chave || !c.elevenlabs_voz)) {
    return { texto: "Informe a chave do ElevenLabs e a voz, ou escolha outro provedor.", campos: [...(c.elevenlabs_chave ? [] : ["elevenlabs_chave"]), ...(c.elevenlabs_voz ? [] : ["elevenlabs_voz_id"])] };
  }
  if (c.voz_provedor === "gemini" && !c.gemini_chave) return { texto: "Informe a chave do Gemini, ou escolha outro provedor.", campos: ["gemini_chave"] };
  return null;
}

/** Toca um WAV no painel. */
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

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Gera opções de select a partir de uma base + valor atual; se o atual não estiver na lista, acrescenta. */
export function opcoesDeVoz(
  base: [string, string][],
  atual: string,
  rotuloAusente?: (v: string) => string,
): [string, string][] {
  if (!atual || base.some(([v]) => v === atual)) return base;
  const rotulo = rotuloAusente ? rotuloAusente(atual) : atual;
  return [...base, [atual, rotulo]];
}

async function buscarJson<T>(url: string, prazoMs: number): Promise<T | null> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), prazoMs);
  try {
    const r = await fetch(url, { signal: ac.signal });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch { return null; } finally { clearTimeout(t); }
}

/** Seção Voz: listas de seleção principal/reserva, blocos de serviço e dispositivos. */
export class AbaVoz {
  private cfgPaineis: PaineisConfig = paineisEmBranco();
  private estado: EstadoServico = "fora";
  private motores = { xtts: false, kokoro: false, edge: false, piper: false };
  private vozesServico: string[] = [];
  private vozesElevenLabs: { id: string; nome: string }[] = [];
  private aviso!: HTMLElement;
  private avisoDetalhe!: HTMLElement;
  private selPrincipal!: HTMLSelectElement;
  private selReserva!: HTMLSelectElement;
  private btnAmostraPrincipal!: HTMLButtonElement;
  private btnAmostraReserva!: HTMLButtonElement;

  constructor(private raiz: HTMLElement, private cfg: Config, private deps: DepsAbaVoz) {}

  montar() {
    this.raiz.insertAdjacentHTML("afterbegin", `
      <div id="cfg-voz-aviso" class="voz-aviso" hidden>
        <strong id="cfg-voz-aviso-texto"></strong>
        <p id="cfg-voz-aviso-detalhe"></p>
      </div>
      <fieldset><legend>Voz principal</legend>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Voz usada para falar</span>
          <div class="voz-select-linha">
            <select id="cfg-voz-principal"></select>
            <button type="button" id="cfg-voz-amostra-principal" class="voz-btn-amostra">Ouvir amostra</button>
          </div>
        </label>
      </fieldset>
      <fieldset><legend>Voz de reserva</legend>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Se a principal falhar, o Vard fala com esta</span>
          <div class="voz-select-linha">
            <select id="cfg-voz-reserva"></select>
            <button type="button" id="cfg-voz-amostra-reserva" class="voz-btn-amostra">Ouvir amostra</button>
          </div>
        </label>
      </fieldset>
      <fieldset><legend>Ouvido</legend>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Detector de voz</span>
          <select id="cfg-vad">
            <option value="energia">Energia (leve)</option>
            <option value="silero">Silero (preciso)</option>
          </select>
        </label>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Interromper ao falar</span>
          <input type="checkbox" id="cfg-interromper_ao_falar">
        </label>
      </fieldset>
      <fieldset><legend>Serviços e chaves</legend>
        <div id="cfg-voz-servicos"></div>
      </fieldset>
      <div id="cfg-voz-cadastradas"></div>
    `);
    this.aviso = this.raiz.querySelector("#cfg-voz-aviso")!;
    this.avisoDetalhe = this.raiz.querySelector("#cfg-voz-aviso-detalhe")!;
    this.selPrincipal = this.raiz.querySelector("#cfg-voz-principal")!;
    this.selReserva = this.raiz.querySelector("#cfg-voz-reserva")!;
    this.btnAmostraPrincipal = this.raiz.querySelector("#cfg-voz-amostra-principal")!;
    this.btnAmostraReserva = this.raiz.querySelector("#cfg-voz-amostra-reserva")!;

    this.selPrincipal.addEventListener("change", () => { this.aplicarSelecaoPrincipal(); this.desenharServicos(); });
    this.selReserva.addEventListener("change", () => { this.aplicarSelecaoReserva(); });
    this.btnAmostraPrincipal.addEventListener("click", () => { void this.amostraSelecionada("principal"); });
    this.btnAmostraReserva.addEventListener("click", () => { void this.amostraSelecionada("reserva"); });
    this.preencherListas(); // já com o que não depende do serviço; atualizar() completa
    this.desenharServicos();
  }

  /** Estado do serviço de voz + vozes; redesenha listas. */
  async atualizar(): Promise<void> {
    const url = this.cfg.voz_url?.trim();
    if (!url) {
      this.estado = "desligado";
      this.motores = { xtts: false, kokoro: false, edge: false, piper: false };
      this.vozesServico = [];
    } else {
      const base = url.replace(/\/+$/, "");
      const saude = await buscarJson<{ xtts?: unknown; kokoro?: unknown; edge?: unknown; piper?: unknown }>(`${base}/saude`, 3000);
      if (!saude) {
        this.estado = "fora";
        this.motores = { xtts: false, kokoro: false, edge: false, piper: false };
        this.vozesServico = [];
      } else {
        this.estado = "no-ar";
        this.motores = { xtts: saude.xtts === true, kokoro: saude.kokoro === true, edge: saude.edge === true, piper: saude.piper === true };
        // Lista de vozes falhando não pode esvaziar a tela: sem ela, as listas ficam com o que não depende do serviço.
        try { this.vozesServico = (await new Voz(url).vozes()).vozes; } catch { this.vozesServico = []; }
      }
    }
    try { this.cfgPaineis = await lerPaineis(); } catch { this.cfgPaineis = paineisEmBranco(); }
    this.atualizarAviso();
    this.preencherListas();
    this.desenharServicos();
    this.desenharCadastradas();
  }

  private atualizarAviso() {
    const texto = this.raiz.querySelector<HTMLElement>("#cfg-voz-aviso-texto")!;
    if (this.estado === "fora") {
      texto.textContent = AVISO_SERVICOS;
      this.avisoDetalhe.textContent = "O serviço de voz não respondeu; as vozes locais aparecem quando ele subir.";
      this.aviso.hidden = false;
    } else if (this.estado === "desligado") {
      texto.textContent = "O serviço de voz está desligado.";
      this.avisoDetalhe.textContent = "Informe o endereço do serviço de voz abaixo para usar as vozes locais.";
      this.aviso.hidden = false;
    } else {
      this.aviso.hidden = true;
    }
  }

  // ---- listas de seleção ---------------------------------------------------
  private opcoesDisponiveis(): OpcaoVoz[] {
    const ops: OpcaoVoz[] = [];
    const fora = this.estado !== "no-ar";
    for (const v of VOZES_KOKORO) {
      ops.push({ valor: `openjarvis:${v.id}`, rotulo: `${v.rotulo} (OpenJarvis)`, grupo: "Kokoro · OpenJarvis", provedor: "openjarvis" });
    }
    if (!fora) {
      if (this.motores.xtts) {
        for (const nome of this.vozesServico) {
          ops.push({ valor: `propria:xtts:${nome}`, rotulo: `${nome} (XTTS, neste PC)`, grupo: "XTTS · neste PC", provedor: "propria", motor: "xtts" });
        }
      }
      if (this.motores.kokoro) {
        for (const v of VOZES_KOKORO) {
          ops.push({ valor: `propria:kokoro:${v.id}`, rotulo: `${v.rotulo} (Kokoro, neste PC)`, grupo: "Kokoro · neste PC", provedor: "propria", motor: "kokoro" });
        }
      }
      if (this.motores.edge) {
        for (const v of VOZES_EDGE_PT_BR) {
          ops.push({ valor: `propria:edge:${v.id}`, rotulo: `${v.rotulo} (Edge, internet)`, grupo: "Edge · neste PC", provedor: "propria", motor: "edge" });
        }
      }
      if (this.motores.piper) {
        for (const v of VOZES_PIPER_PT_BR) {
          ops.push({ valor: `propria:piper:${v.id}`, rotulo: `${v.rotulo} (Piper, local)`, grupo: "Piper · neste PC", provedor: "propria", motor: "piper" });
        }
      }
    }
    for (const v of this.vozesElevenLabs) {
      ops.push({ valor: `elevenlabs:${v.id}`, rotulo: `${v.nome || v.id} (ElevenLabs)`, grupo: "ElevenLabs · nuvem", provedor: "elevenlabs" });
    }
    for (const nome of VOZES_GEMINI) {
      ops.push({ valor: `gemini:${nome}`, rotulo: `${nome} (Gemini)`, grupo: "Gemini · nuvem", provedor: "gemini" });
    }
    for (const p of vozesCadastradas(this.cfgPaineis)) {
      ops.push({ valor: `cadastrada:${p.id}`, rotulo: `${p.nome} (${motorDoTipo(p.tipo)})`, grupo: `${motorDoTipo(p.tipo)} · cadastrada`, provedor: "propria" });
    }
    return ops;
  }

  private preencherListas() {
    const ops = this.opcoesDisponiveis();
    const valorPrincipal = this.valorDaSelecao(this.cfg.voz_provedor, this.cfg.voz_motor, this.cfg.voz_propria, this.cfg.voz, this.cfg.elevenlabs_voz, this.cfg.gemini_voz);
    const valorReserva = this.cfg.voz_reserva_provedor && this.cfg.voz_reserva_provedor !== "nenhuma"
      ? this.valorDaSelecao(this.cfg.voz_reserva_provedor as ProvedorVoz, this.cfg.voz_reserva_motor, this.cfg.voz_reserva_id ?? "", this.cfg.voz_reserva_id ?? "", this.cfg.voz_reserva_provedor === "elevenlabs" ? (this.cfg.voz_reserva_id ?? "") : "", this.cfg.voz_reserva_provedor === "gemini" ? (this.cfg.voz_reserva_id ?? "") : "")
      : "";

    const preencher = (sel: HTMLSelectElement, valorAtual: string, comNenhuma: boolean) => {
      sel.replaceChildren();
      if (comNenhuma) sel.append(new Option("Nenhuma (usa OpenJarvis como último recurso)", "", false, valorAtual === ""));
      const grupos = new Map<string, HTMLOptGroupElement>();
      for (const op of ops) {
        let g = grupos.get(op.grupo);
        if (!g) { g = document.createElement("optgroup"); g.label = op.grupo; sel.append(g); grupos.set(op.grupo, g); }
        g.append(new Option(op.rotulo, op.valor, false, op.valor === valorAtual));
      }
      if (!comNenhuma && !ops.some((o) => o.valor === valorAtual)) {
        // Nada escolhido ainda ("propria::") ou voz salva que sumiu: texto legível, nunca o código interno.
        const nome = valorAtual.split(":").filter(Boolean).slice(1).join(" ");
        const rotulo = nome ? `Voz salva não encontrada: ${nome}` : "Escolha uma voz";
        sel.prepend(new Option(rotulo, valorAtual, false, true));
        sel.value = valorAtual;
      }
    };
    preencher(this.selPrincipal, valorPrincipal, false);
    preencher(this.selReserva, valorReserva, true);
  }

  private valorDaSelecao(provedor: ProvedorVoz | "openjarvis", motor?: string, propria?: string, oj?: string, el?: string, gem?: string): string {
    if (provedor === "openjarvis") return `openjarvis:${oj || this.cfg.voz}`;
    if (provedor === "elevenlabs") return `elevenlabs:${el || ""}`;
    if (provedor === "gemini") return `gemini:${gem || "Kore"}`;
    if (provedor === "propria") return `propria:${motor || ""}:${propria || ""}`;
    return "";
  }

  private aplicarSelecaoPrincipal() {
    const val = this.selPrincipal.value;
    const parsed = this.parseValor(val);
    if (!parsed) return;
    this.cfg.voz_provedor = parsed.provedor === "openjarvis" ? "openjarvis" : parsed.provedor as ProvedorVoz;
    this.cfg.voz_motor = parsed.motor ?? "";
    this.cfg.voz_propria = parsed.id ?? "";
    if (parsed.provedor === "openjarvis") this.cfg.voz = parsed.id ?? this.cfg.voz;
    if (parsed.provedor === "elevenlabs") this.cfg.elevenlabs_voz = parsed.id ?? "";
    if (parsed.provedor === "gemini") this.cfg.gemini_voz = parsed.id ?? "Kore";
    this.deps.dizer(`Voz principal: ${this.selPrincipal.selectedOptions[0]?.textContent ?? ""}`);
  }

  private aplicarSelecaoReserva() {
    const val = this.selReserva.value;
    if (!val) {
      this.cfg.voz_reserva_provedor = "nenhuma";
      this.cfg.voz_reserva_motor = "";
      this.cfg.voz_reserva_id = "";
      this.deps.dizer("Voz de reserva: nenhuma.");
      return;
    }
    const parsed = this.parseValor(val);
    if (!parsed) return;
    this.cfg.voz_reserva_provedor = parsed.provedor === "openjarvis" ? "openjarvis" : parsed.provedor as ProvedorVoz;
    this.cfg.voz_reserva_motor = parsed.motor ?? "";
    this.cfg.voz_reserva_id = parsed.id ?? "";
    this.deps.dizer(`Voz de reserva: ${this.selReserva.selectedOptions[0]?.textContent ?? ""}`);
  }

  private parseValor(valor: string): { provedor: string; motor?: string; id?: string } | null {
    if (!valor) return null;
    const partes = valor.split(":");
    if (partes[0] === "openjarvis") return { provedor: "openjarvis", id: partes[1] };
    if (partes[0] === "elevenlabs") return { provedor: "elevenlabs", id: partes[1] };
    if (partes[0] === "gemini") return { provedor: "gemini", id: partes[1] };
    if (partes[0] === "propria") return { provedor: "propria", motor: partes[1], id: partes[2] };
    if (partes[0] === "cadastrada") return { provedor: "propria", id: partes[1] };
    return null;
  }

  // ---- amostras ------------------------------------------------------------
  private async amostraSelecionada(qual: "principal" | "reserva") {
    const sel = qual === "principal" ? this.selPrincipal : this.selReserva;
    const val = sel.value;
    if (!val) { this.deps.dizer("Escolha uma voz primeiro.", true); return; }
    const parsed = this.parseValor(val);
    if (!parsed) return;
    this.deps.dizer("Sintetizando...");
    try {
      let wav: ArrayBuffer;
      if (parsed.provedor === "openjarvis") {
        wav = await this.deps.criarOj().sintetizar(FRASE_AMOSTRA, parsed.id ?? this.cfg.voz, this.deps.velocidade());
      } else if (parsed.provedor === "elevenlabs") {
        const chave = this.el("elevenlabs_chave").value.trim();
        if (!chave) { this.deps.dizer("Informe a chave do ElevenLabs para ouvir esta voz.", true); return; }
        const fonte = new ElevenLabs(chave, parsed.id ?? "");
        wav = await fonte.falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000);
      } else if (parsed.provedor === "gemini") {
        const chave = this.el("gemini_chave").value.trim();
        if (!chave) { this.deps.dizer("Informe a chave do Gemini para ouvir esta voz.", true); return; }
        const { Gemini } = await import("../conectores/nuvem/gemini");
        const fonte = new Gemini(chave, parsed.id ?? "Kore");
        wav = await fonte.falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000);
      } else {
        const url = this.cfg.voz_url?.trim();
        if (!url) { this.deps.dizer("Endereço do serviço de voz não informado.", true); return; }
        wav = await new Voz(url, { voz: parsed.id }).falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000);
      }
      this.deps.dizer("Tocando.");
      await tocarWav(wav);
      this.deps.dizer("");
    } catch (erro) {
      this.deps.dizer(`Não consegui ouvir: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
  }

  // ---- serviços e chaves ---------------------------------------------------
  private desenharServicos() {
    const bloco = this.raiz.querySelector<HTMLElement>("#cfg-voz-servicos")!;
    const url = this.cfg.voz_url?.trim() ?? "";
    const estadoTxt = this.estado === "no-ar" ? "Serviço de voz no ar" : this.estado === "fora" ? "Serviço de voz fora do ar" : "Serviço de voz desligado";
    bloco.innerHTML = `
      <div class="voz-bloco-servico">
        <h4>Serviço de voz deste PC</h4>
        <p class="voz-servico-desc">Endereço do serviço local que roda XTTS, Kokoro, Edge ou Piper. As vozes locais aparecem na lista quando o serviço está no ar.</p>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Endereço do serviço de voz</span>
          <input type="text" id="cfg-voz_url" value="${esc(url)}" placeholder="http://127.0.0.1:4710">
          <span class="campo-modal-ajuda">${estadoTxt}</span>
        </label>
      </div>
      <div class="voz-bloco-servico">
        <h4>ElevenLabs</h4>
        <p class="voz-servico-desc">Vozes em nuvem sintetizadas na sua conta ElevenLabs. Informe a chave e carregue as vozes.</p>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Chave da API ElevenLabs</span>
          <input type="password" id="cfg-elevenlabs_chave" value="${esc(this.cfg.elevenlabs_chave)}">
        </label>
        <button type="button" id="cfg-voz-carregar-elevenlabs" class="voz-btn-secundario">Carregar vozes do ElevenLabs</button>
      </div>
      <div class="voz-bloco-servico">
        <h4>Gemini</h4>
        <p class="voz-servico-desc">Vozes sintetizadas pelo Google Gemini. Informe a chave para usar.</p>
        <label class="campo-modal">
          <span class="campo-modal-rotulo">Chave da API Gemini</span>
          <input type="password" id="cfg-gemini_chave" value="${esc(this.cfg.gemini_chave)}">
        </label>
      </div>
    `;
    bloco.querySelector("#cfg-voz-carregar-elevenlabs")?.addEventListener("click", () => { void this.carregarElevenLabs(); });
  }

  private async carregarElevenLabs() {
    const chave = this.el("elevenlabs_chave").value.trim();
    if (!chave) { this.deps.dizer("Informe a chave do ElevenLabs para carregar as vozes.", true); return; }
    try {
      const lista = await new ElevenLabs(chave, "x").vozes();
      this.vozesElevenLabs = lista;
      this.preencherListas();
      this.deps.dizer(`${lista.length} vozes carregadas.`);
    } catch (erro) {
      this.deps.dizer(`Não consegui carregar as vozes: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
  }

  private desenharCadastradas() {
    const bloco = this.raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const lista = vozesCadastradas(this.cfgPaineis);
    if (lista.length === 0) { bloco.innerHTML = ""; return; }
    bloco.innerHTML = `<fieldset><legend>Vozes cadastradas</legend><div id="cfg-voz-cadastradas-lista"></div></fieldset>`;
    const alvo = bloco.querySelector("#cfg-voz-cadastradas-lista")!;
    for (const p of lista) {
      const div = document.createElement("div");
      div.className = "voz-cadastrada-linha";
      div.innerHTML = `<span>${esc(p.nome)} (${motorDoTipo(p.tipo)})</span>`;
      const btnEditar = document.createElement("button");
      btnEditar.type = "button";
      btnEditar.textContent = "Editar";
      btnEditar.className = "voz-btn-secundario";
      btnEditar.addEventListener("click", () => { this.abrirCadastro(p); });
      div.append(btnEditar);
      alvo.append(div);
    }
    const btnAdd = document.createElement("button");
    btnAdd.type = "button";
    btnAdd.textContent = "Adicionar voz";
    btnAdd.className = "primaria";
    btnAdd.addEventListener("click", () => { this.abrirCadastro(); });
    alvo.append(btnAdd);
  }

  private abrirCadastro(atual?: VozCadastrada) {
    abrirModalVoz({
      cfg: this.cfgPaineis,
      atual,
      aoSalvar: async (campos, idOriginal) => { await this.salvarCadastrada(campos, idOriginal); },
      aoRemover: async (id) => {
        const p = this.cfgPaineis.provedores.find((x) => x.id === id);
        if (p) await this.removerCadastrada(p as VozCadastrada);
      },
    });
  }

  private async salvarCadastrada(campos: CamposVozCadastrada, idOriginal: string | null) {
    const nova: VozCadastrada = {
      id: campos.id, nome: campos.nome, tipo: campos.tipo,
      url_base: campos.url_base, modelo: campos.modelo,
      ...(campos.credencial_ref ? { credencial_ref: campos.credencial_ref } : {}),
    };
    const idx = idOriginal ? this.cfgPaineis.provedores.findIndex((p) => p.id === idOriginal) : -1;
    if (idx >= 0) this.cfgPaineis.provedores[idx] = nova;
    else this.cfgPaineis.provedores.push(nova);
    try {
      await gravarPaineis(this.cfgPaineis);
      this.deps.dizer("Voz salva.");
      this.desenharCadastradas();
      this.preencherListas();
    } catch (erro) {
      this.deps.dizer(`Não consegui salvar: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
  }

  private async removerCadastrada(p: VozCadastrada) {
    const idx = this.cfgPaineis.provedores.findIndex((x) => x.id === p.id);
    if (idx >= 0) this.cfgPaineis.provedores.splice(idx, 1);
    try {
      await gravarPaineis(this.cfgPaineis);
      this.deps.dizer("Voz removida.");
      this.desenharCadastradas();
      this.preencherListas();
    } catch (erro) {
      this.deps.dizer(`Não consegui remover: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
  }

  // ---- dispositivos e leitura do formulário ---------------------------------
  async carregarDispositivos() {
    const selMic = this.sel("microfone_id");
    const selSai = this.sel("saida_id");
    const notaMic = this.raiz.querySelector<HTMLElement>("#cfg-microfone_nota")!;
    const notaSai = this.raiz.querySelector<HTMLElement>("#cfg-saida_nota")!;
    try {
      const mics = await listarDispositivos("audioinput");
      const sais = await listarDispositivos("audiooutput");
      const pref = obterPreferencia();
      const opcoesMic: [string, string][] = [["", "Padrão do sistema"], ...mics.map((d): [string, string] => [d.deviceId, d.label])];
      const opcoesSai: [string, string][] = [["", "Padrão do sistema"], ...sais.map((d): [string, string] => [d.deviceId, d.label])];
      if (pref.microfone_id && !opcoesMic.some(([v]) => v === pref.microfone_id)) {
        opcoesMic.push([pref.microfone_id, `${pref.microfone_rotulo || pref.microfone_id} (não encontrado)`]);
      }
      if (pref.saida_id && !opcoesSai.some(([v]) => v === pref.saida_id)) {
        opcoesSai.push([pref.saida_id, `${pref.saida_rotulo || pref.saida_id} (não encontrado)`]);
      }
      this.preencherSelect(selMic, opcoesMic, pref.microfone_id);
      this.preencherSelect(selSai, opcoesSai, pref.saida_id);
      notaMic.textContent = pref.microfone_id && !mics.some((d) => d.deviceId === pref.microfone_id)
        ? "Microfone preferido não encontrado; usando padrão até reaparecer." : "";
      notaSai.textContent = pref.saida_id && !sais.some((d) => d.deviceId === pref.saida_id)
        ? "Saída preferida não encontrada; usando padrão até reaparecer." : "";
    } catch {
      notaMic.textContent = "Não consegui listar dispositivos.";
      notaSai.textContent = "";
    }
  }

  private preencherSelect(sel: HTMLSelectElement, opcoes: [string, string][], marcada: string) {
    sel.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor, false, valor === marcada)));
  }

  ler(): CamposVoz & Pick<Config, "microfone_id" | "microfone_rotulo" | "saida_id" | "saida_rotulo"> {
    const micSel = this.raiz.querySelector<HTMLSelectElement>("#cfg-microfone_id");
    const saiSel = this.raiz.querySelector<HTMLSelectElement>("#cfg-saida_id");
    const vadSel = this.raiz.querySelector<HTMLSelectElement>("#cfg-vad");
    const interEl = this.raiz.querySelector<HTMLInputElement>("#cfg-interromper_ao_falar");
    const micId = micSel?.value ?? "";
    const saiId = saiSel?.value ?? "";
    const micRot = micId && micSel ? (micSel.selectedOptions[0]?.textContent ?? "").replace(/ \(não encontrado\)$/, "") : "";
    const saiRot = saiId && saiSel ? (saiSel.selectedOptions[0]?.textContent ?? "").replace(/ \(não encontrado\)$/, "") : "";
    definirPreferencia({ microfone_id: micId, microfone_rotulo: micRot, saida_id: saiId, saida_rotulo: saiRot });
    return {
      vad: vadSel?.value === "silero" ? "silero" : "energia",
      interromper_ao_falar: interEl?.checked ?? false,
      voz_provedor: this.cfg.voz_provedor,
      voz_motor: this.cfg.voz_motor,
      voz_propria: this.cfg.voz_propria,
      voz: this.cfg.voz,
      elevenlabs_chave: this.el("elevenlabs_chave").value.trim(),
      elevenlabs_voz: this.cfg.elevenlabs_voz,
      gemini_chave: this.el("gemini_chave").value.trim(),
      gemini_voz: this.cfg.gemini_voz,
      voz_reserva_provedor: this.cfg.voz_reserva_provedor,
      voz_reserva_motor: this.cfg.voz_reserva_motor,
      voz_reserva_id: this.cfg.voz_reserva_id,
      microfone_id: micId, microfone_rotulo: micRot, saida_id: saiId, saida_rotulo: saiRot,
    };
  }

  erro(): string | null {
    const p = problemaDeVoz(this.ler());
    const marcar = (id: string, el: HTMLElement | null | undefined) => el?.classList.toggle("aviso", p?.campos.includes(id) ?? false);
    marcar("elevenlabs_chave", this.raiz.querySelector("#cfg-elevenlabs_chave"));
    marcar("gemini_chave", this.raiz.querySelector("#cfg-gemini_chave"));
    return p ? p.texto : null;
  }

  /** Endereço do serviço de voz lido do formulário (ou vazio). */
  vozUrl(): string {
    return this.el("voz_url")?.value?.trim() ?? "";
  }

  private el(id: string): HTMLInputElement { return this.raiz.querySelector(`#cfg-${id}`)!; }
  private sel(id: string): HTMLSelectElement { return this.raiz.querySelector(`#cfg-${id}`)!; }
}