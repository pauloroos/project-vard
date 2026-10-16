/**
 * Seção Voz (0.9.3): a voz numa seção só — lista de vozes em cards agrupada por motor
 * (XTTS, Kokoro, Edge, Piper, ElevenLabs, Gemini, Fish) com as vozes cadastradas de
 * "Painéis: Vozes" no grupo do motor delas. Cadastrar/editar é modal (paineis-vozes).
 * Abaixo da lista ficam como estão: detector/interrupção, endereço do serviço de voz,
 * chaves e dispositivos. Serviço de voz fora do ar ⇒ aviso claro no topo (U8).
 */
import type { Config } from "../config/config";
import { PAINEIS_PADRAO, gravarPaineis, lerPaineis, type PaineisConfig } from "../config/paineis";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import { ElevenLabs } from "../conectores/nuvem/elevenlabs";
import { VOZES_GEMINI } from "../conectores/nuvem/gemini";
import { Voz } from "../conectores/voz/cliente";
import { FRASE_AMOSTRA, criarFonteDeVoz, type ProvedorVoz } from "../conectores/voz/escolher";
import { VOZES_KOKORO, VOZES_EDGE_PT_BR, VOZES_PIPER_PT_BR } from "../conectores/voz/kokoro";
import { listarDispositivos, definirPreferencia, obterPreferencia } from "../audio/dispositivos";
import { desenharCards, type AcaoCard, type Card } from "./componentes";
import { abrirModalVoz, motorDoTipo, vozesCadastradas, type CamposVozCadastrada, type VozCadastrada } from "./paineis-vozes";
import "./estilos/voz.css";

export interface DepsAbaVoz {
  /** Cliente do OpenJarvis no endereço salvo (para ouvir a voz Kokoro do servidor). */
  criarOj: () => OpenJarvis;
  /** Velocidade que está no formulário agora. */
  velocidade: () => number;
  dizer: (texto: string, ruim?: boolean) => void;
}

export type CamposVoz = Pick<Config, "vad" | "interromper_ao_falar" | "voz_provedor" | "voz_motor" | "voz_propria" | "voz" | "elevenlabs_chave" | "elevenlabs_voz" | "gemini_chave" | "gemini_voz">;

export const MOTORES_PROPRIA = [
  { id: "", rotulo: "Automático (o serviço escolhe)" },
  { id: "kokoro", rotulo: "Kokoro (local, sem rede)" },
  { id: "edge", rotulo: "Edge TTS (Microsoft, usa internet)" },
  { id: "piper", rotulo: "Piper (local, CPU)" },
  { id: "xtts", rotulo: "XTTS (local, GPU)" },
] as const;

export const VOZES_POR_MOTOR: Record<string, readonly { id: string; rotulo: string }[]> = {
  kokoro: VOZES_KOKORO,
  edge: VOZES_EDGE_PT_BR,
  piper: VOZES_PIPER_PT_BR,
};

/** Opções de um select de voz; a voz atual que não está na lista é acrescentada (não se perde em silêncio). */
export function opcoesDeVoz(base: [string, string][], atual: string, rotuloAusente: (v: string) => string = (v) => v): [string, string][] {
  return atual && !base.some(([v]) => v === atual) ? [...base, [atual, rotuloAusente(atual)]] : base;
}

/** Voz do Gemini que o select marca: a salva ou, vazia, a Kore (o padrão de criarFonteDeVoz). */
export function vozGeminiMarcada(salva: string): string { return salva.trim() || "Kore"; }

/** Motivo para não salvar e os campos (ids sem "cfg-") a marcar; null quando está tudo certo. */
export function problemaDeVoz(c: Pick<CamposVoz, "voz_provedor" | "elevenlabs_chave" | "elevenlabs_voz" | "gemini_chave">): { texto: string; campos: string[] } | null {
  if (c.voz_provedor === "elevenlabs" && (!c.elevenlabs_chave || !c.elevenlabs_voz)) {
    return { texto: "Informe a chave do ElevenLabs e a voz, ou escolha outro provedor.", campos: [...(c.elevenlabs_chave ? [] : ["elevenlabs_chave"]), ...(c.elevenlabs_voz ? [] : ["elevenlabs_voz_id"])] };
  }
  if (c.voz_provedor === "gemini" && !c.gemini_chave) return { texto: "Informe a chave do Gemini, ou escolha outro provedor.", campos: ["gemini_chave"] };
  return null;
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

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

async function buscarJson<T>(url: string, prazoMs: number): Promise<T | null> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), prazoMs);
  try {
    const r = await fetch(url, { signal: ac.signal });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch { return null; } finally { clearTimeout(t); }
}

