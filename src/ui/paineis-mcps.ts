/**
 * Aba de cadastro manual de servidores MCP (0.6 Painéis).
 *
 * Renderiza lista + formulário de adicionar/editar; persiste via paineis.json.
 * Credencial por referência ao cofre; botão "Testar" verifica existência sem expor valor.
 * Tipos: stdio (command + args) e http (url).
 */
import { cofreExiste } from "../config/segredos";
import type { PaineisConfig, Mcp } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export interface DepsMcps {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
}

export class AbaPaineisMcps {
  private cfg!: PaineisConfig;
  private editando: number | null = null;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsMcps = {},
  ) {}

  async montar() {
    this.cfg = lerPaineis();
    this.desenhar();
  }

  private desenhar() {
    const linhas = this.cfg.mcps.map((m, i) => `
      <tr data-idx="${i}">
        <td>${esc(m.nome)}</td>
        <td>${m.command ? "stdio" : "http"}</td>
        <td>${m.habilitado ? "Sim" : "Não"}</td>
        <td>${m.credencial_ref ? `<button type="button" class="btn-testar-cred-mcp" data-ref="${esc(m.credencial_ref)}">Testar</button>` : "—"}</td>
        <td>
          <button type="button" class="btn-toggle-mcp" data-idx="${i}">${m.habilitado ? "Desabilitar" : "Habilitar"}</button>
          <button type="button" class="btn-editar-mcp" data-idx="${i}">Editar</button>
          <button type="button" class="btn-remover-mcp" data-idx="${i}">Remover</button>
        </td>
      </tr>
    `).join("");

    const formHtml = this.editando !== null
      ? this.formularioEdicao(this.editando >= 0 ? this.cfg.mcps[this.editando] : undefined)
      : "";

    this.raiz.innerHTML = `
      <fieldset><legend>Servidores MCP cadastrados</legend>
        ${this.cfg.mcps.length === 0 ? "<p>Nenhum MCP cadastrado.</p>" : `
        <table>
          <thead><tr><th>Nome</th><th>Tipo</th><th>Habilitado</th><th>Credencial</th><th>Ações</th></tr></thead>
          <tbody>${linhas}</tbody>
        </table>`}
        <button id="btn-adicionar-mcp" type="button">Adicionar MCP</button>
      </fieldset>
      ${formHtml}
      <div id="msg-mcps" role="status"></div>
    `;
    this.vincularEventos();
  }

  private formularioEdicao(m?: Mcp): string {
    const titulo = m ? "Editar MCP" : "Novo MCP";
    const v = (k: keyof Mcp) => m ? esc(String(m[k] ?? "")) : "";
    const tipo = m?.command ? "stdio" : "http";
    const argsStr = m?.args ? m.args.join(" ") : "";

    return `
      <fieldset id="form-mcp"><legend>${titulo}</legend>
        <label>ID<input id="mcp-id" type="text" value="${v("id")}" ${m ? "readonly" : ""}></label>
        <label>Nome<input id="mcp-nome" type="text" value="${v("nome")}"></label>
        <label>Tipo
          <select id="mcp-tipo">
            <option value="stdio" ${tipo === "stdio" ? "selected" : ""}>stdio (comando local)</option>
            <option value="http" ${tipo === "http" ? "selected" : ""}>HTTP (Streamable)</option>
          </select>
        </label>
        <div id="campo-stdio" style="display:${tipo === "stdio" ? "block" : "none"}">
          <label>Command<input id="mcp-command" type="text" value="${v("command")}"></label>
          <label>Args (separados por espaço)<input id="mcp-args" type="text" value="${esc(argsStr)}"></label>
        </div>
        <div id="campo-http" style="display:${tipo === "http" ? "block" : "none"}">
          <label>URL<input id="mcp-url" type="text" value="${v("url")}"></label>
        </div>
        <label>Referência da credencial (opcional)<input id="mcp-cred" type="text" value="${v("credencial_ref")}"></label>
        <div class="acoes-form">
          <button id="btn-salvar-mcp" type="button">Salvar</button>
          <button id="btn-cancelar-mcp" type="button">Cancelar</button>
        </div>
      </fieldset>
    `;
  }

  private vincularEventos() {
    // Toggle tipo no formulário
    this.raiz.querySelector("#mcp-tipo")?.addEventListener("change", (e) => {
      const tipo = (e.target as HTMLSelectElement).value;
      const stdio = this.raiz.querySelector("#campo-stdio") as HTMLElement;
      const http = this.raiz.querySelector("#campo-http") as HTMLElement;
      if (stdio) stdio.style.display = tipo === "stdio" ? "block" : "none";
      if (http) http.style.display = tipo === "http" ? "block" : "none";
    });

    this.raiz.querySelector("#btn-adicionar-mcp")?.addEventListener("click", () => {
      this.editando = -1;
      this.desenhar();
    });

    this.raiz.querySelectorAll(".btn-editar-mcp").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.editando = Number((btn as HTMLElement).dataset.idx);
        this.desenhar();
      });
    });

    this.raiz.querySelectorAll(".btn-remover-mcp").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number((btn as HTMLElement).dataset.idx);
        this.cfg.mcps.splice(idx, 1);
        this.persistir();
      });
    });

    this.raiz.querySelectorAll(".btn-toggle-mcp").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number((btn as HTMLElement).dataset.idx);
        this.cfg.mcps[idx].habilitado = !this.cfg.mcps[idx].habilitado;
        this.persistir();
      });
    });

    this.raiz.querySelectorAll(".btn-testar-cred-mcp").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ref = (btn as HTMLElement).dataset.ref!;
        const [tipo, id] = ref.split(":");
        const ok = await cofreExiste(tipo, id);
        this.msg(ok ? "Credencial encontrada no cofre." : "Credencial NÃO encontrada no cofre.", !ok);
      });
    });

    this.raiz.querySelector("#btn-salvar-mcp")?.addEventListener("click", () => this.salvarFormulario());
    this.raiz.querySelector("#btn-cancelar-mcp")?.addEventListener("click", () => {
      this.editando = null;
      this.desenhar();
    });
  }

  private salvarFormulario() {
    const id = (this.raiz.querySelector("#mcp-id") as HTMLInputElement).value.trim();
    const nome = (this.raiz.querySelector("#mcp-nome") as HTMLInputElement).value.trim();
    const tipo = (this.raiz.querySelector("#mcp-tipo") as HTMLSelectElement).value;
    const command = (this.raiz.querySelector("#mcp-command") as HTMLInputElement).value.trim();
    const argsRaw = (this.raiz.querySelector("#mcp-args") as HTMLInputElement).value.trim();
    const url = (this.raiz.querySelector("#mcp-url") as HTMLInputElement).value.trim();
    const cred = (this.raiz.querySelector("#mcp-cred") as HTMLInputElement).value.trim() || undefined;

    if (!id || !nome) {
      this.msg("Preencha todos os campos obrigatórios (ID, Nome).", true);
      return;
    }

    if (this.editando === -1 && this.cfg.mcps.some((m) => m.id === id)) {
      this.msg(`Já existe um MCP com ID "${id}".`, true);
      return;
    }

    if (tipo === "stdio" && !command) {
      this.msg("MCP stdio exige o campo Command.", true);
      return;
    }

    if (tipo === "http" && !url) {
      this.msg("MCP HTTP exige o campo URL.", true);
      return;
    }

    if (cred && !/^[\w.-]+:[\w.-]+$/.test(cred)) {
      this.msg("Referência de credencial deve estar no formato tipo:id.", true);
      return;
    }

    const args = tipo === "stdio" && argsRaw ? argsRaw.split(/\s+/) : undefined;

    const novo: Mcp = {
      id,
      nome,
      habilitado: this.editando !== null && this.editando >= 0
        ? this.cfg.mcps[this.editando].habilitado
        : true,
      ...(tipo === "stdio" ? { command, args } : { url }),
      credencial_ref: cred,
    };

    if (this.editando === -1) {
      this.cfg.mcps.push(novo);
    } else if (this.editando !== null) {
      this.cfg.mcps[this.editando] = novo;
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
    const el = this.raiz.querySelector("#msg-mcps") as HTMLElement;
    if (el) {
      el.textContent = texto;
      el.classList.toggle("ruim", ruim);
    }
  }
}