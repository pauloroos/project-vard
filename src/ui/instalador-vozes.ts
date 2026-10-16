/**
 * Tela do Instalador de Vozes (T5b).
 * Lista pacotes opcionais, mostra licença antes de instalar,
 * exibe progresso via SSE e permite cancelar/remover.
 */

export interface PacoteManifesto {
  id: string;
  nome: string;
  versao: string;
  tipo: string;
  descricao: string;
  bytes_download: number;
  bytes_instalado: number;
  licenca_url: string;
  licenca_nome: string;
  indisponivel: boolean;
  motivo_indisponivel?: string | null;
}

export interface EstadoPacote {
  instalado: boolean;
  ativo: boolean;
  versao_instalada?: string;
}

export interface ProgressoInstalacao {
  estado: "aguardando" | "baixando" | "verificando" | "instalando" | "concluido" | "falhou" | "cancelado";
  bytes_baixados: number;
  bytes_total: number;
  erro?: string | null;
}

export interface DepsInstaladorVozes {
  /** Base URL do núcleo (ex: http://127.0.0.1:4700) */
  baseUrl: string;
  /** Callback para notificações de status ao usuário */
  notificar: (msg: string, erro?: boolean) => void;
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

function formatarBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const unidades = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), unidades.length - 1);
  const valor = bytes / Math.pow(1024, i);
  return `${valor.toFixed(i === 0 ? 0 : 1)} ${unidades[i]}`;
}

export class InstaladorVozes {
  private raiz: HTMLElement;
  private deps: DepsInstaladorVozes;
  private pacotes: PacoteManifesto[] = [];
  private estados: Record<string, EstadoPacote> = {};
  private abortControllers: Record<string, AbortController> = {};

  constructor(raiz: HTMLElement, deps: DepsInstaladorVozes) {
    this.raiz = raiz;
    this.deps = deps;
  }

  async montar(): Promise<void> {
    await this.carregarDados();
    this.renderizar();
  }

