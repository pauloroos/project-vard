/**
 * Vozes cadastradas (0.6 Painéis → 0.9.3 Voz).
 *
 * O conteúdo do antigo "Painéis: Vozes" agora mora na seção Voz: este arquivo virou
 * o módulo das vozes cadastradas — tipos, validação, persistência em paineis.json e
 * o modal de adicionar/editar usado pela aba-voz. Credencial por referência ao cofre
 * (tipo:id); "Testar credencial" verifica existência sem expor valor.
 * Tipos válidos: suad, kokoro, elevenlabs, gemini, fish.
 */
import { cofreExiste } from "../config/segredos";
import type { PaineisConfig, Provedor } from "../config/paineis";
import { lerPaineis, gravarPaineis } from "../config/paineis";
import { abrirModal, campoModal, type AcaoModal, type ModalAberto } from "./componentes";

const TIPOS_VOZ = ["suad", "kokoro", "elevenlabs", "gemini", "fish"] as const;
export type TipoVoz = (typeof TIPOS_VOZ)[number];

/** Grupo (motor) da lista da aba Voz onde cada tipo cadastrado aparece. */
export const MOTOR_DO_TIPO: Record<TipoVoz, string> = {
  suad: "XTTS",
  kokoro: "Kokoro",
  elevenlabs: "ElevenLabs",
  gemini: "Gemini",
  fish: "Fish",
};

