import type { Config } from "../config/config";
import {
  ErroPonte,
  type CategoriaPreviaImportacao,
  type EscolhaImportacao,
  type ItemPreviaImportacao,
  type Ponte,
  type PreviaImportacao,
  type ResultadoAplicacaoImportacao,
  type ResultadoReversaoImportacao,
} from "../conectores/ponte/cliente";

export type ItemPrevia = ItemPreviaImportacao;
export type CategoriaPrevia = CategoriaPreviaImportacao;
export type ResultadoAplicacao = ResultadoAplicacaoImportacao;
export type ResultadoReversao = ResultadoReversaoImportacao;
export type { EscolhaImportacao, PreviaImportacao };

/** Campos da HUD que a importação pode trazer. Chaves (elevenlabs_chave, gemini_chave) nunca entram. */
export const CAMPOS_HUD_IMPORTAVEIS = [
  "nome", "variantes", "usuario", "voz", "velocidade", "idioma", "voz_provedor", "voz_propria",
] as const;
export type CampoHudImportavel = (typeof CAMPOS_HUD_IMPORTAVEIS)[number];
export type HudAtual = Partial<Record<CampoHudImportavel, unknown>>;

const CATEGORIAS = ["chamada", "voz", "cerebro", "persona", "config_toml", "segredos"] as const;
const ESTADOS = ["pronta", "ausente", "igual", "erro"] as const;

/** Retrato da HUD ativa só com campos importáveis (para comparar na prévia). Chaves nunca saem daqui. */
export function resumirHudAtual(cfg: Config): HudAtual {
  const saida: HudAtual = {};
  for (const k of CAMPOS_HUD_IMPORTAVEIS) {
    const v = cfg[k];
    saida[k] = Array.isArray(v) ? [...v] : v;
  }
  return saida;
}

/** Corpo do POST de prévia: origem mais o retrato da HUD (sem segredos). */
export function montarPedidoPrevia(origem: string, cfg: Config): { origem: string; hud_atual: HudAtual } {
  return { origem, hud_atual: resumirHudAtual(cfg) };
}

function itemOk(x: unknown): ItemPrevia | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  if (typeof o.campo !== "string" || !o.campo) return null;
  return {
    campo: o.campo,
    ...(o.origem !== undefined ? { origem: o.origem } : {}),
    ...(o.destino !== undefined ? { destino: o.destino } : {}),
    ...(typeof o.origem_tem === "boolean" ? { origem_tem: o.origem_tem } : {}),
    ...(typeof o.destino_tem === "boolean" ? { destino_tem: o.destino_tem } : {}),
    ...(typeof o.conflito === "boolean" ? { conflito: o.conflito } : {}),
    ...(typeof o.estado === "string" ? { estado: o.estado } : {}),
  };
}

/** Valida a prévia que veio da ponte; null = forma errada (não aplica). */
export function normalizarPrevia(x: unknown): PreviaImportacao | null {
  if (typeof x !== "object" || x === null) return null;
  const o = x as Record<string, unknown>;
  if (o.schema !== 1 || typeof o.previa_id !== "string" || !o.previa_id) return null;
  if (typeof o.origem !== "string" || typeof o.ja_ativo !== "boolean") return null;
  if (!Array.isArray(o.categorias) || !Array.isArray(o.avisos) || !o.avisos.every((a) => typeof a === "string")) return null;
  const categorias: CategoriaPrevia[] = [];
  for (const c of o.categorias) {
    if (typeof c !== "object" || c === null) return null;
    const r = c as Record<string, unknown>;
    if (!(CATEGORIAS as readonly string[]).includes(String(r.id))) return null;
    if (typeof r.titulo !== "string" || !(ESTADOS as readonly string[]).includes(String(r.estado))) return null;
    if (!Array.isArray(r.itens) || !Array.isArray(r.avisos) || !r.avisos.every((a) => typeof a === "string")) return null;
    const itens: ItemPrevia[] = [];
    for (const i of r.itens) {
      const n = itemOk(i);
      if (!n) return null;
      itens.push(n);
    }
    categorias.push({ id: String(r.id), titulo: r.titulo, estado: String(r.estado), itens, avisos: r.avisos as string[] });
  }
  return { schema: 1, previa_id: o.previa_id, origem: o.origem, ja_ativo: o.ja_ativo, categorias, avisos: o.avisos as string[] };
}

/** Sugestão inicial: importa o que não conflita, mantém o que conflita. */
export function sugerirEscolhas(pv: PreviaImportacao): Record<string, EscolhaImportacao> {
  const saida: Record<string, EscolhaImportacao> = {};
  for (const c of pv.categorias) {
    saida[c.id] = c.itens.some((i) => i.conflito) ? "manter" : "importar";
  }
  return saida;
}

