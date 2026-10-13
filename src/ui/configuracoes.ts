import { invoke } from "@tauri-apps/api/core";
import type { Config } from "../config/config";
import { avisosDeUrl, limitarLado, mudancasQueExigemReinicio, salvarConfig, urlLocal } from "../config/config";
import { ACOES_ATALHO, ROTULOS_ATALHO, avisoAltGr, validarAtalhos, type AcaoAtalho, type FalhaAtalho } from "../config/atalhos";
import { campoAtalho } from "./campo-atalho";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import { AbaModelos } from "./aba-modelos";

export interface DepsConfiguracoes {
  /** Cliente do OpenJarvis para o endereço dado (o main decide se passa pelo proxy do dev). */
  criarOj: (url: string, modelo?: string) => OpenJarvis;
  /** Status da ponte no endereço dado (null = fora ou desligada). */
  statusPonte: (url: string) => Promise<StatusPonte | null>;
  /** Depois de gravar: o main avisa o widget (evento config-salva). */
  aoSalvar?: (c: Config) => void;
  /** Fecha a janela do painel. */
  fechar?: () => void;
}

/** Monitor como o comando listar_monitores devolve (pixels físicos). */
export interface MonitorInfo { nome: string; x: number; y: number; largura: number; altura: number; escala: number; principal: boolean }

export type Aba = "geral" | "voz" | "atalhos" | "modelos" | "ponte";
const ABAS: [Aba, string][] = [["geral", "Geral"], ["voz", "Voz"], ["atalhos", "Atalhos"], ["modelos", "Modelos"], ["ponte", "Ponte"]];
const OPCOES_TAMANHO: [Config["tamanho"], string][] = [
  ["pequeno", "Pequeno (240 px)"], ["medio", "Médio (320 px)"], ["grande", "Grande (480 px)"], ["personalizado", "Personalizado"],
];

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Painel de configurações na janela própria "configuracoes": abas e um campo por chave editável do Config. */
export class Configuracoes {
  private msg!: HTMLElement;
  private logon!: HTMLInputElement;
  private logonGuardado = false;
  private atalhos: Config["atalhos"];
  private falhas: FalhaAtalho[] = [];
  private modelos: AbaModelos | null = null;
  private linhasAtalho = new Map<AcaoAtalho, { campo: HTMLButtonElement; motivo: HTMLElement }>();

  constructor(private cfg: Config, private raiz: HTMLElement, private deps: DepsConfiguracoes) {
    this.atalhos = { ...cfg.atalhos };
  }

  /** Desenha as abas e lê o que só o Rust sabe (início no logon, atalhos que não registraram). */
  async montar() {
    this.desenhar();
    this.modelos = new AbaModelos(this.raiz.querySelector<HTMLElement>("#cfg-modelos")!, this.cfg.modelo, {
      criarOj: (modelo) => this.deps.criarOj(this.cfg.openjarvis_url, modelo),
      statusPonte: () => this.deps.statusPonte(this.cfg.ponte_url),
    });
    void this.modelos.carregar();
    this.abrirAba("geral");
    try { this.logonGuardado = await invoke<boolean>("inicio_no_logon_ativo"); } catch { this.logonGuardado = false; }
    this.logon.checked = this.logonGuardado;
    try { this.preencherMonitores(await invoke<MonitorInfo[]>("listar_monitores")); } catch { this.preencherMonitores([]); }
    try { this.falhas = await invoke<FalhaAtalho[]>("falhas_de_atalho"); } catch { this.falhas = []; }
    this.marcarAtalhos({});
    if (this.falhas.length) this.dizer("Há atalhos que o Windows não aceitou: veja a aba Atalhos.", true);
  }

  abrirAba(aba: Aba) {
    for (const s of this.raiz.querySelectorAll<HTMLElement>("section[data-aba]")) s.hidden = s.dataset.aba !== aba;
    for (const b of this.raiz.querySelectorAll<HTMLButtonElement>("nav button")) b.classList.toggle("ativa", b.dataset.aba === aba);
  }

  /** O widget gravou topo ou compacto pelos próprios botões: acompanha sem perder o resto do formulário. */
  mudouNoWidget(c: Pick<Config, "sempre_no_topo" | "compacto">) {
    this.cfg.sempre_no_topo = c.sempre_no_topo;
    this.cfg.compacto = c.compacto;
    this.el("sempre_no_topo").checked = c.sempre_no_topo;
    this.el("compacto").checked = c.compacto;
  }

