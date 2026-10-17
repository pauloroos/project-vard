/** Aba Perfil (0.9.4): chamada (nome/variantes/usuário), perfis prontos em cards e campos do perfil.json.
 *
 * Contrato:
 * - Nome, variantes e "como te chamar" vieram da aba Geral; agora vivem aqui e sincronizam via deps.
 * - Os quatro campos do perfil.json (tom, personalidade, instruções, sobre_usuario) continuam abaixo.
 * - Perfis prontos preenchem tom/personalidade/instruções com confirmação quando já há texto escrito.
 * - A prévia montada vem da ponte: `GET /perfil/persona?nome=&usuario=`.
 */
import type { Perfil } from "../config/perfil";
import { PERFIL_PADRAO } from "../config/perfil";
import { abrirModal, desenharCards, type Card } from "./componentes";
import { PERFIS_PRONTOS, type PerfilPronto } from "./perfis-prontos";
import "./estilos/perfil.css";

export type CampoAssistente = "nome" | "usuario" | "variantes";

export interface DepsAbaPerfil {
  /** Nome atual (config.json). */
  nome: () => string;
  /** "Como te chamar" atual (config.json). */
  usuario: () => string;
  /** Variantes atuais (config.json). */
  variantes: () => string[];
  /** Lê o perfil.json salvo (padrão quando não existe). */
  ler: () => Promise<Perfil>;
  /** Grava o perfil.json. */
  gravar: (p: Perfil) => Promise<void>;
  /** Persona montada pela ponte; null quando a ponte está fora. */
  previa: () => Promise<string | null>;
  /** Mudou nome/usuário/variantes aqui: a aba Geral acompanha. */
  aoMudar?: (campo: CampoAssistente, valor: string) => void;
}

const CAMPOS_PERFIL = ["tom", "personalidade", "instrucoes", "sobre_usuario"] as const;

export class AbaPerfil {
  constructor(private raiz: HTMLElement, private deps: DepsAbaPerfil) {}

  /** Desenha chamada, perfis prontos e campos do perfil.json; carrega o perfil salvo. */
  async montar(): Promise<void> {
    this.raiz.innerHTML = `
      <fieldset>
        <legend>Chamada</legend>
        <div class="perfil-chamada">
          <label>Nome do assistente<input id="perfil-nome" type="text"></label>
          <label>Variantes (separadas por vírgula)<input id="perfil-variantes" type="text"></label>
          <label>Como te chamar (opcional)<input id="perfil-usuario" type="text"></label>
        </div>
      </fieldset>
      <fieldset>
        <legend>Perfis prontos</legend>
        <p class="nota">Escolher um perfil preenche tom, personalidade e instruções. O campo "Sobre você" nunca é alterado automaticamente.</p>
        <div id="perfil-prontos-lista"></div>
      </fieldset>
      <fieldset>
        <legend>Perfil do agente</legend>
        <div class="perfil-campos">
          <label>Tom<input id="perfil-tom" type="text"></label>
          <label>Personalidade<textarea id="perfil-personalidade" rows="3"></textarea></label>
          <label>Instruções<textarea id="perfil-instrucoes" rows="6"></textarea></label>
          <label>Sobre você<textarea id="perfil-sobre-usuario" rows="4"></textarea></label>
        </div>
        <div class="perfil-acoes">
          <button id="perfil-previa" type="button">Ver prévia da persona</button>
        </div>
        <pre id="perfil-texto" class="perfil-previa-texto" hidden></pre>
      </fieldset>`;

    // Sincroniza chamada com a aba Geral.
    for (const campo of ["nome", "usuario", "variantes"] as CampoAssistente[]) {
      this.campoChamada(campo).addEventListener("input", (ev) => {
        this.deps.aoMudar?.(campo, (ev.target as HTMLInputElement).value);
      });
    }

    this.el("perfil-previa").addEventListener("click", () => {
      void this.mostrarPrevia();
    });

    this.desenharPerfisProntos();

    let perfil: Perfil = { ...PERFIL_PADRAO };
    try {
      perfil = await this.deps.ler();
    } catch {
      /* sem perfil salvo: fica o padrão */
    }
    this.preencher(perfil);
  }