function textoValido(v: unknown): v is string {
  return typeof v === "string" && v.trim() !== "";
}

/** Aplica o `hud` do resultado sobre uma cópia da config: só campos permitidos, com tipo certo. Chaves nunca entram. */
export function aplicarHudEscolhido(atual: Config, hud: unknown): Config {
  const saida: Config = { ...atual, variantes: [...atual.variantes], atalhos: { ...atual.atalhos } };
  if (typeof hud !== "object" || hud === null) return saida;
  const o = hud as Record<string, unknown>;
  if (textoValido(o.nome)) saida.nome = o.nome.trim();
  if (Array.isArray(o.variantes) && o.variantes.every((v) => typeof v === "string")) {
    const limpas = o.variantes.map((v) => v.trim()).filter(Boolean);
    if (limpas.length) saida.variantes = [...new Set(limpas)];
  }
  if (typeof o.usuario === "string") saida.usuario = o.usuario;
  if (textoValido(o.voz)) saida.voz = (o.voz as string).trim();
  if (typeof o.velocidade === "number" && Number.isFinite(o.velocidade) && o.velocidade > 0) saida.velocidade = o.velocidade;
  if (textoValido(o.idioma)) saida.idioma = (o.idioma as string).trim();
  if (textoValido(o.voz_provedor)) saida.voz_provedor = o.voz_provedor as Config["voz_provedor"];
  if (typeof o.voz_propria === "string") saida.voz_propria = o.voz_propria;
  return saida;
}