  /** A bandeja mudou "Sempre no topo": reflete no painel sem mexer no resto do formulário. */
  mudouTopo(ligado: boolean) {
    this.cfg.sempre_no_topo = ligado;
    this.el("sempre_no_topo").checked = ligado;
  }

  private campo(id: string, rotulo: string, valor: string | number, tipo = "text", extra = ""): string {
    return `<label>${rotulo}<input id="cfg-${id}" type="${tipo}" value="${esc(String(valor))}" ${extra}></label>`;
  }
  private marca(id: string, rotulo: string, valor: boolean): string {
    return `<label class="marca"><input id="cfg-${id}" type="checkbox" ${valor ? "checked" : ""}> ${rotulo}</label>`;
  }
  private el(id: string): HTMLInputElement { return this.raiz.querySelector<HTMLInputElement>(`#cfg-${id}`)!; }
  private sel(id: string): HTMLSelectElement { return this.raiz.querySelector<HTMLSelectElement>(`#cfg-${id}`)!; }

  private desenhar() {
    const c = this.cfg;
    this.raiz.innerHTML = `
      <nav>${ABAS.map(([id, nome]) => `<button type="button" data-aba="${id}">${nome}</button>`).join("")}</nav>
      <section data-aba="geral">
        <fieldset><legend>Endereços</legend>
          ${this.campo("openjarvis_url", "OpenJarvis", c.openjarvis_url)}
          ${this.campo("gui_url", "Interface de texto", c.gui_url)}
          <button id="cfg-testar" type="button">Testar OpenJarvis</button>
        </fieldset>
        <fieldset><legend>Chamada</legend>
          ${this.campo("nome", "Nome para chamar", c.nome)}
          ${this.campo("variantes", "Variantes (separadas por vírgula)", c.variantes.join(", "))}
          ${this.campo("usuario", "Como te chamar (opcional)", c.usuario)}
          ${this.campo("idioma", "Idioma do reconhecimento", c.idioma)}
        </fieldset>
        <fieldset id="cfg-janela"><legend>Janela</legend>
          <label>Tamanho do widget<select id="cfg-tamanho">${OPCOES_TAMANHO.map(([v, r]) => `<option value="${v}" ${v === c.tamanho ? "selected" : ""}>${r}</option>`).join("")}</select></label>
          ${this.campo("tamanho_px", "Lado em px (personalizado, 160 a 800)", c.tamanho_px, "number", 'step="10" min="160" max="800"')}
          ${this.marca("compacto", "Compacto (só o holograma)", c.compacto)}
          ${this.marca("sempre_no_topo", "Sempre no topo", c.sempre_no_topo)}
          ${this.marca("click_through", "Clique atravessa a janela", c.click_through)}
          ${this.marca("logon", "Iniciar com o Windows", false)}
          <label>Monitor da tela cheia<select id="cfg-sala_monitor"></select></label>
        </fieldset>
      </section>
      <section data-aba="voz">
        <fieldset><legend>Fala</legend>
          ${this.campo("voz", "Voz da fala (OpenJarvis)", c.voz)}
          ${this.campo("velocidade", "Velocidade da fala", c.velocidade, "number", 'step="0.05" min="0.5" max="2"')}
          ${this.campo("voz_url", "Serviço de voz (opcional; vazio desliga)", c.voz_url)}
          ${this.campo("instrucao_formato", "Instrução de formato", c.instrucao_formato)}
        </fieldset>
        <fieldset><legend>Ouvido</legend>
          ${this.campo("finish_ms", "Silêncio para encerrar a fala (ms)", c.finish_ms, "number", 'step="50" min="200" max="3000"')}
          ${this.campo("limiar_vad", "Limiar do microfone", c.limiar_vad, "number", 'step="0.005" min="0.001" max="0.5"')}
        </fieldset>
      </section>
      <section data-aba="atalhos">
        <p class="nota">Clique num atalho e pressione a nova combinação (Ctrl, Alt ou Win mais uma tecla). Esc cancela. Valem depois de reiniciar o Vard.</p>
        <div id="cfg-atalhos"></div>
      </section>
      <section data-aba="ponte">
        ${this.campo("ponte_url", "Ponte do Vard (opcional; vazio desliga)", c.ponte_url)}
        <p class="nota">A ponte dá olhos na tela e modo jogo. Sem ela o widget funciona igual. Veja docs/ponte-do-vard.md.</p>
      </section>
      <section data-aba="modelos" id="cfg-modelos"></section>
      <footer>
        <div id="cfg-msg" role="status"></div>
        <div class="acoes"><button id="cfg-salvar" type="button">Salvar</button><button id="cfg-fechar" type="button">Fechar</button></div>
      </footer>`;
    this.msg = this.raiz.querySelector<HTMLElement>("#cfg-msg")!;
    this.logon = this.el("logon");
    for (const b of this.raiz.querySelectorAll<HTMLButtonElement>("nav button")) b.addEventListener("click", () => this.abrirAba(b.dataset.aba as Aba));
    this.raiz.querySelector("#cfg-fechar")!.addEventListener("click", () => this.deps.fechar?.());
    this.raiz.querySelector("#cfg-salvar")!.addEventListener("click", () => { void this.salvar(); });
    this.raiz.querySelector("#cfg-testar")!.addEventListener("click", () => { void this.testar(); });
    this.montarAtalhos(this.raiz.querySelector<HTMLElement>("#cfg-atalhos")!);
    for (const id of ["openjarvis_url", "gui_url", "ponte_url", "voz_url"]) {
      const campo = this.el(id);
      const opcional = id === "ponte_url" || id === "voz_url"; // vazio desliga: não é endereço ruim
      const marcar = () => campo.classList.toggle("aviso", !(opcional && campo.value.trim() === "") && !urlLocal(campo.value.trim()));
      campo.addEventListener("input", marcar); marcar();
    }
  }