export function motorDoTipo(tipo: string): string {
  return MOTOR_DO_TIPO[tipo as TipoVoz] ?? "Cadastradas";
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export interface DepsVozes {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
}

export type VozCadastrada = Provedor & { tipo: TipoVoz };

export interface CamposVozCadastrada {
  id: string;
  nome: string;
  tipo: TipoVoz;
  url_base: string;
  modelo: string;
  credencial_ref: string;
}

/** Só as vozes (tipos de voz) dentro de paineis.json; provedores de cérebro ficam de fora. */
export function vozesCadastradas(cfg: PaineisConfig): VozCadastrada[] {
  return cfg.provedores.filter((p): p is VozCadastrada => TIPOS_VOZ.includes(p.tipo as TipoVoz));
}

/** Motivo para não salvar; null quando está tudo certo. Mesmos textos do formulário de 0.6. */
export function validarCamposVoz(c: CamposVozCadastrada, cfg: PaineisConfig, idOriginal: string | null): string | null {
  if (!c.id || !c.nome || !c.tipo) return "Preencha todos os campos obrigatórios (ID, Nome, Tipo).";
  if (!TIPOS_VOZ.includes(c.tipo)) return `Tipo de voz desconhecido: ${c.tipo}. Use um dos: ${TIPOS_VOZ.join(", ")}.`;
  if (idOriginal === null && cfg.provedores.some((p) => p.id === c.id)) return `Já existe uma voz com ID "${c.id}".`;
  if (c.credencial_ref && !/^[\w.-]+:[\w.-]+$/.test(c.credencial_ref)) return "Referência de credencial deve estar no formato tipo:id.";
  return null;
}

export interface OpcoesModalVoz {
  /** paineis.json como está agora (validação de id duplicado). */
  cfg: PaineisConfig;
  /** Informado = editar; omitido = adicionar. */
  atual?: VozCadastrada;
  tipoInicial?: TipoVoz;
  aoSalvar: (campos: CamposVozCadastrada, idOriginal: string | null) => void | Promise<void>;
  aoRemover?: (id: string) => void | Promise<void>;
  testarCredencial?: (ref: string) => Promise<boolean>;
  raiz?: HTMLElement;
}

/** Modal de adicionar/editar voz cadastrada (cadastro sempre em modal; nada de formulário jogado para baixo). */
export function abrirModalVoz(op: OpcoesModalVoz): ModalAberto {
  const atual = op.atual;
  const corpo = document.createElement("div");
  corpo.className = "modal-voz";
  const id = document.createElement("input");
  id.type = "text";
  id.value = atual?.id ?? "";
  id.readOnly = Boolean(atual);
  const nome = document.createElement("input");
  nome.type = "text";
  nome.value = atual?.nome ?? "";
  const tipo = document.createElement("select");
  for (const t of TIPOS_VOZ) tipo.append(new Option(MOTOR_DO_TIPO[t], t, false, t === (atual?.tipo ?? op.tipoInicial ?? TIPOS_VOZ[0])));
  const url = document.createElement("input");
  url.type = "text";
  url.value = atual?.url_base ?? "";
  const modelo = document.createElement("input");
  modelo.type = "text";
  modelo.value = atual?.modelo ?? "";
  const cred = document.createElement("input");
  cred.type = "text";
  cred.value = atual?.credencial_ref ?? "";
  corpo.append(
    campoModal("ID", id, "Como a voz é identificada; não muda depois de salva."),
    campoModal("Nome", nome),
    campoModal("Tipo", tipo),
    campoModal("URL base (opcional)", url, "Endereço do serviço que fala esta voz."),
    campoModal("Modelo (opcional)", modelo),
    campoModal("Referência da credencial (opcional)", cred, "Formato tipo:id, apontando para o cofre."),
  );
  const ler = (): CamposVozCadastrada => ({
    id: id.value.trim(),
    nome: nome.value.trim(),
    tipo: tipo.value as TipoVoz,
    url_base: url.value.trim(),
    modelo: modelo.value.trim(),
    credencial_ref: cred.value.trim(),
  });

  let modal!: ModalAberto;
  const avisar = (texto: string, ruim = false) => modal.avisar(texto, ruim);
  const acoes: AcaoModal[] = [
    {
      rotulo: "Salvar",
      primaria: true,
      aoClicar: async () => {
        const campos = ler();
        const erro = validarCamposVoz(campos, op.cfg, atual?.id ?? null);
        if (erro) {
          avisar(erro, true);
          return false;
        }
        await op.aoSalvar(campos, atual?.id ?? null);
      },
    },
    {
      rotulo: "Testar credencial",
      aoClicar: async () => {
        const ref = cred.value.trim();
        if (!ref) {
          avisar("Informe a referência da credencial (tipo:id).", true);
          return false;
        }
        const ok = await (op.testarCredencial ?? cofreExisteRef)(ref);
        avisar(ok ? "Credencial encontrada no cofre." : "Credencial NÃO encontrada no cofre.", !ok);
        return false;
      },
    },
  ];
  if (atual && op.aoRemover) {
    acoes.push({
      rotulo: "Remover",
      aoClicar: async () => {
        await op.aoRemover!(atual.id);
      },
    });
  }
  acoes.push({ rotulo: "Cancelar" });
  modal = abrirModal({ titulo: atual ? "Editar voz" : "Adicionar voz", corpo, acoes }, op.raiz);
  return modal;
}

/** Credencial padrão do modal: pergunta ao cofre pela referência tipo:id, sem expor o valor. */
async function cofreExisteRef(ref: string): Promise<boolean> {
  const [tipo, id] = ref.split(":");
  return cofreExiste(tipo, id);
}

export class AbaPaineisVozes {
  private cfg!: PaineisConfig;
  private editando: number | null = null;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsVozes = {},
  ) {}

  async montar() {
    this.cfg = await lerPaineis();
    this.desenhar();
  }

  private desenhar() {
    // Filtra apenas provedores que são de voz (tipo em TIPOS_VOZ)
    const vozes = this.cfg.provedores.filter((p): p is VozCadastrada =>
      TIPOS_VOZ.includes(p.tipo as TipoVoz),
    );

    const linhas = vozes.map((p) => {
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
      `<option value="${t}" ${p?.tipo === t ? "selected" : ""}>${MOTOR_DO_TIPO[t]}</option>`,
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
    const cred = (this.raiz.querySelector("#voz-cred") as HTMLInputElement).value.trim() || "";

    const erro = validarCamposVoz({ id, nome, tipo, url_base: url, modelo, credencial_ref: cred }, this.cfg, this.editando === -1 ? null : id);
    if (erro) {
      this.msg(erro, true);
      return;
    }

    const novo: Provedor = { id, nome, tipo, url_base: url, modelo, credencial_ref: cred || undefined };

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
    const el = this.raiz.querySelector("#msg-vozes") as HTMLElement;
    if (el) {
      el.textContent = texto;
      el.classList.toggle("ruim", ruim);
    }
  }
}