  private async carregarDados(): Promise<void> {
    try {
      const resp = await fetch(`${this.deps.baseUrl}/pacotes`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const dados = await resp.json();
      this.pacotes = dados.pacotes || [];
      // Mapeia estados de instalação
      for (const pkg of this.pacotes) {
        this.estados[pkg.id] = {
          instalado: !!dados.instalados?.[pkg.id],
          ativo: !!dados.ativos?.[pkg.id],
          versao_instalada: dados.instalados?.[pkg.id]?.versao,
        };
      }
    } catch (exc) {
      this.deps.notificar(`Falha ao carregar pacotes: ${exc instanceof Error ? exc.message : "erro"}`, true);
      this.pacotes = [];
    }
  }

  private renderizar(): void {
    if (this.pacotes.length === 0) {
      this.raiz.innerHTML = `<p class="nota">Nenhum pacote disponível ou falha ao carregar.</p>`;
      return;
    }

    const linhas = this.pacotes.map((pkg) => {
      const est = this.estados[pkg.id] || { instalado: false, ativo: false };
      const indisp = pkg.indisponivel;
      const tamanho = formatarBytes(pkg.bytes_download);
      const botaoAcao = indisp
        ? `<button disabled title="${esc(pkg.motivo_indisponivel || "indisponível")}">Indisponível</button>`
        : est.instalado
          ? `<button data-acao="remover" data-pkg="${esc(pkg.id)}">Remover</button>`
          : `<button data-acao="instalar" data-pkg="${esc(pkg.id)}">Instalar</button>`;

      const statusTexto = est.instalado
        ? `<span class="status-instalado">✓ Instalado${est.ativo ? " (ativo)" : ""}</span>`
        : indisp
          ? `<span class="status-indisponivel">✗ ${esc(pkg.motivo_indisponivel || "indisponível")}</span>`
          : `<span class="status-nao-instalado">Não instalado</span>`;

      return `
        <div class="pacote-linha" id="pkg-${esc(pkg.id)}">
          <div class="pacote-info">
            <strong>${esc(pkg.nome)}</strong> <small>v${esc(pkg.versao)}</small>
            <p class="descricao">${esc(pkg.descricao)}</p>
            <p class="meta">Tamanho: ${tamanho} · Licença: <a href="${esc(pkg.licenca_url)}" target="_blank" rel="noopener">${esc(pkg.licenca_nome || "Ver")}</a></p>
            <p class="status">${statusTexto}</p>
          </div>
          <div class="pacote-acoes">
            ${botaoAcao}
            <div class="progresso-container" id="prog-${esc(pkg.id)}" style="display:none;">
              <progress max="100" value="0"></progress>
              <span class="progresso-texto">0%</span>
              <button data-acao="cancelar" data-pkg="${esc(pkg.id)}" class="btn-cancelar">Cancelar</button>
            </div>
          </div>
        </div>
      `;
    });

    this.raiz.innerHTML = `
      <fieldset>
        <legend>Pacotes de Voz Opcionais</legend>
        <p class="nota">Instale motores e vozes adicionais. A licença será exibida antes do download.</p>
        <div class="pacotes-lista">${linhas.join("")}</div>
      </fieldset>
    `;

    this.vincularEventos();
  }

  private vincularEventos(): void {
    this.raiz.addEventListener("click", (ev) => {
      const alvo = ev.target as HTMLElement;
      const acao = alvo.dataset.acao;
      const pkgId = alvo.dataset.pkg;
      if (!acao || !pkgId) return;

      if (acao === "instalar") this.iniciarInstalacao(pkgId);
      else if (acao === "cancelar") this.cancelarInstalacao(pkgId);
      else if (acao === "remover") this.removerPacote(pkgId);
    });
  }

  private async iniciarInstalacao(pkgId: string): Promise<void> {
    const pkg = this.pacotes.find((p) => p.id === pkgId);
    if (!pkg) return;

    // Confirmação de licença
    if (pkg.licenca_url) {
      const aceito = window.confirm(
        `Este pacote está sob a licença "${pkg.licenca_nome || "Desconhecida"}".\n\n` +
        `Leia os termos em:\n${pkg.licenca_url}\n\n` +
        `Deseja continuar com a instalação?`
      );
      if (!aceito) return;
    }

    // UI: mostrar progresso
    const progContainer = this.raiz.querySelector(`#prog-${pkgId}`) as HTMLElement;
    const progBar = progContainer?.querySelector("progress") as HTMLProgressElement;
    const progTexto = progContainer?.querySelector(".progresso-texto") as HTMLElement;
    const btnInstalar = this.raiz.querySelector(`button[data-acao="instalar"][data-pkg="${pkgId}"]`) as HTMLButtonElement;
    if (progContainer) progContainer.style.display = "";
    if (btnInstalar) btnInstalar.disabled = true;

    const ctrl = new AbortController();
    this.abortControllers[pkgId] = ctrl;

    try {
      const resp = await fetch(`${this.deps.baseUrl}/pacotes/${encodeURIComponent(pkgId)}/instalar`, {
        method: "POST",
        signal: ctrl.signal,
      });

      if (!resp.ok && !resp.body) {
        const err = await resp.json().catch(() => ({ erro: `HTTP ${resp.status}` }));
        this.deps.notificar(`Falha ao iniciar: ${err.erro || resp.status}`, true);
        return;
      }

      // Ler SSE
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const linhas = buffer.split("\n");
        buffer = linhas.pop() || "";

        for (const linha of linhas) {
          if (!linha.startsWith("data: ")) continue;
          try {
            const dados: ProgressoInstalacao = JSON.parse(linha.slice(6));
            this.atualizarProgresso(pkgId, dados, progBar, progTexto);
            if (dados.estado === "concluido") {
              this.deps.notificar(`${pkg.nome} instalado com sucesso.`);
              this.estados[pkgId] = { ...this.estados[pkgId], instalado: true, versao_instalada: pkg.versao };
              this.renderizar();
              return;
            }
            if (dados.estado === "falhou") {
              this.deps.notificar(`Falha na instalação: ${dados.erro || "desconhecido"}`, true);
              this.renderizar();
              return;
            }
            if (dados.estado === "cancelado") {
              this.deps.notificar("Instalação cancelada.");
              this.renderizar();
              return;
            }
          } catch { /* ignora linha malformada */ }
        }
      }
    } catch (exc) {
      if ((exc as Error).name !== "AbortError") {
        this.deps.notificar(`Erro de conexão: ${(exc as Error).message}`, true);
      }
    } finally {
      delete this.abortControllers[pkgId];
    }
  }

  private atualizarProgresso(
    _pkgId: string,
    dados: ProgressoInstalacao,
    bar: HTMLProgressElement | null,
    texto: HTMLElement | null,
  ): void {
    if (!bar || !texto) return;
    if (dados.bytes_total > 0) {
      const pct = Math.round((dados.bytes_baixados / dados.bytes_total) * 100);
      bar.value = pct;
      texto.textContent = `${pct}% (${formatarBytes(dados.bytes_baixados)})`;
    } else {
      texto.textContent = dados.estado;
    }
  }

  private async cancelarInstalacao(pkgId: string): Promise<void> {
    const ctrl = this.abortControllers[pkgId];
    if (ctrl) ctrl.abort();
    try {
      await fetch(`${this.deps.baseUrl}/pacotes/${encodeURIComponent(pkgId)}/cancelar`, { method: "POST" });
    } catch { /* melhor esforço */ }
  }

  private async removerPacote(pkgId: string): Promise<void> {
    const pkg = this.pacotes.find((p) => p.id === pkgId);
    if (!pkg) return;
    const confirmar = window.confirm(`Remover ${pkg.nome}? Arquivos pessoais serão preservados.`);
    if (!confirmar) return;

    try {
      const resp = await fetch(`${this.deps.baseUrl}/pacotes/${encodeURIComponent(pkgId)}/remover`, { method: "POST" });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ erro: `HTTP ${resp.status}` }));
        this.deps.notificar(`Falha ao remover: ${err.erro || resp.status}`, true);
        return;
      }
      this.deps.notificar(`${pkg.nome} removido.`);
      this.estados[pkgId] = { instalado: false, ativo: false };
      this.renderizar();
    } catch (exc) {
      this.deps.notificar(`Erro ao remover: ${(exc as Error).message}`, true);
    }
  }
}