  /** Valor atual dos quatro campos do perfil.json. */
  lerPerfil(): Perfil {
    const valor: Perfil = { ...PERFIL_PADRAO };
    for (const campo of CAMPOS_PERFIL) valor[campo] = this.campoLongo(campo).value;
    return valor;
  }

  /** Grava o perfil.json com o que está no formulário. */
  async gravar(): Promise<void> {
    await this.deps.gravar(this.lerPerfil());
  }

  /** A aba Geral mudou nome/usuário/variantes: reflete aqui sem perder o resto do formulário. */
  definir(campo: CampoAssistente, valor: string) {
    const alvo = this.campoChamada(campo);
    if (alvo.value !== valor) alvo.value = valor;
  }

  /** Monta a persona pela ponte e mostra o texto na tela. */
  async mostrarPrevia(): Promise<void> {
    const caixa = this.el("perfil-texto") as HTMLPreElement;
    caixa.hidden = false;
    caixa.textContent = "Montando a persona...";
    const texto = await this.deps.previa();
    caixa.textContent = texto ?? "A ponte não respondeu. Confira o endereço na aba Sistema e tente de novo.";
  }

  private desenharPerfisProntos() {
    const alvo = this.el("perfil-prontos-lista");
    const cards: Card[] = PERFIS_PRONTOS.map((p) => ({
      id: p.id,
      titulo: p.rotulo,
      detalhes: [p.descricao],
      acoes: [{ rotulo: "Usar este perfil", primaria: true, aoClicar: () => this.aplicarPerfilPronto(p) }],
      busca: `${p.rotulo} ${p.descricao} ${p.tom} ${p.personalidade}`,
    }));
    desenharCards(alvo, cards, { vazio: "Nenhum perfil pronto disponível." });
  }

  private aplicarPerfilPronto(perfil: PerfilPronto) {
    const atual = this.lerPerfil();
    const temTexto = Boolean(atual.tom.trim() || atual.personalidade.trim() || atual.instrucoes.trim());
    const aplicar = () => {
      this.campoLongo("tom").value = perfil.tom;
      this.campoLongo("personalidade").value = perfil.personalidade;
      this.campoLongo("instrucoes").value = perfil.instrucoes;
    };
    if (!temTexto) {
      aplicar();
      return;
    }
    const corpo = document.createElement("dl");
    corpo.className = "modal-perfil-preview";
    const campos: [string, string][] = [
      ["Tom", perfil.tom],
      ["Personalidade", perfil.personalidade],
      ["Instruções", perfil.instrucoes],
    ];
    for (const [rotulo, valor] of campos) {
      const dt = document.createElement("dt");
      dt.textContent = rotulo;
      const dd = document.createElement("dd");
      dd.textContent = valor;
      corpo.append(dt, dd);
    }
    abrirModal({
      titulo: `Aplicar "${perfil.rotulo}"?`,
      corpo,
      acoes: [
        { rotulo: "Cancelar" },
        {
          rotulo: "Substituir",
          primaria: true,
          aoClicar: () => {
            aplicar();
            return true;
          },
        },
      ],
    });
  }

  private preencher(perfil: Perfil) {
    this.campoChamada("nome").value = this.deps.nome();
    this.campoChamada("usuario").value = this.deps.usuario();
    this.campoChamada("variantes").value = this.deps.variantes().join(", ");
    for (const campo of CAMPOS_PERFIL) this.campoLongo(campo).value = perfil[campo];
  }

  private el(id: string): HTMLElement {
    return this.raiz.querySelector<HTMLElement>(`#${id}`)!;
  }

  private campoChamada(campo: CampoAssistente): HTMLInputElement {
    return this.raiz.querySelector<HTMLInputElement>(`#perfil-${campo}`)!;
  }

  private campoLongo(campo: keyof Perfil): HTMLInputElement | HTMLTextAreaElement {
    return this.raiz.querySelector<HTMLInputElement | HTMLTextAreaElement>(`#perfil-${campo.replace(/_/g, "-")}`)!;
  }
}