/** "Dora (pt-BR, feminina)" vira nome "Dora" e observação "pt-BR, feminina". */
function nomeEObservacao(rotulo: string): { nome: string; observacao: string } {
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(rotulo);
  return m ? { nome: m[1], observacao: m[2] } : { nome: rotulo, observacao: "" };
}

const AVISO_SERVICOS = "Os serviços do Vard estão desligados — abra pelo atalho do Vard ou ligue em Sistema.";
const MOTORES_GRUPOS = ["XTTS", "Kokoro", "Edge", "Piper", "ElevenLabs", "Gemini", "Fish"] as const;
const MOTOR_LOCAL: Record<string, string> = { XTTS: "xtts", Kokoro: "kokoro", Edge: "edge", Piper: "piper" };
const VAZIO_GRUPO: Record<string, string> = {
  XTTS: "Nenhuma voz local carregada.",
  Kokoro: "Nenhuma voz Kokoro.",
  Edge: "Nenhuma voz Edge.",
  Piper: "Nenhuma voz Piper.",
  ElevenLabs: "Nenhuma voz carregada da conta. Informe a chave abaixo e clique em Carregar vozes do ElevenLabs.",
  Gemini: "Nenhuma voz Gemini.",
  Fish: "Nenhuma voz Fish cadastrada. Use Adicionar voz para cadastrar.",
};
const CATALOGOS: Record<string, readonly { id: string; rotulo: string }[]> = {
  Kokoro: VOZES_KOKORO,
  Edge: VOZES_EDGE_PT_BR,
  Piper: VOZES_PIPER_PT_BR,
};
const IDS_CONHECIDOS = new Set<string>([...VOZES_KOKORO, ...VOZES_EDGE_PT_BR, ...VOZES_PIPER_PT_BR].map((v) => v.id));
const IDS_POR_MOTOR: Record<"kokoro" | "edge" | "piper", Set<string>> = {
  kokoro: new Set(VOZES_KOKORO.map((v) => v.id)),
  edge: new Set(VOZES_EDGE_PT_BR.map((v) => v.id)),
  piper: new Set(VOZES_PIPER_PT_BR.map((v) => v.id)),
};

type EstadoServico = "no-ar" | "fora" | "desligado";

interface GrupoCards { id: string; titulo: string; cards: Card[] }

interface SelecaoVoz {
  voz_provedor: ProvedorVoz;
  voz_motor: string;
  voz_propria: string;
  voz: string;
  elevenlabs_voz: string;
  gemini_voz: string;
}

/** Cópia descartável do padrão (nunca mexe no PAINEIS_PADRAO compartilhado). */
function paineisEmBranco(): PaineisConfig {
  return { ...PAINEIS_PADRAO, provedores: [], mcps: [], agentes: { ...PAINEIS_PADRAO.agentes } };
}

/** Seção Voz: lista de vozes em cards por motor, modal de cadastro e as opções de sempre abaixo. */
export class AbaVoz {
  private selecao: SelecaoVoz;
  private cfgPaineis: PaineisConfig = paineisEmBranco();
  private estado: EstadoServico = "fora";
  private motores = { xtts: false, kokoro: false, edge: false, piper: false };
  private vozesServico: string[] = [];
  private vozesElevenLabs: { id: string; nome: string }[] = [];
  private buscas = new Map<string, string>();
  private lista!: HTMLElement;
  private aviso!: HTMLElement;
  private avisoDetalhe!: HTMLElement;

  constructor(private raiz: HTMLElement, private cfg: Config, private deps: DepsAbaVoz) {
    this.selecao = {
      voz_provedor: cfg.voz_provedor,
      voz_motor: cfg.voz_motor ?? "",
      voz_propria: cfg.voz_propria,
      voz: cfg.voz,
      elevenlabs_voz: cfg.elevenlabs_voz,
      gemini_voz: vozGeminiMarcada(cfg.gemini_voz),
    };
  }