  private montarAtalhos(caixa: HTMLElement) {
    this.linhasAtalho.clear();
    for (const acao of ACOES_ATALHO) {
      const linha = document.createElement("div");
      linha.className = "linha-atalho";
      const rotulo = document.createElement("span");
      rotulo.textContent = ROTULOS_ATALHO[acao];
      const campo = campoAtalho(this.atalhos[acao], (nova) => { this.atalhos[acao] = nova; this.marcarAtalhos(validarAtalhos(this.atalhos)); });
      const motivo = document.createElement("small");
      motivo.className = "motivo";
      linha.append(rotulo, campo, motivo);
      caixa.append(linha);
      this.linhasAtalho.set(acao, { campo, motivo });
    }
  }

  /** Marca cada campo com o erro de validação ou com a falha de registro do arranque (enquanto a combinação for a mesma). */
  private marcarAtalhos(erros: Partial<Record<AcaoAtalho, string>>) {
    for (const [acao, { campo, motivo }] of this.linhasAtalho) {
      const falha = this.falhas.find((f) => f.chave === acao && f.combinacao === this.atalhos[acao]);
      const texto = erros[acao] ?? (falha ? `Não registrou no Windows: ${falha.erro}. Outro programa pode estar usando; troque e reinicie.` : "");
      const altgr = texto === "" ? avisoAltGr(this.atalhos[acao]) : null;
      campo.classList.toggle("aviso", texto !== "" || altgr !== null);
      motivo.textContent = texto || altgr || "";
    }
  }


