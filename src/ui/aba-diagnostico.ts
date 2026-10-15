/** Aba Diagnóstico (T10): executa checagens somente-leitura e exibe relatório.
 * Contrato:
 * - `rodar_diagnostico(tipo: "basico" | "preflight") -> ResultadoDiagnostico`
 * - Básico: só leitura (portas, processos, config, GPU/RAM); nunca inicia serviço.
 * - Preflight: checks completos quando integrações externas estiverem configuradas.
 * - Timeout/cancelamento mata só o job do diagnóstico.
 * - Relatório sanitizado (sem credenciais nem caminhos pessoais).
 */
import { invoke } from "@tauri-apps/api/core";

export interface Checagem {
  grupo: string;
  nome: string;
  estado: "ok" | "aviso" | "falha";
  frase: string;
}

export interface ResultadoDiagnostico {
  checagens: Checagem[];
  relatorio: string;
  duracao_ms: number;
}

export interface DepsAbaDiagnostico {
  copiar: (texto: string) => Promise<void>;
}

const DEPS_PADRAO: DepsAbaDiagnostico = {
  copiar: (texto) => navigator.clipboard.writeText(texto),
};

export class AbaDiagnostico {
  private resultado: ResultadoDiagnostico | null = null;
  private executando = false;
  private cancelado = false;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsAbaDiagnostico = DEPS_PADRAO,
  ) {}

  montar(): void {
    this.raiz.innerHTML = `
      <fieldset>
        <legend>Diagnóstico</legend>
        <p class="nota">O diagnóstico básico é somente-leitura: verifica portas, processos, configuração, GPU e RAM sem iniciar serviços nem carregar modelos.</p>
        <div class="botoes">
          <button id="diag-basico" type="button">Diagnóstico Básico</button>
          <button id="diag-preflight" type="button" disabled>Preflight Completo</button>
          <button id="diag-cancelar" type="button" disabled>Cancelar</button>
          <button id="diag-copiar" type="button" disabled>Copiar Relatório</button>
        </div>
        <div id="diag-progresso" hidden>
          <progress id="diag-barra" max="100" value="0"></progress>
          <span id="diag-texto">Executando...</span>
        </div>
        <div id="diag-resultado" hidden>
          <h3>Resultado</h3>
          <pre id="diag-relatorio"></pre>
          <div id="diag-resumo"></div>
        </div>
      </fieldset>
    `;

    this.el("diag-basico").addEventListener("click", () => this.executar("basico"));
    this.el("diag-preflight").addEventListener("click", () => this.executar("preflight"));
    this.el("diag-cancelar").addEventListener("click", () => this.cancelar());
    this.el("diag-copiar").addEventListener("click", () => this.copiarRelatorio());
  }

  private el(id: string): HTMLButtonElement | HTMLProgressElement | HTMLPreElement | HTMLDivElement | HTMLSpanElement {
    return this.raiz.querySelector(`#${id}`)!;
  }

  private async executar(tipo: "basico" | "preflight"): Promise<void> {
    if (this.executando) return;
    this.executando = true;
    this.cancelado = false;
    this.resultado = null;

    const btnBasico = this.el("diag-basico") as HTMLButtonElement;
    const btnPreflight = this.el("diag-preflight") as HTMLButtonElement;
    const btnCancelar = this.el("diag-cancelar") as HTMLButtonElement;
    const btnCopiar = this.el("diag-copiar") as HTMLButtonElement;
    const progresso = this.el("diag-progresso") as HTMLDivElement;
    const barra = this.el("diag-barra") as HTMLProgressElement;
    const texto = this.el("diag-texto") as HTMLSpanElement;
    const divResultado = this.el("diag-resultado") as HTMLDivElement;

    btnBasico.disabled = true;
    btnPreflight.disabled = true;
    btnCancelar.disabled = false;
    btnCopiar.disabled = true;
    progresso.hidden = false;
    divResultado.hidden = true;
    barra.value = 0;
    texto.textContent = `Executando diagnóstico ${tipo}...`;

    try {
      const resultado = await invoke<ResultadoDiagnostico>("rodar_diagnostico", { tipo });
      if (this.cancelado) {
        texto.textContent = "Diagnóstico cancelado.";
        return;
      }
      this.resultado = resultado;
      this.exibirResultado(resultado);
      btnCopiar.disabled = false;
    } catch (erro) {
      texto.textContent = `Erro: ${erro instanceof Error ? erro.message : String(erro)}`;
    } finally {
      this.executando = false;
      btnBasico.disabled = false;
      btnPreflight.disabled = tipo === "preflight"; // preflight ainda não implementado
      btnCancelar.disabled = true;
      progresso.hidden = true;
    }
  }

  private cancelar(): void {
    this.cancelado = true;
    const texto = this.el("diag-texto") as HTMLSpanElement;
    texto.textContent = "Cancelando...";
    // O backend deve respeitar o sinal de cancelamento via callback
    void invoke("cancelar_diagnostico").catch(() => {});
  }

  private exibirResultado(resultado: ResultadoDiagnostico): void {
    const divResultado = this.el("diag-resultado") as HTMLDivElement;
    const preRelatorio = this.el("diag-relatorio") as HTMLPreElement;
    const divResumo = this.el("diag-resumo") as HTMLDivElement;

    divResultado.hidden = false;
    preRelatorio.textContent = resultado.relatorio;

    const ok = resultado.checagens.filter((c) => c.estado === "ok").length;
    const av = resultado.checagens.filter((c) => c.estado === "aviso").length;
    const fa = resultado.checagens.filter((c) => c.estado === "falha").length;
    divResumo.textContent = `${ok} ok, ${av} avisos, ${fa} falhas (${resultado.duracao_ms} ms)`;
  }

  private async copiarRelatorio(): Promise<void> {
    if (!this.resultado) return;
    try {
      await this.deps.copiar(this.resultado.relatorio);
      const btnCopiar = this.el("diag-copiar") as HTMLButtonElement;
      const original = btnCopiar.textContent;
      btnCopiar.textContent = "Copiado!";
      setTimeout(() => { btnCopiar.textContent = original; }, 2000);
    } catch {
      // clipboard pode falhar em contexto inseguro
    }
  }
}