export interface DepsImportacao {
  previa: (origem: string, hudAtual: HudAtual) => Promise<PreviaImportacao>;
  aplicar: (previaId: string, escolhas: Record<string, EscolhaImportacao>, hudAtual: HudAtual) => Promise<ResultadoAplicacao>;
  reverter: (operacaoId: string) => Promise<ResultadoReversao>;
  lerHud: () => Config;
  salvarHud: (c: Config) => Promise<void>;
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Caixa "Importar instalação anterior" (aba Sistema): pasta, prévia por categoria, aplicar e reverter. */
export function montarImportacao(raiz: HTMLElement, deps: DepsImportacao): void {
  raiz.innerHTML =
    `<h3>Importar instalação anterior</h3>` +
    `<p class="nota">Traz nome, voz, cérebro, persona e segredos de uma instalação antiga. A origem nunca é alterada.</p>` +
    `<label>Pasta da instalação antiga <input id="primeiro-uso-importacao-origem" type="text" size="48" placeholder="Caminho da pasta"></label> ` +
    `<button type="button" id="primeiro-uso-importacao-previa">Ver prévia</button>` +
    `<div id="primeiro-uso-importacao-msg" role="status"></div>` +
    `<div id="primeiro-uso-importacao-categorias"></div>` +
    `<div id="primeiro-uso-importacao-acoes"></div>`;
  const msg = raiz.querySelector<HTMLElement>("#primeiro-uso-importacao-msg")!;
  const caixa = raiz.querySelector<HTMLElement>("#primeiro-uso-importacao-categorias")!;
  const acoes = raiz.querySelector<HTMLElement>("#primeiro-uso-importacao-acoes")!;
  let pv: PreviaImportacao | null = null;
  let hudAntes: Config | null = null;
  let operacao: string | null = null;

  const dizer = (t: string) => { msg.textContent = t; };

  async function verPrevia() {
    const origem = (raiz.querySelector<HTMLInputElement>("#primeiro-uso-importacao-origem")!.value || "").trim();
    acoes.innerHTML = "";
    operacao = null;
    if (!origem) { dizer("Informe a pasta da instalação antiga."); return; }
    dizer("Lendo a instalação antiga...");
    try {
      const bruta = await deps.previa(origem, resumirHudAtual(deps.lerHud()));
      const normal = normalizarPrevia(bruta);
      if (!normal) { dizer("A ponte devolveu uma prévia inválida."); return; }
      pv = normal;
      hudAntes = deps.lerHud();
      desenhar();
      dizer(pv.ja_ativo ? "Essa pasta já é a instalação ativa: nada a importar." : "Prévia pronta: escolha por categoria e aplique.");
    } catch (e) {
      pv = null;
      dizer(`Não consegui ler a origem: ${e instanceof ErroPonte ? e.codigo : "rede"}`);
    }
  }

  function desenhar() {
    if (!pv) { caixa.innerHTML = ""; return; }
    const sug = sugerirEscolhas(pv);
    caixa.innerHTML = pv.categorias.map((c) => {
      const itens = c.itens.map((i) => {
        const valor = i.origem !== undefined ? String(i.origem) : (i.origem_tem ? "presente" : "ausente");
        const marca = i.conflito ? " (diferente da atual)" : "";
        return `<li><strong>${esc(i.campo)}</strong>: ${esc(valor)}${esc(marca)}</li>`;
      }).join("");
      const avisos = c.avisos.map((a) => `<p class="nota">${esc(a)}</p>`).join("");
      const ops = c.estado === "pronta"
        ? `<label><input type="radio" name="imp-${c.id}" value="importar"${sug[c.id] === "importar" ? " checked" : ""}> Importar</label> ` +
          `<label><input type="radio" name="imp-${c.id}" value="manter"${sug[c.id] === "manter" ? " checked" : ""}> Manter a atual</label>`
        : `<span>Estado: ${esc(c.estado)}</span>`;
      return `<section><h4>${esc(c.titulo)}</h4><ul>${itens}</ul>${avisos}<div>${ops}</div></section>`;
    }).join("") + (pv.avisos.map((a) => `<p class="nota">${esc(a)}</p>`).join(""));
    acoes.innerHTML = pv.ja_ativo
      ? ""
      : `<button type="button" id="primeiro-uso-importacao-aplicar">Aplicar</button><span id="primeiro-uso-importacao-reverter-slot"></span>`;
    acoes.querySelector("#primeiro-uso-importacao-aplicar")?.addEventListener("click", () => { void aplicar(); });
  }

  function escolhas(): Record<string, EscolhaImportacao> {
    const saida: Record<string, EscolhaImportacao> = {};
    for (const c of pv?.categorias ?? []) {
      const marcado = caixa.querySelector<HTMLInputElement>(`input[name="imp-${c.id}"]:checked`);
      saida[c.id] = marcado?.value === "manter" ? "manter" : "importar";
    }
    return saida;
  }

  async function aplicar() {
    if (!pv || !hudAntes) return;
    dizer("Aplicando...");
    try {
      const r = await deps.aplicar(pv.previa_id, escolhas(), resumirHudAtual(deps.lerHud()));
      if (!r.ok) { dizer("A ponte não aplicou."); return; }
      if (r.hud) await deps.salvarHud(aplicarHudEscolhido(deps.lerHud(), r.hud));
      operacao = r.operacao_id;
      const base = r.operacao_id ? `Importado: ${(r.aplicadas ?? []).join(", ") || "nada mudou"}.` : "Nada mudou: já estava igual.";
      dizer(r.avisos?.length ? `${base} ${r.avisos.join(" ")}` : base);
      if (operacao) {
        const slot = acoes.querySelector("#primeiro-uso-importacao-reverter-slot")!;
        slot.innerHTML = `<button type="button" id="primeiro-uso-importacao-reverter">Reverter</button>`;
        slot.querySelector("button")!.addEventListener("click", () => { void reverter(); });
      }
    } catch (e) {
      dizer(`Não consegui aplicar: ${e instanceof ErroPonte ? e.codigo : "rede"}`);
    }
  }

  async function reverter() {
    if (!operacao) return;
    dizer("Revertendo...");
    try {
      const r = await deps.reverter(operacao);
      const anteriorHud: HudAtual | null =
        (r.hud_anterior && Object.keys(r.hud_anterior).length ? r.hud_anterior : null) ??
        (hudAntes ? resumirHudAtual(hudAntes) : null);
      if (anteriorHud) await deps.salvarHud(aplicarHudEscolhido(deps.lerHud(), anteriorHud));
      operacao = null;
      dizer(`Revertido: ${(r.restaurados ?? []).join(", ") || "arquivos de volta"}. ${(r.avisos ?? []).join(" ")}`);
    } catch (e) {
      dizer(`Não consegui reverter: ${e instanceof ErroPonte ? e.codigo : "rede"}`);
    }
  }

  raiz.querySelector("#primeiro-uso-importacao-previa")!.addEventListener("click", () => { void verPrevia(); });
}

/** Liga a caixa ao Ponte real e aos acessores da HUD (a ponte é criada a cada chamada, como nas outras abas). */
export function montarImportacaoComPonte(
  raiz: HTMLElement, criarPonte: () => Ponte, lerHud: () => Config, salvarHud: (c: Config) => Promise<void>,
): void {
  montarImportacao(raiz, {
    previa: (origem, hudAtual) => criarPonte().previaImportacao(origem, hudAtual),
    aplicar: (previaId, escolhas, hudAtual) => criarPonte().aplicarImportacao(previaId, escolhas, hudAtual),
    reverter: (operacaoId) => criarPonte().reverterImportacao(operacaoId),
    lerHud,
    salvarHud,
  });
}
