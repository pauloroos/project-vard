import { invoke } from "@tauri-apps/api/core";
import type { Config } from "../config/config";
import { avisosDeUrl, salvarConfig, urlLocal } from "../config/config";
import type { OpenJarvis } from "../api/openjarvis";

export interface DepsConfiguracoes {
  /** Cria um cliente do OpenJarvis para o endereço digitado (o main decide se passa pelo proxy do dev). */
  criarOj: (url: string) => OpenJarvis;
  /** Chamado depois de salvar, com a config já gravada (o main reaplica o que dá para aplicar sem reiniciar). */
  aoSalvar?: (c: Config) => void;
  /** Chamado ao abrir/fechar: o main tira o click-through enquanto o painel está aberto. */
  aoAlternar?: (aberto: boolean) => void;
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Painel de configurações: uma sobreposição dentro do widget, sem framework. Um campo por chave editável do Config. */
export class Configuracoes {
  private painel: HTMLElement;
  private msg!: HTMLElement;
  private logon!: HTMLInputElement;
  private logonGuardado = false;

  constructor(private cfg: Config, painel: HTMLElement, private deps: DepsConfiguracoes) {
    this.painel = painel;
    window.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && this.aberto()) this.fechar(); });
  }

  aberto(): boolean { return !this.painel.hidden; }

  async abrir() {
    this.desenhar();
    this.painel.hidden = false;
    this.deps.aoAlternar?.(true);
    try { this.logonGuardado = await invoke<boolean>("inicio_no_logon_ativo"); } catch { this.logonGuardado = false; /* fora do Tauri */ }
    this.logon.checked = this.logonGuardado;
  }

  fechar() { this.painel.hidden = true; this.deps.aoAlternar?.(false); }

  private campo(id: string, rotulo: string, valor: string | number, tipo = "text", extra = ""): string {
    return `<label>${rotulo}<input id="cfg-${id}" type="${tipo}" value="${esc(String(valor))}" ${extra}></label>`;
  }
  private marca(id: string, rotulo: string, valor: boolean): string {
    return `<label class="marca"><input id="cfg-${id}" type="checkbox" ${valor ? "checked" : ""}> ${rotulo}</label>`;
  }
  private el(id: string): HTMLInputElement { return this.painel.querySelector<HTMLInputElement>(`#cfg-${id}`)!; }

  private desenhar() {
    const c = this.cfg;
    this.painel.innerHTML = `
      <h2>Configurações</h2>
      <fieldset><legend>Endereços</legend>
        ${this.campo("openjarvis_url", "OpenJarvis", c.openjarvis_url)}
        ${this.campo("gui_url", "Interface de texto", c.gui_url)}
        ${this.campo("ponte_url", "Ponte do Vard (opcional; vazio desliga)", c.ponte_url)}
      </fieldset>
      <fieldset><legend>Voz</legend>
        ${this.campo("nome", "Nome para chamar", c.nome)}
        ${this.campo("usuario", "Como te chamar (opcional)", c.usuario)}
        ${this.campo("variantes", "Variantes (separadas por vírgula)", c.variantes.join(", "))}
        ${this.campo("idioma", "Idioma do reconhecimento", c.idioma)}
        ${this.campo("voz", "Voz da fala", c.voz)}
        ${this.campo("velocidade", "Velocidade da fala", c.velocidade, "number", 'step="0.05" min="0.5" max="2"')}
        ${this.campo("finish_ms", "Silêncio para encerrar a fala (ms)", c.finish_ms, "number", 'step="50" min="200" max="3000"')}
        ${this.campo("limiar_vad", "Limiar do microfone", c.limiar_vad, "number", 'step="0.005" min="0.001" max="0.5"')}
        ${this.campo("instrucao_formato", "Instrução de formato", c.instrucao_formato)}
      </fieldset>
      <fieldset><legend>Janela e atalhos</legend>
        ${this.marca("sempre_no_topo", "Sempre no topo", c.sempre_no_topo)}
        ${this.marca("click_through", "Clique atravessa a janela", c.click_through)}
        ${this.marca("logon", "Iniciar com o Windows", false)}
        ${this.campo("atalho_falar", "Atalho: falar (segurar)", c.atalhos.falar)}
        ${this.campo("atalho_parar", "Atalho: interromper", c.atalhos.parar)}
        ${this.campo("atalho_mostrar", "Atalho: mostrar/ocultar", c.atalhos.mostrar)}
      </fieldset>
      <div id="cfg-msg" role="status"></div>
      <div class="acoes">
        <button id="cfg-testar" type="button">Testar OpenJarvis</button>
        <button id="cfg-salvar" type="button">Salvar</button>
        <button id="cfg-fechar" type="button">Fechar</button>
      </div>`;
    this.msg = this.painel.querySelector<HTMLElement>("#cfg-msg")!;
    this.logon = this.el("logon");
    this.painel.querySelector("#cfg-fechar")!.addEventListener("click", () => this.fechar());
    this.painel.querySelector("#cfg-salvar")!.addEventListener("click", () => { void this.salvar(); });
    this.painel.querySelector("#cfg-testar")!.addEventListener("click", () => { void this.testar(); });
    for (const id of ["openjarvis_url", "gui_url", "ponte_url"]) {
      const campo = this.el(id);
      const marcar = () => campo.classList.toggle("aviso", !urlLocal(campo.value));
      campo.addEventListener("input", marcar); marcar();
    }
  }

  private dizer(t: string, ruim = false) { this.msg.textContent = t; this.msg.classList.toggle("ruim", ruim); }

  /** Lê o formulário; números inválidos e textos vazios mantêm o valor atual. */
  lerFormulario(): Config {
    const num = (id: string, atual: number) => {
      const bruto = this.el(id).value.trim().replace(",", ".");
      const n = Number(bruto);
      return bruto !== "" && Number.isFinite(n) ? n : atual;
    };
    const txt = (id: string, atual: string) => this.el(id).value.trim() || atual;
    // Campos opcionais: vazio é um valor válido (desliga a ponte, tira o nome, idioma automático).
    const opc = (id: string) => this.el(id).value.trim();
    const c = this.cfg;
    return {
      ...c,
      openjarvis_url: txt("openjarvis_url", c.openjarvis_url), gui_url: txt("gui_url", c.gui_url), ponte_url: opc("ponte_url"),
      nome: txt("nome", c.nome), usuario: opc("usuario"),
      variantes: this.el("variantes").value.split(",").map((v) => v.trim()).filter(Boolean),
      idioma: opc("idioma"), voz: txt("voz", c.voz),
      velocidade: num("velocidade", c.velocidade), finish_ms: num("finish_ms", c.finish_ms), limiar_vad: num("limiar_vad", c.limiar_vad),
      instrucao_formato: txt("instrucao_formato", c.instrucao_formato),
      sempre_no_topo: this.el("sempre_no_topo").checked, click_through: this.el("click_through").checked,
      atalhos: { falar: txt("atalho_falar", c.atalhos.falar), parar: txt("atalho_parar", c.atalhos.parar), mostrar: txt("atalho_mostrar", c.atalhos.mostrar) },
    };
  }

  private async salvar() {
    const novo = this.lerFormulario();
    if (novo.variantes.length === 0) novo.variantes = [novo.nome];
    const exigeReinicio = (["openjarvis_url", "ponte_url", "nome", "idioma", "voz", "velocidade", "finish_ms", "limiar_vad", "instrucao_formato"] as const)
      .some((k) => novo[k] !== this.cfg[k]) || JSON.stringify(novo.variantes) !== JSON.stringify(this.cfg.variantes)
      || JSON.stringify(novo.atalhos) !== JSON.stringify(this.cfg.atalhos);
    try { await salvarConfig(novo); }
    catch (erro) { this.dizer(`Não consegui salvar: ${String(erro)}`, true); return; }
    Object.assign(this.cfg, novo);
    // O atalho de início só é mexido quando a caixa mudou (evita regravar o .lnk a cada Salvar).
    let falhouAtalho = false;
    if (this.logon.checked !== this.logonGuardado) {
      try { await invoke("definir_inicio_no_logon", { ligado: this.logon.checked }); this.logonGuardado = this.logon.checked; }
      catch { falhouAtalho = true; this.logon.checked = this.logonGuardado; }
    }
    this.deps.aoSalvar?.(this.cfg);
    const avisos = avisosDeUrl(novo);
    const partes = [falhouAtalho ? "Configuração salva, mas não consegui criar o atalho de início." : "Salvo."];
    if (exigeReinicio) partes.push("Reinicie o HUD para aplicar endereços, voz e atalhos.");
    if (avisos.length) partes.push(`Atenção: ${avisos.join("; ")}.`);
    this.dizer(partes.join(" "), avisos.length > 0 || falhouAtalho);
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
