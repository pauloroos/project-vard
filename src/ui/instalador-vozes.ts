/**
 * Tela do Instalador de Vozes (T5b).
 * Lista pacotes opcionais, mostra licença antes de instalar,
 * exibe progresso via SSE e permite cancelar/remover.
 */
import { abrirModal } from "./componentes";

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
  instalado?: boolean;
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
  aoMudar?: (id: string, instalado: boolean) => void | Promise<void>;
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
    this.vincularEventos();
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
          instalado: typeof pkg.instalado === "boolean" ? pkg.instalado : !!dados.instalados?.[pkg.id],
          ativo: !!dados.ativos?.[pkg.id],
          versao_instalada: dados.instalados?.[pkg.id]?.versao,
        };
      }
    } catch {
      // Falha silenciosa: a seção fica vazia sem poluir o status global.
      // Erros reais de instalação/remoção são notificados separadamente.
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

  }

  /** Entrada dos cards de motor: usa a mesma licença, progresso e cancelamento da lista.
   * Devolve true só quando o pacote terminou instalado; licença já aceita na pergunta não é repetida. */
  async instalar(pkgId: string, op: { licencaAceita?: boolean } = {}): Promise<boolean> {
    return this.iniciarInstalacao(pkgId, op.licencaAceita === true);
  }

  estaInstalado(pkgId: string): boolean { return this.estados[pkgId]?.instalado ?? false; }

  /** Dados do manifesto (nome, tamanho, licença) para a pergunta de instalar. */
  pacote(pkgId: string): PacoteManifesto | undefined { return this.pacotes.find((p) => p.id === pkgId); }

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

  private async iniciarInstalacao(pkgId: string, licencaAceita = false): Promise<boolean> {
    const pkg = this.pacotes.find((p) => p.id === pkgId);
    if (!pkg || pkg.indisponivel || this.abortControllers[pkgId]) return false;
    if (this.estados[pkgId]?.instalado) return true;

    // Confirmação de licença
    if (pkg.licenca_url && !licencaAceita) {
      const aceito = window.confirm(
        `Este pacote está sob a licença "${pkg.licenca_nome || "Desconhecida"}".\n\n` +
        `Leia os termos em:\n${pkg.licenca_url}\n\n` +
        `Deseja continuar com a instalação?`
      );
      if (!aceito) return false;
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
        return false;
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
              void this.deps.aoMudar?.(pkgId, true);
              return true;
            }
            if (dados.estado === "falhou") {
              this.deps.notificar(`Falha na instalação: ${dados.erro || "desconhecido"}`, true);
              this.renderizar();
              return false;
            }
            if (dados.estado === "cancelado") {
              this.deps.notificar("Instalação cancelada.");
              this.renderizar();
              return false;
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
    return false;
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
      void this.deps.aoMudar?.(pkgId, false);
    } catch (exc) {
      this.deps.notificar(`Erro ao remover: ${(exc as Error).message}`, true);
    }
  }
}

export interface PerguntaInstalacao {
  /** Nome do motor/voz como aparece no card. */
  nome: string;
  /** Do manifesto, quando o instalador já carregou a lista. */
  pacote?: Pick<PacoteManifesto, "nome" | "bytes_download" | "licenca_nome" | "licenca_url">;
  raiz?: HTMLElement;
}

/** Pergunta em modal se instala a voz que falta; mostra tamanho e licença do pacote. Resolve true para instalar. */
export function perguntarInstalacao(op: PerguntaInstalacao): Promise<boolean> {
  const corpo = document.createElement("div");
  corpo.className = "modal-instalar-voz";
  const texto = document.createElement("p");
  texto.textContent = `${op.nome} não está instalado neste PC. Quer instalar agora? Ao terminar, o Vard já deixa esta voz escolhida.`;
  corpo.append(texto);
  const pkg = op.pacote;
  if (pkg) {
    const meta = document.createElement("p");
    meta.className = "nota";
    meta.append(`${pkg.nome}${pkg.bytes_download > 0 ? ` · download de ${formatarBytes(pkg.bytes_download)}` : ""}`);
    if (pkg.licenca_url) {
      meta.append(" · Licença: ");
      const link = document.createElement("a");
      link.href = pkg.licenca_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = pkg.licenca_nome || "ver termos";
      meta.append(link, ". Instalar significa aceitar esses termos.");
    }
    corpo.append(meta);
  }
  return new Promise((resolver) => {
    let instalar = false;
    abrirModal({
      titulo: `Instalar ${op.nome}?`,
      corpo,
      acoes: [
        { rotulo: "Instalar e usar", primaria: true, aoClicar: () => { instalar = true; } },
        { rotulo: "Agora não" },
      ],
      aoFechar: () => resolver(instalar),
    }, op.raiz);
  });
}
