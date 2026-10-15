/** Aba Perfil (T14a): tom, personalidade, instruções e sobre a pessoa, com prévia da persona.
 *
 * Contrato:
 * - Nome e "como te chamar" são os mesmos da aba Geral: vão para o config.json.
 * - Os outros quatro campos vão para o perfil.json (comandos ler_perfil/gravar_perfil).
 * - A prévia montada vem da ponte: `GET /perfil/persona?nome=&usuario=`.
 */
import type { Perfil } from "../config/perfil";
import { PERFIL_PADRAO } from "../config/perfil";

export type CampoAssistente = "nome" | "usuario";

export interface DepsAbaPerfil {
  /** Nome atual (config.json, aba Geral). */
  nome: () => string;
  /** "Como te chamar" atual (config.json, aba Geral). */
  usuario: () => string;
  /** Lê o perfil.json salvo (padrão quando não existe). */
  ler: () => Promise<Perfil>;
  /** Grava o perfil.json. */
  gravar: (p: Perfil) => Promise<void>;
  /** Persona montada pela ponte; null quando a ponte está fora. */
  previa: () => Promise<string | null>;
  /** Mudou nome/usuário aqui: a aba Geral acompanha. */
  aoMudar?: (campo: CampoAssistente, valor: string) => void;
}

const CAMPOS = ["tom", "personalidade", "instrucoes", "sobre_usuario"] as const;

export class AbaPerfil {
  constructor(private raiz: HTMLElement, private deps: DepsAbaPerfil) {}

  /** Desenha os 6 campos e carrega o perfil salvo. */
  async montar(): Promise<void> {
    this.raiz.innerHTML = `
      <fieldset>
        <legend>Perfil do agente</legend>
        <p class="nota">Nome e como te chamar são os mesmos da aba Geral (config.json). Tom, personalidade, instruções e sobre você vão para o perfil.json, que o núcleo lê na conversa.</p>
        <label>Nome do assistente<input id="perfil-nome" type="text"></label>
        <label>Como te chamar (opcional)<input id="perfil-usuario" type="text"></label>
        <label>Tom<input id="perfil-tom" type="text"></label>
        <label>Personalidade<textarea id="perfil-personalidade" rows="3"></textarea></label>
        <label>Instruções<textarea id="perfil-instrucoes" rows="6"></textarea></label>
        <label>Sobre você<textarea id="perfil-sobre-usuario" rows="4"></textarea></label>
        <div class="acoes"><button id="perfil-previa" type="button">Ver prévia da persona</button></div>
        <pre id="perfil-texto" hidden></pre>
      </fieldset>`;
    for (const campo of ["nome", "usuario"] as CampoAssistente[]) {
      this.campoTexto(campo).addEventListener("input", (ev) => {
        this.deps.aoMudar?.(campo, (ev.target as HTMLInputElement).value);
      });
    }
    this.el("perfil-previa").addEventListener("click", () => { void this.mostrarPrevia(); });
    let perfil: Perfil = { ...PERFIL_PADRAO };
    try { perfil = await this.deps.ler(); } catch { /* sem perfil salvo: fica o padrão */ }
    this.preencher(perfil);
  }

  /** Valor atual dos quatro campos do perfil.json. */
  lerPerfil(): Perfil {
    const valor: Perfil = { ...PERFIL_PADRAO };
    for (const campo of CAMPOS) valor[campo] = this.campoLongo(campo).value;
    return valor;
  }

  /** Grava o perfil.json com o que está no formulário. */
  async gravar(): Promise<void> {
    await this.deps.gravar(this.lerPerfil());
  }

  /** A aba Geral mudou nome/usuário: reflete aqui sem perder o resto do formulário. */
  definir(campo: CampoAssistente, valor: string) {
    const alvo = this.campoTexto(campo);
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

  private preencher(perfil: Perfil) {
    this.campoTexto("nome").value = this.deps.nome();
    this.campoTexto("usuario").value = this.deps.usuario();
    for (const campo of CAMPOS) this.campoLongo(campo).value = perfil[campo];
  }

  private el(id: string): HTMLElement {
    return this.raiz.querySelector<HTMLElement>(`#${id}`)!;
  }

  private campoTexto(campo: CampoAssistente): HTMLInputElement {
    return this.raiz.querySelector<HTMLInputElement>(`#perfil-${campo}`)!;
  }

  private campoLongo(campo: keyof Perfil): HTMLInputElement | HTMLTextAreaElement {
    // O campo `sobre_usuario` vira `#perfil-sobre-usuario`; ids na página usam hífen.
    return this.raiz.querySelector<HTMLInputElement | HTMLTextAreaElement>(`#perfil-${campo.replace(/_/g, "-")}`)!;
  }
}
