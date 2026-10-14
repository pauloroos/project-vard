/**
 * Aba de cadastro manual de provedores de voz (0.6 Painéis).
 *
 * Renderiza lista + formulário de adicionar/editar; persiste via paineis.json.
 * Credencial por referência ao cofre; botão "Testar" verifica existência sem expor valor.
 * Tipos válidos: suad, kokoro, elevenlabs, gemini, fish.
 */
import { cofreExiste } from "../config/segredos";
import type { PaineisConfig, Provedor } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";

const TIPOS_VOZ = ["suad", "kokoro", "elevenlabs", "gemini", "fish"] as const;
export type TipoVoz = (typeof TIPOS_VOZ)[number];

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export interface DepsVozes {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
}

export class AbaPaineisVozes {
  private cfg!: PaineisConfig;
  private editando: number | null = null;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsVozes = {},
  ) {}

  async montar() {
    this.cfg = lerPaineis();
    this.desenhar();
  }

  private desenhar() {
    // Filtra apenas provedores que são de voz (tipo em TIPOS_VOZ)
    const vozes = this.cfg.provedores.filter((p): p is Provedor & { tipo: TipoVoz } =>
      TIPOS_VOZ.includes(p.tipo as TipoVoz),
    );

    const linhas = vozes.map((p, i) => {
      // Índice real no array completo de provedores
      const idxReal = this.cfg.provedores.indexOf(p);
      return `
      <tr data-idx="${idxReal}">
        <td>${esc(p.nome)}</td>
        <td>${esc(p.tipo)}</td>
        <td>${esc(p.url_base || "—")}</td>
        <td>${esc(p.modelo || "—")}</td>
        <td>${p.credencial_ref ? `<button type="button" class="btn-testar-cred-voz" data-ref="${esc(p.credencial_ref)}">Testar</button>` : "—"}</td>
        <td>
          <button type="button" class="btn-editar-voz" data-idx="${idxReal}">Editar</button>
          <button type="button" class="btn-remover-voz" data-idx="${idxReal}">Remover</button>
        </td>
      </tr>
    `;
    }).join("");

    const ativoSel = vozes.map((p) =>
      `<option value="${esc(p.id)}" ${this.cfg.ativo === p.id ? "selected" : ""}>${esc(p.nome)}</option>`,
    ).join("");

    const formHtml = this.editando !== null ? this.formularioEdicao(this.editando >= 0 ? this.cfg.provedores[this.editando] : undefined) : "";

    this.raiz.innerHTML = `
      <fieldset><legend>Vozes cadastradas</legend>
        ${vozes.length === 0 ? "<p>Nenhuma voz cadastrada.</p>" : `
        <table>
          <thead><tr><th>Nome</th><th>Tipo</th><th>URL base</th><th>Modelo</th><th>Credencial</th><th>Ações</th></tr></thead>
          <tbody>${linhas}</tbody>
        </table>`}
        <button id="btn-adicionar-voz" type="button">Adicionar voz</button>
      </fieldset>
      ${formHtml}
      <fieldset><legend>Voz ativa</legend>
        <label>Voz padrão<select id="sel-voz-ativa"><option value="">Nenhuma</option>${ativoSel}</select></label>
      </fieldset>
      <div id="msg-vozes" role="status"></div>
    `;
    this.vincularEventos();
  }

  private formularioEdicao(p?: Provedor): string {
    const titulo = p ? "Editar voz" : "Nova voz";
    const v = (k: keyof Provedor) => p ? esc(String(p[k] ?? "")) : "";
    const tipoOptions = TIPOS_VOZ.map((t) =>
      `<option value="${t}" ${p?.tipo === t ? "selected" : ""}>${t}</option>`,
    ).join("");

    return `
      <fieldset id="form-voz"><legend>${titulo}</legend>
        <label>ID<input id="voz-id" type="text" value="${v("id")}" ${p ? "readonly" : ""}></label>
        <label>Nome<input id="voz-nome" type="text" value="${v("nome")}"></label>
        <label>Tipo<select id="voz-tipo">${tipoOptions}</select></label>
        <label>URL base (opcional)<input id="voz-url" type="text" value="${v("url_base")}"></label>
        <label>Modelo (opcional)<input id="voz-modelo" type="text" value="${v("modelo")}"></label>
        <label>Referência da credencial (opcional)<input id="voz-cred" type="text" value="${v("credencial_ref")}"></label>
        <div class="acoes-form">
          <button id="btn-salvar-voz" type="button">Salvar</button>
          <button id="btn-cancelar-voz" type="button">Cancelar</button>
        </div>
      </fieldset>
    `;
  }

  private vincularEventos() {
    this.raiz.querySelector("#btn-adicionar-voz")?.addEventListener("click", () => {
      this.editando = -1;
      this.desenhar();
    });

    this.raiz.querySelectorAll(".btn-editar-voz").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.editando = Number((btn as HTMLElement).dataset.idx);
        this.desenhar();
      });
    });

    this.raiz.querySelectorAll(".btn-remover-voz").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number((btn as HTMLElement).dataset.idx);
        this.cfg.provedores.splice(idx, 1);
        if (this.cfg.ativo && !this.cfg.provedores.some((p) => p.id === this.cfg.ativo)) this.cfg.ativo = null;
        if (this.cfg.reserva && !this.cfg.provedores.some((p) => p.id === this.cfg.reserva)) this.cfg.reserva = null;
        this.persistir();
      });
    });

    this.raiz.querySelectorAll(".btn-testar-cred-voz").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ref = (btn as HTMLElement).dataset.ref!;
        const [tipo, id] = ref.split(":");
        const ok = await cofreExiste(tipo, id);
        this.msg(ok ? "Credencial encontrada no cofre." : "Credencial NÃO encontrada no cofre.", !ok);
      });
    });

    this.raiz.querySelector("#btn-salvar-voz")?.addEventListener("click", () => this.salvarFormulario());
    this.raiz.querySelector("#btn-cancelar-voz")?.addEventListener("click", () => {
      this.editando = null;
      this.desenhar();
    });

    this.raiz.querySelector("#sel-voz-ativa")?.addEventListener("change", (e) => {
      this.cfg.ativo = (e.target as HTMLSelectElement).value || null;
      this.persistir();
    });
  }

  private salvarFormulario() {
    const id = (this.raiz.querySelector("#voz-id") as HTMLInputElement).value.trim();
    const nome = (this.raiz.querySelector("#voz-nome") as HTMLInputElement).value.trim();
    const tipo = (this.raiz.querySelector("#voz-tipo") as HTMLSelectElement).value as TipoVoz;
    const url = (this.raiz.querySelector("#voz-url") as HTMLInputElement).value.trim() || "";
    const modelo = (this.raiz.querySelector("#voz-modelo") as HTMLInputElement).value.trim() || "";
    const cred = (this.raiz.querySelector("#voz-cred") as HTMLInputElement).value.trim() || undefined;

    if (!id || !nome || !tipo) {
      this.msg("Preencha todos os campos obrigatórios (ID, Nome, Tipo).", true);
      return;
    }

    if (!TIPOS_VOZ.includes(tipo)) {
      this.msg(`Tipo de voz desconhecido: ${tipo}. Use um dos: ${TIPOS_VOZ.join(", ")}.`, true);
      return;
    }

    if (this.editando === -1 && this.cfg.provedores.some((p) => p.id === id)) {
      this.msg(`Já existe uma voz com ID "${id}".`, true);
      return;
    }

    if (cred && !/^[\w.-]+:[\w.-]+$/.test(cred)) {
      this.msg("Referência de credencial deve estar no formato tipo:id.", true);
      return;
    }

    const novo: Provedor = { id, nome, tipo, url_base: url, modelo, credencial_ref: cred };

    if (this.editando === -1) {
      this.cfg.provedores.push(novo);
    } else if (this.editando !== null) {
      this.cfg.provedores[this.editando] = novo;
    }

    this.editando = null;
    this.persistir();
  }

  private persistir() {
    try {
      gravarPaineis(this.cfg);
      this.deps.aoMudar?.();
      this.desenhar();
      this.msg("Salvo.");
    } catch (e) {
      this.msg(`Erro ao salvar: ${String(e)}`, true);
    }
  }

  private msg(texto: string, ruim = false) {
    const el = this.raiz.querySelector("#msg-vozes") as HTMLElement;
    if (el) {
      el.textContent = texto;
      el.classList.toggle("ruim", ruim);
    }
  }
}