  montar() {
    const c = this.cfg;
    this.raiz.innerHTML = `
      <div id="cfg-voz-aviso" class="voz-aviso" hidden>
        <strong id="cfg-voz-aviso-texto"></strong>
        <p id="cfg-voz-aviso-detalhe"></p>
      </div>
      <div class="voz-lista-topo">
        <button id="cfg-voz-adicionar" class="primaria" type="button">Adicionar voz</button>
      </div>
      <div id="cfg-voz-lista"><p class="nota">Carregando vozes…</p></div>
      <fieldset><legend>Detecção de voz</legend>
        <label>Detector<select id="cfg-vad"><option value="energia" ${c.vad === "energia" ? "selected" : ""}>Energia (padrão)</option><option value="silero" ${c.vad === "silero" ? "selected" : ""}>Silero (local)</option></select></label>
        <label class="marca"><input id="cfg-interromper_ao_falar" type="checkbox" ${c.interromper_ao_falar ? "checked" : ""}> Interromper ao falar por cima</label>
        <p class="nota">Mudanças valem após reiniciar. Para melhor separação de eco, use fones de ouvido.</p>
      </fieldset>
      <fieldset><legend>Serviço de voz e chaves</legend>
        <label>Endereço do serviço de voz (vazio desliga)<input id="cfg-voz_url" type="text" value="${esc(c.voz_url)}"></label>
        <label>Chave do ElevenLabs<input id="cfg-elevenlabs_chave" type="password" autocomplete="off" value="${esc(c.elevenlabs_chave)}"></label>
        <button id="cfg-elevenlabs_carregar" type="button">Carregar vozes do ElevenLabs</button>
        <label>Chave do Gemini<input id="cfg-gemini_chave" type="password" autocomplete="off" value="${esc(c.gemini_chave)}"></label>
        <p class="nota">As chaves ficam só na sua configuração e nunca aparecem em mensagens nem logs.</p>
      </fieldset>
      <fieldset><legend>Dispositivos</legend>
        <label>Microfone<select id="cfg-microfone_id"></select></label>
        <p class="nota" id="cfg-microfone_nota"></p>
        <label>Saída de áudio<select id="cfg-saida_id"></select></label>
        <p class="nota" id="cfg-saida_nota"></p>
      </fieldset>`;
    this.lista = this.raiz.querySelector<HTMLElement>("#cfg-voz-lista")!;
    this.aviso = this.raiz.querySelector<HTMLElement>("#cfg-voz-aviso")!;
    this.avisoDetalhe = this.raiz.querySelector<HTMLElement>("#cfg-voz-aviso-detalhe")!;
    this.raiz.querySelector("#cfg-voz-adicionar")!.addEventListener("click", () => this.abrirCadastro());
    this.raiz.querySelector("#cfg-elevenlabs_carregar")!.addEventListener("click", () => { void this.carregarElevenLabs(); });
    for (const id of ["elevenlabs_chave", "gemini_chave"]) this.el(id).addEventListener("input", () => this.el(id).classList.remove("aviso"));
    void this.atualizar();
    void this.carregarDispositivos();
  }

  /** Endereço do serviço de voz como está no formulário. */
  vozUrl(): string { return this.el("voz_url").value.trim(); }

  private el(id: string): HTMLInputElement { return this.raiz.querySelector<HTMLInputElement>(`#cfg-${id}`)!; }
  private sel(id: string): HTMLSelectElement { return this.raiz.querySelector<HTMLSelectElement>(`#cfg-${id}`)!; }