  /** "Principal" mais os monitores conectados; um escolhido que sumiu continua na lista, marcado, para não se perder. */
  private preencherMonitores(lista: MonitorInfo[]) {
    const sel = this.sel("sala_monitor");
    const atual = this.cfg.sala_monitor;
    const opcoes: [string, string][] = [
      ["", "Principal"],
      ...lista.map((m, i): [string, string] => [m.nome, `Monitor ${i + 1}: ${m.largura}x${m.altura}${m.principal ? " (principal)" : ""}`]),
    ];
    if (atual && !lista.some((m) => m.nome === atual)) opcoes.push([atual, "Desconectado (a sala abre no principal)"]);
    sel.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor, false, valor === atual)));
  }

  private dizer(t: string, ruim = false) { this.msg.textContent = t; this.msg.classList.toggle("ruim", ruim); }

  /** Lê o formulário; números inválidos e textos obrigatórios vazios mantêm o valor atual. */
  lerFormulario(): Config {
    const num = (id: string, atual: number) => {
      const bruto = this.el(id).value.trim().replace(",", ".");
      const n = Number(bruto);
      return bruto !== "" && Number.isFinite(n) ? n : atual;
    };
    const txt = (id: string, atual: string) => this.el(id).value.trim() || atual;
    const opc = (id: string) => this.el(id).value.trim(); // vazio é valor válido (desliga, tira o nome, idioma automático)
    const c = this.cfg;
    return {
      ...c,
      openjarvis_url: txt("openjarvis_url", c.openjarvis_url), gui_url: txt("gui_url", c.gui_url), ponte_url: opc("ponte_url"),
      voz_url: opc("voz_url"),
      nome: txt("nome", c.nome), usuario: opc("usuario"),
      variantes: this.el("variantes").value.split(",").map((v) => v.trim()).filter(Boolean),
      idioma: opc("idioma"), voz: txt("voz", c.voz),
      velocidade: num("velocidade", c.velocidade), finish_ms: num("finish_ms", c.finish_ms), limiar_vad: num("limiar_vad", c.limiar_vad),
      instrucao_formato: txt("instrucao_formato", c.instrucao_formato),
      tamanho: this.sel("tamanho").value as Config["tamanho"], tamanho_px: limitarLado(num("tamanho_px", c.tamanho_px)),
      compacto: this.el("compacto").checked,
      sempre_no_topo: this.el("sempre_no_topo").checked, click_through: this.el("click_through").checked,
      atalhos: { ...this.atalhos },
      modelo: this.modelos?.escolhido ?? c.modelo,
      sala_monitor: this.sel("sala_monitor").options.length ? this.sel("sala_monitor").value : c.sala_monitor, // lista ainda não chegou: mantém
    };
  }

  private async salvar() {
    const novo = this.lerFormulario();
    if (novo.variantes.length === 0) novo.variantes = [novo.nome];
    const erros = validarAtalhos(novo.atalhos);
    for (const acao of ACOES_ATALHO) {
      if (erros[acao]) continue;
      try { await invoke("validar_atalho", { combinacao: novo.atalhos[acao] }); }
      catch (e) { erros[acao] = `O Windows não aceita essa combinação (${String(e)}).`; }
    }
    this.marcarAtalhos(erros);
    if (Object.keys(erros).length) { this.abrirAba("atalhos"); this.dizer("Corrija os atalhos marcados antes de salvar.", true); return; }
    const reiniciar = mudancasQueExigemReinicio(this.cfg, novo);
    try { await salvarConfig(novo); }
    catch (erro) { this.dizer(`Não consegui salvar: ${String(erro)}`, true); return; }
    Object.assign(this.cfg, novo);
    // O atalho de início só é mexido quando a caixa mudou (evita regravar o .lnk a cada Salvar).
    let falhouLogon = false;
    if (this.logon.checked !== this.logonGuardado) {
      try { await invoke("definir_inicio_no_logon", { ligado: this.logon.checked }); this.logonGuardado = this.logon.checked; }
      catch { falhouLogon = true; this.logon.checked = this.logonGuardado; }
    }
    this.deps.aoSalvar?.(this.cfg);
    const avisos = avisosDeUrl(novo);
    const partes = [falhouLogon ? "Configuração salva, mas não consegui criar o atalho de início." : "Salvo; tamanho, janela e usuário já valem no widget."];
    if (reiniciar.length) partes.push(`Reinicie o Vard para aplicar: ${reiniciar.join(", ")}.`);
    if (avisos.length) partes.push(`Atenção: ${avisos.join("; ")}.`);
    this.dizer(partes.join(" "), avisos.length > 0 || falhouLogon);
  }

  private async testar() {
    const url = this.el("openjarvis_url").value.trim();
    this.dizer("Testando...");
    try {
      const oj = this.deps.criarOj(url);
      if (!(await oj.saude())) { this.dizer("OpenJarvis não respondeu nesse endereço.", true); return; }
      if (!(await oj.fala())) { this.dizer("OpenJarvis no ar, mas a fala está desligada. Veja docs/ligar-a-fala.md.", true); return; }
      this.dizer("OpenJarvis no ar e a fala está ligada.");
    } catch (erro) { this.dizer(`Falha no teste: ${String(erro)}`, true); }
  }
}
