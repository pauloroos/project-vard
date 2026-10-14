/**
 * Aba de cadastro manual de provedores (0.6 Painéis).
 *
 * Renderiza lista + formulário de adicionar/editar; persiste via paineis.json.
 * Credencial por referência ao cofre; botão "Testar" verifica existência sem expor valor.
 */
import { cofreExiste } from "../config/segredos";
import type { PaineisConfig, Provedor } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export interface DepsProvedores {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
}

export class AbaPaineisProvedores {
  private cfg!: PaineisConfig;
  private editando: number | null = null;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsProvedores = {},
  ) {}

  async montar() {
    this.cfg = await lerPaineis();
    this.desenhar();
  }

  private desenhar() {
    const linhas = this.cfg.provedores.map((p, i) => `
      <tr data-idx="${i}">
        <td>${esc(p.nome)}</td>
        <td>${esc(p.tipo)}</td>
        <td>${esc(p.url_base)}</td>
        <td>${esc(p.modelo)}</td>
        <td>${p.credencial_ref ? `<button type="button" class="btn-testar-cred" data-ref="${esc(p.credencial_ref)}">Testar</button>` : "—"}</td>
        <td>
          <button type="button" class="btn-editar" data-idx="${i}">Editar</button>
          <button type="button" class="btn-remover" data-idx="${i}">Remover</button>
        </td>
      </tr>
    `).join("");

    const ativoSel = this.cfg.provedores.map((p) =>
      `<option value="${esc(p.id)}" ${this.cfg.ativo === p.id ? "selected" : ""}>${esc(p.nome)}</option>`
    ).join("");
    const reservaSel = this.cfg.provedores.map((p) =>
      `<option value="${esc(p.id)}" ${this.cfg.reserva === p.id ? "selected" : ""}>${esc(p.nome)}</option>`
    ).join("");

    const formHtml = this.editando !== null ? this.formularioEdicao(this.cfg.provedores[this.editando]) : "";

    this.raiz.innerHTML = `
      <fieldset><legend>Provedores cadastrados</legend>
        ${this.cfg.provedores.length === 0 ? "<p>Nenhum provedor cadastrado.</p>" : `
        <table>
          <thead><tr><th>Nome</th><th>Tipo</th><th>URL base</th><th>Modelo</th><th>Credencial</th><th>Ações</th></tr></thead>
          <tbody>${linhas}</tbody>
        </table>`}
        <button id="btn-adicionar-provedor" type="button">Adicionar provedor</button>
      </fieldset>
      ${formHtml}
      <fieldset><legend>Seleção</legend>
        <label>Ativo<select id="sel-ativo"><option value="">Nenhum</option>${ativoSel}</select></label>
        <label>Reserva<select id="sel-reserva"><option value="">Nenhuma</option>${reservaSel}</select></label>
      </fieldset>
      <div id="msg-provedores" role="status"></div>
    `;

    this.vincularEventos();
  }

  private formularioEdicao(p?: Provedor): string {
    const titulo = p ? "Editar provedor" : "Novo provedor";
    const v = (k: keyof Provedor) => p ? esc(String(p[k] ?? "")) : "";
    return `
      <fieldset id="form-provedor"><legend>${titulo}</legend>
        <label>ID<input id="prov-id" type="text" value="${v("id")}" ${p ? "readonly" : ""}></label>
        <label>Nome<input id="prov-nome" type="text" value="${v("nome")}"></label>
        <label>Tipo<input id="prov-tipo" type="text" value="${v("tipo")}"></label>
        <label>URL base<input id="prov-url" type="text" value="${v("url_base")}"></label>
        <label>Modelo<input id="prov-modelo" type="text" value="${v("modelo")}"></label>
        <label>Referência da credencial (opcional)<input id="prov-cred" type="text" value="${v("credencial_ref")}"></label>
        <div class="acoes-form">
          <button id="btn-salvar-provedor" type="button">Salvar</button>
          <button id="btn-cancelar-provedor" type="button">Cancelar</button>
        </div>
      </fieldset>
    `;
  }

  private vincularEventos() {
    this.raiz.querySelector("#btn-adicionar-provedor")?.addEventListener("click", () => {
      this.editando = -1; // sentinel para novo
      this.desenhar();
    });

    this.raiz.querySelectorAll(".btn-editar").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.editando = Number((btn as HTMLElement).dataset.idx);
        this.desenhar();
      });
    });

    this.raiz.querySelectorAll(".btn-remover").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number((btn as HTMLElement).dataset.idx);
        this.cfg.provedores.splice(idx, 1);
        // Ajusta ativo/reserva se apontavam para o removido
        if (this.cfg.ativo && !this.cfg.provedores.some((p) => p.id === this.cfg.ativo)) this.cfg.ativo = null;
        if (this.cfg.reserva && !this.cfg.provedores.some((p) => p.id === this.cfg.reserva)) this.cfg.reserva = null;
        this.persistir();
      });
    });

    this.raiz.querySelectorAll(".btn-testar-cred").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ref = (btn as HTMLElement).dataset.ref!;
        const ok = await cofreExiste(ref.split(":")[0], ref.split(":")[1]);
        this.msg(ok ? "Credencial encontrada no cofre." : "Credencial NÃO encontrada no cofre.", !ok);
      });
    });

    this.raiz.querySelector("#btn-salvar-provedor")?.addEventListener("click", () => this.salvarFormulario());
    this.raiz.querySelector("#btn-cancelar-provedor")?.addEventListener("click", () => {
      this.editando = null;
      this.desenhar();
    });

    this.raiz.querySelector("#sel-ativo")?.addEventListener("change", (e) => {
      this.cfg.ativo = (e.target as HTMLSelectElement).value || null;
      this.persistir();
    });
    this.raiz.querySelector("#sel-reserva")?.addEventListener("change", (e) => {
      this.cfg.reserva = (e.target as HTMLSelectElement).value || null;
      this.persistir();
    });
  }

  private salvarFormulario() {
    const id = (this.raiz.querySelector("#prov-id") as HTMLInputElement).value.trim();
    const nome = (this.raiz.querySelector("#prov-nome") as HTMLInputElement).value.trim();
    const tipo = (this.raiz.querySelector("#prov-tipo") as HTMLInputElement).value.trim();
    const url = (this.raiz.querySelector("#prov-url") as HTMLInputElement).value.trim();
    const modelo = (this.raiz.querySelector("#prov-modelo") as HTMLInputElement).value.trim();
    const cred = (this.raiz.querySelector("#prov-cred") as HTMLInputElement).value.trim() || undefined;

    if (!id || !nome || !tipo || !url || !modelo) {
      this.msg("Preencha todos os campos obrigatórios (ID, Nome, Tipo, URL, Modelo).", true);
      return;
    }

    // ID duplicado só é erro em novos; edição mantém o próprio ID
    if (this.editando === -1 && this.cfg.provedores.some((p) => p.id === id)) {
      this.msg(`Já existe um provedor com ID "${id}".`, true);
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
      void gravarPaineis(this.cfg);
      this.deps.aoMudar?.();
      this.desenhar();
      this.msg("Salvo.");
    } catch (e) {
      this.msg(`Erro ao salvar: ${String(e)}`, true);
    }
  }

  private msg(texto: string, ruim = false) {
    const el = this.raiz.querySelector("#msg-provedores") as HTMLElement;
    if (el) {
      el.textContent = texto;
      el.classList.toggle("ruim", ruim);
    }
  }
}