  /** Estado do serviço de voz + vozes do serviço + vozes cadastradas; redesenha a lista. */
  async atualizar(): Promise<void> {
    const url = this.vozUrl();
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
        const { vozes } = await new Voz(url).vozes();
        this.vozesServico = vozes;
      }
    }
    try { this.cfgPaineis = await lerPaineis(); } catch { this.cfgPaineis = paineisEmBranco(); }
    this.atualizarAviso();
    this.desenharLista();
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

  // ---- lista de vozes -------------------------------------------------------

  private montarGrupos(): GrupoCards[] {
    const grupos = new Map<string, Card[]>();
    const add = (grupo: string, card: Card) => grupos.set(grupo, [...(grupos.get(grupo) ?? []), card]);

    for (const p of vozesCadastradas(this.cfgPaineis)) add(motorDoTipo(p.tipo), this.cartaoCadastrada(p));

    const fora = this.estado !== "no-ar";
    const estadoFora = (grupo: string, motor: string) =>
      add(grupo, this.cartaoEstado(grupo, "Serviço de voz fora do ar", [`O motor ${motor} local aparece quando o serviço de voz subir.`]));
    const estadoAusente = (grupo: string, motor: string, acoes?: AcaoCard[]) =>
      add(grupo, this.cartaoEstado(grupo, "Não instalado neste PC", [`O motor ${motor} não está instalado neste PC.`], acoes));

    if (fora) estadoFora("XTTS", "XTTS");
    else if (!this.motorDisponivel("xtts")) {
      estadoAusente("XTTS", "XTTS", [{ rotulo: "Instalar", primaria: true, aoClicar: () => this.instalarPacote("xtts-v2") }]);
    } else {
      for (const nome of this.vozesServico) if (!IDS_CONHECIDOS.has(nome)) add("XTTS", this.cartaoLocal("XTTS", nome, nome, nome, ""));
    }

    // Kokoro tem duas origens: as vozes do OpenJarvis (sempre) e as do motor local (quando instalado).
    for (const v of VOZES_KOKORO) add("Kokoro", this.cartaoOpenJarvis(v.id, v.rotulo));
    if (fora) estadoFora("Kokoro", "Kokoro");
    else if (!this.motorDisponivel("kokoro")) estadoAusente("Kokoro", "Kokoro");
    else for (const v of VOZES_KOKORO) add("Kokoro", this.cartaoLocal("Kokoro", v.id, v.rotulo, v.rotulo, ""));

    for (const grupo of ["Edge", "Piper"] as const) {
      const motor = MOTOR_LOCAL[grupo] as "edge" | "piper";
      if (fora) estadoFora(grupo, grupo);
      else if (!this.motorDisponivel(motor)) estadoAusente(grupo, grupo);
      else for (const v of CATALOGOS[grupo]) add(grupo, this.cartaoLocal(grupo, v.id, v.rotulo, v.rotulo, grupo === "Edge" ? "usa a internet (Microsoft)" : "local, em CPU"));
    }

    for (const v of this.vozesElevenLabs) add("ElevenLabs", this.cartaoNuvem("ElevenLabs", v.id, v.nome || v.id));
    for (const nome of VOZES_GEMINI) add("Gemini", this.cartaoNuvem("Gemini", nome, nome));

    return MOTORES_GRUPOS.map((id) => ({ id, titulo: id, cards: grupos.get(id) ?? [] }));
  }

  /** Motor disponível: o /saude diz que sim, ou o /vozes já lista vozes dele (serviço sem os flags). */
  private motorDisponivel(motor: "xtts" | "kokoro" | "edge" | "piper"): boolean {
    if (this.motores[motor]) return true;
    if (motor === "xtts") return this.vozesServico.some((v) => !IDS_CONHECIDOS.has(v));
    return this.vozesServico.some((v) => IDS_POR_MOTOR[motor].has(v));
  }

  private cartaoEstado(grupo: string, titulo: string, linhas: string[], acoes?: AcaoCard[]): Card {
    return { id: `estado:${grupo}:${titulo}`, titulo, etiqueta: grupo, detalhes: linhas, acoes, selos: [], busca: "" };
  }

  private cartaoLocal(grupo: string, id: string, rotulo: string, nome: string, nota: string): Card {
    const { nome: titulo, observacao } = nomeEObservacao(nome);
    const emUso = this.selecao.voz_provedor === "propria" && this.selecao.voz_propria === id && (this.selecao.voz_motor === MOTOR_LOCAL[grupo] || !this.selecao.voz_motor);
    return this.cartaoDeVoz({
      chave: `voz:neste-pc:${grupo}:${id}`,
      titulo,
      etiqueta: `${grupo} · neste PC`,
      observacao: [observacao, nota].filter(Boolean).join(" · "),
      busca: `${id} ${rotulo}`,
      emUso,
      acao: () => {
        this.selecao = { ...this.selecao, voz_provedor: "propria", voz_motor: MOTOR_LOCAL[grupo], voz_propria: id };
        this.deps.dizer(`Voz em uso: ${titulo} (${grupo}, neste PC).`);
        this.desenharLista();
      },
      amostra: () => this.amostraLocal(id),
    });
  }

  private cartaoOpenJarvis(id: string, rotulo: string): Card {
    const { nome: titulo, observacao } = nomeEObservacao(rotulo);
    const emUso = this.selecao.voz_provedor === "openjarvis" && this.selecao.voz === id;
    return this.cartaoDeVoz({
      chave: `voz:openjarvis:Kokoro:${id}`,
      titulo,
      etiqueta: "Kokoro · OpenJarvis",
      observacao,
      busca: `${id} ${rotulo}`,
      emUso,
      acao: () => {
        this.selecao = { ...this.selecao, voz_provedor: "openjarvis", voz: id };
        this.deps.dizer(`Voz em uso: ${titulo} (OpenJarvis).`);
        this.desenharLista();
      },
      amostra: () => this.amostraOpenJarvis(id),
    });
  }

  private cartaoNuvem(grupo: "ElevenLabs" | "Gemini", id: string, titulo: string): Card {
    const emUso = grupo === "ElevenLabs"
      ? this.selecao.voz_provedor === "elevenlabs" && this.selecao.elevenlabs_voz === id
      : this.selecao.voz_provedor === "gemini" && this.selecao.gemini_voz === id;
    return this.cartaoDeVoz({
      chave: `voz:nuvem:${grupo}:${id}`,
      titulo,
      etiqueta: `${grupo} · nuvem`,
      observacao: grupo === "ElevenLabs" ? "sintetiza na conta ElevenLabs" : "sintetiza no Google",
      busca: `${id} ${titulo}`,
      emUso,
      acao: () => {
        this.selecao = grupo === "ElevenLabs"
          ? { ...this.selecao, voz_provedor: "elevenlabs", elevenlabs_voz: id }
          : { ...this.selecao, voz_provedor: "gemini", gemini_voz: id };
        this.deps.dizer(`Voz em uso: ${titulo} (${grupo}).`);
        this.desenharLista();
      },
      amostra: () => this.amostraNuvem(grupo, id),
    });
  }

  private cartaoCadastrada(p: VozCadastrada): Card {
    const grupo = motorDoTipo(p.tipo);
    const emUso = this.cfgPaineis.ativo === p.id;
    return this.cartaoDeVoz({
      chave: `voz:cadastrada:${grupo}:${p.id}`,
      titulo: p.nome,
      etiqueta: `${grupo} · cadastrada`,
      observacao: [p.modelo, p.url_base].filter(Boolean).join(" · ") || `tipo ${p.tipo}`,
      busca: `${p.id} ${p.nome} ${p.tipo}`,
      emUso,
      acao: () => { void this.usarCadastrada(p); },
      amostra: () => this.amostraCadastrada(p),
      cadastrada: p,
    });
  }

  private cartaoDeVoz(o: {
    chave: string; titulo: string; etiqueta: string; observacao: string; busca: string;
    emUso: boolean; acao: () => void; amostra: () => Promise<void>; cadastrada?: VozCadastrada;
  }): Card {
    const acoes: AcaoCard[] = [
      { rotulo: "Usar esta", primaria: true, aoClicar: o.acao },
      { rotulo: "Ouvir amostra", aoClicar: () => { void o.amostra(); } },
    ];
    if (o.cadastrada) {
      const p = o.cadastrada;
      acoes.push({ rotulo: "Editar", aoClicar: () => this.abrirCadastro(p) });
      acoes.push({ rotulo: "Remover", perigo: true, aoClicar: () => { void this.removerCadastrada(p); } });
    }
    return {
      id: o.chave,
      titulo: o.titulo,
      etiqueta: o.etiqueta,
      selos: o.emUso ? [{ texto: "Em uso", tom: "ativo" as const }] : [],
      detalhes: o.observacao ? [o.observacao] : [],
      acoes,
      busca: o.busca,
    };
  }

  private desenharLista() {
    const grupos = this.montarGrupos();
    this.lista.replaceChildren();
    for (const g of grupos) {
      const bloco = document.createElement("section");
      bloco.className = "grupo-motor";
      bloco.dataset.grupo = g.id;
      const titulo = document.createElement("h3");
      titulo.textContent = g.titulo;
      const alvo = document.createElement("div");
      alvo.id = `cfg-voz-grupo-${g.id.toLowerCase()}`;
      bloco.append(titulo, alvo);
      this.lista.append(bloco);
      desenharCards(alvo, g.cards, { vazio: VAZIO_GRUPO[g.id] ?? "Nenhuma voz." });
      const busca = alvo.querySelector<HTMLInputElement>("input.cards-busca");
      if (busca) {
        const salva = this.buscas.get(g.id) ?? "";
        busca.value = salva;
        if (salva) busca.dispatchEvent(new Event("input"));
        busca.addEventListener("input", () => this.buscas.set(g.id, busca.value));
      }
    }
  }

  // ---- ações dos cards ------------------------------------------------------

  /** O botão de instalar do instalador existente (só itens do catálogo, ex.: xtts-v2). */
  private instalarPacote(pkgId: string) {
    const botao = document.querySelector<HTMLButtonElement>(`#cfg-instalador-vozes button[data-acao="instalar"][data-pkg="${pkgId}"]`);
    if (botao) {
      botao.scrollIntoView?.({ block: "nearest" });
      botao.click();
      return;
    }
    this.deps.dizer("O instalador de vozes não está disponível nesta tela; abra o painel de novo e tente.", true);
  }

  private async usarCadastrada(p: VozCadastrada) {
    this.cfgPaineis.ativo = p.id;
    try {
      await gravarPaineis(this.cfgPaineis);
      this.deps.dizer(`Voz em uso: ${p.nome}.`);
    } catch (erro) {
      this.deps.dizer(`Não consegui gravar: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
    this.desenharLista();
  }

  private async removerCadastrada(p: VozCadastrada) {
    const idx = this.cfgPaineis.provedores.findIndex((x) => x.id === p.id);
    if (idx >= 0) this.cfgPaineis.provedores.splice(idx, 1);
    if (this.cfgPaineis.ativo === p.id) this.cfgPaineis.ativo = null;
    if (this.cfgPaineis.reserva === p.id) this.cfgPaineis.reserva = null;
    try {
      await gravarPaineis(this.cfgPaineis);
      this.deps.dizer("Voz removida.");
    } catch (erro) {
      this.deps.dizer(`Não consegui remover: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
    this.desenharLista();
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
    } catch (erro) {
      this.deps.dizer(`Não consegui salvar: ${erro instanceof Error ? erro.message : "falha"}`, true);
    }
    this.desenharLista();
  }

  // ---- amostras -------------------------------------------------------------

  private async amostraLocal(id: string) {
    await this.tocar(() => new Voz(this.vozUrl(), { voz: id }).falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000), id);
  }

  private async amostraOpenJarvis(id: string) {
    await this.tocar(() => this.deps.criarOj().sintetizar(FRASE_AMOSTRA, id, this.deps.velocidade()), id);
  }

  private async amostraNuvem(grupo: "ElevenLabs" | "Gemini", id: string) {
    const chave = this.el(grupo === "ElevenLabs" ? "elevenlabs_chave" : "gemini_chave").value.trim();
    if (!chave) { this.deps.dizer(`Informe a chave do ${grupo} para ouvir esta voz.`, true); return; }
    const fonte = criarFonteDeVoz({
      voz_provedor: grupo === "ElevenLabs" ? "elevenlabs" : "gemini",
      voz_url: this.vozUrl(),
      voz_propria: this.selecao.voz_propria,
      elevenlabs_chave: grupo === "ElevenLabs" ? chave : "",
      elevenlabs_voz: grupo === "ElevenLabs" ? id : "",
      gemini_chave: grupo === "Gemini" ? chave : "",
      gemini_voz: grupo === "Gemini" ? id : "",
    });
    if (!fonte) { this.deps.dizer(`Não consegui montar a voz do ${grupo}.`, true); return; }
    await this.tocar(() => fonte.falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000), id);
  }

  private async amostraCadastrada(p: VozCadastrada) {
    if (!p.url_base) { this.deps.dizer("Esta voz cadastrada não tem endereço para amostra.", true); return; }
    await this.tocar(() => new Voz(p.url_base, { voz: p.modelo || p.id }).falarWav(FRASE_AMOSTRA, this.deps.velocidade(), 20000), p.id);
  }

  private async tocar(fonte: () => Promise<ArrayBuffer>, id: string) {
    this.deps.dizer("Sintetizando...");
    try {
      const wav = await fonte();
      this.deps.dizer("Tocando.");
      await tocarWav(wav);
      this.deps.dizer("");
    } catch (erro) { this.deps.dizer(`Não consegui ouvir ${id}: ${erro instanceof Error ? erro.message : "falha"}`, true); }
  }

  private async carregarElevenLabs() {
    const chave = this.el("elevenlabs_chave").value.trim();
    if (!chave) { this.deps.dizer("Informe a chave do ElevenLabs para carregar as vozes.", true); return; }
    try {
      const lista = await new ElevenLabs(chave, "x").vozes();
      this.vozesElevenLabs = lista;
      if (!this.selecao.elevenlabs_voz && lista[0]) this.selecao.elevenlabs_voz = lista[0].id;
      this.desenharLista();
      this.deps.dizer(`${lista.length} vozes carregadas.`);
    } catch (erro) { this.deps.dizer(`Não consegui carregar as vozes: ${erro instanceof Error ? erro.message : "falha"}`, true); }
  }

  // ---- dispositivos e leitura do formulário ---------------------------------

  /** Carrega as listas de microfone e saída e seleciona os salvos; avisa se o preferido sumiu. */
  private async carregarDispositivos() {
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
      // Se o salvo não está na lista, acrescenta para não perder a escolha silenciosamente.
      if (pref.microfone_id && !opcoesMic.some(([v]) => v === pref.microfone_id)) {
        opcoesMic.push([pref.microfone_id, `${pref.microfone_rotulo || pref.microfone_id} (não encontrado)`]);
      }
      if (pref.saida_id && !opcoesSai.some(([v]) => v === pref.saida_id)) {
        opcoesSai.push([pref.saida_id, `${pref.saida_rotulo || pref.saida_id} (não encontrado)`]);
      }
      this.preencher(selMic, opcoesMic, pref.microfone_id);
      this.preencher(selSai, opcoesSai, pref.saida_id);
      notaMic.textContent = pref.microfone_id && !mics.some((d) => d.deviceId === pref.microfone_id)
        ? "Microfone preferido não encontrado; usando padrão até reaparecer." : "";
      notaSai.textContent = pref.saida_id && !sais.some((d) => d.deviceId === pref.saida_id)
        ? "Saída preferida não encontrada; usando padrão até reaparecer." : "";
    } catch {
      notaMic.textContent = "Não consegui listar dispositivos.";
      notaSai.textContent = "";
    }
  }

  private preencher(sel: HTMLSelectElement, opcoes: [string, string][], marcada: string) {
    sel.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor, false, valor === marcada)));
  }

  /** O que o formulário diz sobre a voz; a escolha dos cards vem da seleção atual. */
  ler(): CamposVoz & Pick<Config, "microfone_id" | "microfone_rotulo" | "saida_id" | "saida_rotulo"> {
    const micId = this.sel("microfone_id").value;
    const saiId = this.sel("saida_id").value;
    // Rótulos: usa o texto da opção selecionada (sem o sufixo "não encontrado").
    const micRot = micId ? (this.sel("microfone_id").selectedOptions[0]?.textContent ?? "").replace(/ \(não encontrado\)$/, "") : "";
    const saiRot = saiId ? (this.sel("saida_id").selectedOptions[0]?.textContent ?? "").replace(/ \(não encontrado\)$/, "") : "";
    // Atualiza a preferência em memória para que o devicechange e a captura usem imediatamente.
    definirPreferencia({ microfone_id: micId, microfone_rotulo: micRot, saida_id: saiId, saida_rotulo: saiRot });
    return {
      vad: this.sel("vad").value === "silero" ? "silero" : "energia", interromper_ao_falar: this.el("interromper_ao_falar").checked,
      voz_provedor: this.selecao.voz_provedor, voz_motor: this.selecao.voz_motor, voz_propria: this.selecao.voz_propria, voz: this.selecao.voz,
      elevenlabs_chave: this.el("elevenlabs_chave").value.trim(), elevenlabs_voz: this.selecao.elevenlabs_voz,
      gemini_chave: this.el("gemini_chave").value.trim(), gemini_voz: this.selecao.gemini_voz,
      microfone_id: micId, microfone_rotulo: micRot, saida_id: saiId, saida_rotulo: saiRot,
    };
  }

  /** Motivo para não salvar (provedor de nuvem sem chave ou voz), ou null. Marca em aviso o campo que falta (some ao digitar). */
  erro(): string | null {
    const p = problemaDeVoz(this.ler());
    const marcar = (id: string, el: HTMLElement | null | undefined) => el?.classList.toggle("aviso", p?.campos.includes(id) ?? false);
    marcar("elevenlabs_chave", this.raiz.querySelector("#cfg-elevenlabs_chave"));
    marcar("gemini_chave", this.raiz.querySelector("#cfg-gemini_chave"));
    marcar("elevenlabs_voz_id", this.raiz.querySelector("#cfg-voz-grupo-elevenlabs"));
    return p ? p.texto : null;
  }
}
