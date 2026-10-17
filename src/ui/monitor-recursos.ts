/** Monitor de recursos do Vard (0.9.4 leve): mostra uso de memória e CPU por componente
 * na aba Geral das Configurações. Atualiza a cada 5 segundos enquanto a aba está aberta. */

export interface ComponenteRecursos {
  nome: string;
  memoria_mb: number;
  cpu_percent: number;
  pids: number[];
  detalhes: string;
}

export interface RecursosResposta {
  componentes: ComponenteRecursos[];
  externos: { nome: string; detalhes: string }[];
  total_memoria_mb: number;
  total_cpu_percent: number;
}

export interface DepsMonitorRecursos {
  /** URL base do núcleo (ex.: http://127.0.0.1:8000). */
  urlNucleo: () => string;
}

export class MonitorRecursos {
  private timer: ReturnType<typeof setInterval> | null = null;
  private conteudo!: HTMLElement;

  constructor(private raiz: HTMLElement, private deps: DepsMonitorRecursos) {}

  montar(): void {
    this.raiz.innerHTML = `
      <fieldset id="cfg-recursos-campo">
        <legend>Uso de recursos</legend>
        <div id="cfg-recursos-conteudo"><p>Carregando…</p></div>
      </fieldset>`;
    this.conteudo = this.raiz.querySelector("#cfg-recursos-conteudo")!;
    void this.atualizar();
  }

  ativar(): void {
    if (this.timer !== null) return;
    void this.atualizar();
    this.timer = setInterval(() => void this.atualizar(), 5000);
  }

  desativar(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private async atualizar(): Promise<void> {
    try {
      const url = `${this.deps.urlNucleo().replace(/\/+$/, "")}/recursos`;
      const r = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const dados = (await r.json()) as RecursosResposta;
      this.renderizar(dados);
    } catch (erro) {
      this.conteudo.innerHTML = `<p class="aviso">Não consegui ler os recursos: ${String(erro)}</p>`;
    }
  }

  private renderizar(dados: RecursosResposta): void {
    const linhas = dados.componentes.map((c) => {
      const detalhe = c.detalhes ? ` — ${c.detalhes}` : "";
      return `<tr>
        <td>${esc(c.nome)}</td>
        <td class="num">${c.memoria_mb.toFixed(1)} MB</td>
        <td class="num">${c.cpu_percent.toFixed(1)}%</td>
        <td class="detalhe">${esc(detalhe)}</td>
      </tr>`;
    }).join("");

    const externos = dados.externos.length
      ? `<p class="externos">Fora do Vard: ${dados.externos.map((e) => esc(e.nome)).join(", ")}</p>`
      : "";

    this.conteudo.innerHTML = `
      <table class="recursos-tabela">
        <thead><tr><th>Componente</th><th>Memória</th><th>CPU</th><th>Detalhes</th></tr></thead>
        <tbody>${linhas}</tbody>
        <tfoot><tr>
          <td><strong>Total</strong></td>
          <td class="num"><strong>${dados.total_memoria_mb.toFixed(1)} MB</strong></td>
          <td class="num"><strong>${dados.total_cpu_percent.toFixed(1)}%</strong></td>
          <td></td>
        </tr></tfoot>
      </table>
      ${externos}`;
  }
}

function esc(t: string): string {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}