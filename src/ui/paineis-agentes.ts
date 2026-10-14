/**
 * Aba de configuração de agentes (0.6 Painéis).
 *
 * Renderiza formulário por agente (claude, codex, opencode, agy) com campos
 * "Modelo padrão" e "Modelos disponíveis". Persiste via paineis.json.
 * Validação: modelo padrão deve estar na lista de disponíveis (se lista não vazia).
 */
import type { Agente, PaineisConfig, EscolhaAgente } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";

const AGENTES: Agente[] = ["claude", "codex", "opencode", "agy"];
const ROTULOS: Record<Agente, string> = {
  claude: "Claude",
  codex: "Codex",
  opencode: "OpenCode",
  agy: "Antigravity",
};

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export interface DepsAgentes {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
}

export class AbaPaineisAgentes {
  private cfg!: PaineisConfig;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsAgentes = {},
  ) {}

  async montar() {
    this.cfg = await lerPaineis();
    this.desenhar();
  }

  private desenhar() {
    const formularios = AGENTES.map((ag) => {
      const escolha = this.cfg.agentes[ag] || { padrao: "", modelos: [] };
      const modelosStr = escolha.modelos.join(", ");
      return `
        <fieldset data-agente="${ag}">
          <legend>${ROTULOS[ag]}</legend>
          <label>Modelo padrão<input class="inp-padrao" type="text" value="${esc(escolha.padrao)}"></label>
          <label>Modelos disponíveis (separados por vírgula)<input class="inp-modelos" type="text" value="${esc(modelosStr)}"></label>
          <button type="button" class="btn-salvar-agente" data-ag="${ag}">Salvar ${ROTULOS[ag]}</button>
          <span class="msg-agente" role="status"></span>
        </fieldset>
      `;
    }).join("");

    this.raiz.innerHTML = `
      <div id="agentes-forms">${formularios}</div>
      <div id="msg-agentes-geral" role="status"></div>
    `;
    this.vincularEventos();
  }

  private vincularEventos() {
    this.raiz.querySelectorAll(".btn-salvar-agente").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ag = (btn as HTMLElement).dataset.ag as Agente;
        if (!ag) return;
        this.salvarAgente(ag, btn as HTMLElement);
      });
    });
  }

  private salvarAgente(ag: Agente, _btn: HTMLElement) {
    const fieldset = this.raiz.querySelector(`fieldset[data-agente="${ag}"]`)!;
    const padrao = (fieldset.querySelector(".inp-padrao") as HTMLInputElement).value.trim();
    const modelosRaw = (fieldset.querySelector(".inp-modelos") as HTMLInputElement).value.trim();
    const modelos = modelosRaw
      ? modelosRaw.split(",").map((m) => m.trim()).filter((m) => m.length > 0)
      : [];

    // Validação: se há modelos listados e padrão não vazio, padrão deve estar na lista
    if (padrao && modelos.length > 0 && !modelos.includes(padrao)) {
      this.msgLocal(fieldset, `Modelo padrão "${padrao}" não está na lista de disponíveis.`, true);
      return;
    }

    const escolha: EscolhaAgente = { padrao, modelos };
    this.cfg.agentes[ag] = escolha;

    try {
      void gravarPaineis(this.cfg);
      this.deps.aoMudar?.();
      this.msgLocal(fieldset, "Salvo.");
    } catch (e) {
      this.msgLocal(fieldset, `Erro ao salvar: ${String(e)}`, true);
    }
  }

  private msgLocal(fieldset: Element, texto: string, ruim = false) {
    const el = fieldset.querySelector(".msg-agente") as HTMLElement;
    if (el) {
      el.textContent = texto;
      el.classList.toggle("ruim", ruim);
    }
  }
}