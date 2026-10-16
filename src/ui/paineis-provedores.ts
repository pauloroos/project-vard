/**
 * Aba de cadastro manual de provedores (0.6 Painéis) e CLIs de agente (0.8 T17a).
 *
 * Renderiza lista + formulário de adicionar/editar; persiste via paineis.json.
 * Credencial por referência ao cofre; botão "Testar" verifica existência sem expor valor.
 * Tipos cli-claude/cli-agy só aparecem quando detectados pela ponte (`GET /cli/detectar`);
 * cadastrar ou editar um provedor cli pede confirmação com o aviso do C11.
 */
import { cofreExiste } from "../config/segredos";
import { TIPOS_CLI, type PaineisConfig, type Provedor } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";
import type { CliDetectada } from "../config/clis";

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Aviso do C11 mostrado antes de gravar um provedor cli. */
export const AVISO_CLI =
  "Atenção: a CLI roda com poder completo no seu PC; com yolo, sem pedir permissão.";

const ehTipoCli = (tipo: string): boolean => (TIPOS_CLI as readonly string[]).includes(tipo);

export interface DepsProvedores {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
  /** CLIs instaladas (núcleo, `GET /cli/detectar`); padrão: nenhuma detectada. */
  detectar?: () => Promise<CliDetectada[]>;
}

export class AbaPaineisProvedores {
  private cfg!: PaineisConfig;
  private editando: number | null = null;
  private clis: CliDetectada[] = [];
  private pendente: Provedor | null = null;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsProvedores = {},
  ) {}

  async montar() {
    this.cfg = await lerPaineis();
    this.clis = await this.deps.detectar?.() ?? [];
    this.desenhar();
  }

  private desenhar() {
    const linhas = this.cfg.provedores.map((p, i) => `
      <tr data-idx="${i}">
        <td>${esc(p.nome)}</td>
        <td>${esc(p.tipo)}</td>
        <td>${esc(p.url_base) || "—"}</td>
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
    const cliEditando = p ? ehTipoCli(p.tipo) : false;
    const tiposCli = this.clis.filter((c) => c.instalada);
    const listaTipos = `<datalist id="lista-tipos">${tiposCli.map((c) => `<option value="${esc(c.tipo)}"></option>`).join("")}</datalist>`;
    const cliAtual = tiposCli.find((c) => c.tipo === (p?.tipo ?? ""));
    const listaModelos = `<datalist id="lista-modelo">${(cliAtual?.modelos ?? []).map((m) => `<option value="${esc(m)}"></option>`).join("")}</datalist>`;
    return `
      <fieldset id="form-provedor"><legend>${titulo}</legend>
        <label>ID<input id="prov-id" type="text" value="${v("id")}" ${p ? "readonly" : ""}></label>
        <label>Nome<input id="prov-nome" type="text" value="${v("nome")}"></label>
        <label>Tipo<input id="prov-tipo" type="text" list="lista-tipos" value="${v("tipo")}"></label>
        ${listaTipos}
        <label>Modelo<input id="prov-modelo" type="text" list="lista-modelo" value="${v("modelo")}"></label>
        ${listaModelos}
        <div id="campos-http" ${cliEditando ? "hidden" : ""}>
          <label>URL base<input id="prov-url" type="text" value="${v("url_base")}"></label>
          <label>Referência da credencial (opcional)<input id="prov-cred" type="text" value="${v("credencial_ref")}"></label>
        </div>
        <div id="campos-cli" ${cliEditando ? "" : "hidden"}>
          <label><input id="prov-yolo" type="checkbox" ${p?.yolo !== false ? "checked" : ""}> yolo (sem pedir permissão)</label>
          <label><input id="prov-enxuto" type="checkbox" ${p?.enxuto ? "checked" : ""}> enxuto (só ferramentas do Vard)</label>
          <label>Esforço (opcional)<input id="prov-esforco" type="text" value="${v("esforco")}"></label>
        </div>
        <div id="confirmar-cli" role="alertdialog" hidden>
          <p id="aviso-cli">${esc(AVISO_CLI)}</p>
          <button id="btn-confirmar-cli" type="button">Confirmar e salvar</button>
          <button id="btn-cancelar-cli" type="button">Cancelar</button>
        </div>
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
      this.pendente = null;
      this.desenhar();
    });

    this.raiz.querySelector("#prov-tipo")?.addEventListener("input", () => this.ajustarCamposTipo());

    this.raiz.querySelector("#btn-confirmar-cli")?.addEventListener("click", () => {
      if (!this.pendente) return;
      const novo = this.pendente;
      this.pendente = null;
      if (this.editando === -1) this.cfg.provedores.push(novo);
      else if (this.editando !== null) this.cfg.provedores[this.editando] = novo;
      this.editando = null;
      this.persistir();
    });

    this.raiz.querySelector("#btn-cancelar-cli")?.addEventListener("click", () => {
      this.pendente = null;
      this.raiz.querySelector("#confirmar-cli")?.setAttribute("hidden", "");
      this.msg("Cadastro de CLI cancelado; nada foi gravado.");
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

  /** Tipo cli mostra yolo/enxuto/esforco e esconde url/credencial; a lista de modelos vem da detecção. */
  private ajustarCamposTipo() {
    const campo = this.raiz.querySelector("#prov-tipo") as HTMLInputElement | null;
    const tipo = campo?.value.trim() ?? "";
    const cli = ehTipoCli(tipo);
    this.raiz.querySelector("#campos-cli")?.toggleAttribute("hidden", !cli);
    this.raiz.querySelector("#campos-http")?.toggleAttribute("hidden", cli);
    const lista = this.raiz.querySelector("#lista-modelo");
    if (lista) {
      const modelos = this.clis.find((c) => c.tipo === tipo)?.modelos ?? [];
      lista.innerHTML = modelos.map((m) => `<option value="${esc(m)}"></option>`).join("");
    }
    this.pendente = null;
    this.raiz.querySelector("#confirmar-cli")?.setAttribute("hidden", "");
  }

  private salvarFormulario() {
    const id = (this.raiz.querySelector("#prov-id") as HTMLInputElement).value.trim();
    const nome = (this.raiz.querySelector("#prov-nome") as HTMLInputElement).value.trim();
    const tipo = (this.raiz.querySelector("#prov-tipo") as HTMLInputElement).value.trim();
    const modelo = (this.raiz.querySelector("#prov-modelo") as HTMLInputElement).value.trim();
    const cli = ehTipoCli(tipo);
    const url = cli ? "" : (this.raiz.querySelector("#prov-url") as HTMLInputElement).value.trim();
    const cred = cli ? "" : (this.raiz.querySelector("#prov-cred") as HTMLInputElement).value.trim();

    if (!id || !nome || !tipo || !modelo || (!cli && !url)) {
      this.msg(cli
        ? "Preencha todos os campos obrigatórios (ID, Nome, Tipo, Modelo)."
        : "Preencha todos os campos obrigatórios (ID, Nome, Tipo, URL, Modelo).", true);
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

    let novo: Provedor = { id, nome, tipo, url_base: url, modelo, credencial_ref: cli ? undefined : (cred || undefined) };
    if (cli) {
      novo = {
        ...novo,
        yolo: (this.raiz.querySelector("#prov-yolo") as HTMLInputElement).checked,
        enxuto: (this.raiz.querySelector("#prov-enxuto") as HTMLInputElement).checked,
      };
      const esforco = (this.raiz.querySelector("#prov-esforco") as HTMLInputElement).value.trim();
      if (esforco) novo.esforco = esforco;
      // Poder completo no PC do usuário: gravar cli pede confirmação (C11).
      this.pendente = novo;
      this.raiz.querySelector("#confirmar-cli")?.removeAttribute("hidden");
      this.msg("Confirme para gravar o provedor de CLI.");
      return;
    }

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
