import type { ReuniaoDaLista, ResultadoReuniao, StatusReuniao } from "../conectores/ponte/cliente";

/** O que a aba usa da ponte da reunião (injetável nos testes). */
export interface PonteReuniao {
  reuniaoStatus(): Promise<StatusReuniao | null>;
  iniciarReuniao(): Promise<ResultadoReuniao | null>;
  encerrarReuniao(): Promise<ResultadoReuniao | null>;
  listaReuniao(n?: number): Promise<ReuniaoDaLista[] | null>;
  gerarAta(tipo: "ata" | "relatorio", qual?: string): Promise<ResultadoReuniao | null>;
}

/** Dependências para a seção de instalação/remoção do pacote de reunião. */
export interface DepsPacoteReuniao {
  /** Base URL do núcleo (ex: http://127.0.0.1:4700) */
  baseUrl: string;
  /** Callback para notificações de status ao usuário */
  notificar: (msg: string, erro?: boolean) => void;
}

export interface EstadoPacoteReuniao {
  instalado: boolean;
  saudavel: boolean;
  versao_instalada?: string;
}

export interface ProgressoInstalacaoReuniao {
  estado: "aguardando" | "instalando" | "concluido" | "falhou" | "cancelado";
  erro?: string | null;
}

/** O que cada botão da aba pode fazer. null = ponte fora: nada. */
export function acoesDaReuniao(ativa: boolean | null): { iniciar: boolean; encerrar: boolean; ata: boolean; relatorio: boolean } {
  if (ativa === null) return { iniciar: false, encerrar: false, ata: false, relatorio: false };
  return { iniciar: !ativa, encerrar: ativa, ata: true, relatorio: true };
}

/** Duração em segundos vira "1 h 05 min" (ou "25 min" / "40 s" quando cabe). */
export function formatarDuracao(segundos: number): string {
  const s = Number.isFinite(segundos) ? Math.max(0, Math.round(segundos)) : 0;
  const h = Math.floor(s / 3600);
  const min = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} h ${String(min).padStart(2, "0")} min`;
  if (min > 0) return `${min} min`;
  return `${s} s`;
}

/** Data/hora da ponte vira "13/10/2026 15:00"; texto que não é data fica como está. */
export function formatarDataHora(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

type Chave = "iniciar" | "encerrar" | "ata" | "relatorio";

const TEXTO = "A reunião pertence ao serviço da ponte: quem ouve \"encerra a reunião\" é ele, não o widget. Aqui dá para ver se há uma em andamento, começar ou encerrar pela ponte e gerar a ata ou o relatório da última. Enquanto a reunião corre, o widget fica mudo e não escuta o gatilho.";
const BOTOES: [Chave, string][] = [["iniciar", "Iniciar"], ["encerrar", "Encerrar"], ["ata", "Gerar ata"], ["relatorio", "Gerar relatório"]];

/** Aba Reunião: estado da ponte da reunião a cada 5 s enquanto aberta, os dois verbos e a última reunião. */
export class AbaReuniao {
  private relogio = 0;
  private botoes = new Map<string, HTMLButtonElement>();
  private estado!: HTMLElement;
  private msg!: HTMLElement;
  private ultima!: HTMLElement;
  private acoes = acoesDaReuniao(null);
  private ativa = false;

  // Seção de instalação/remoção do pacote
  private depsPacote?: DepsPacoteReuniao;
  private estadoPacote: EstadoPacoteReuniao = { instalado: false, saudavel: false };
  private abortCtrl?: AbortController;
  private secaoPacote!: HTMLElement;

  constructor(private raiz: HTMLElement, private deps: PonteReuniao, depsPacote?: DepsPacoteReuniao) {
    this.depsPacote = depsPacote;
  }

  montar() {
    const p = document.createElement("p"); p.className = "nota"; p.textContent = TEXTO;
    this.estado = document.createElement("div"); this.estado.id = "reu-estado"; this.estado.textContent = "Consultando a ponte...";
    const caixa = document.createElement("div"); caixa.className = "acoes";
    for (const [chave, rotulo] of BOTOES) {
      const b = document.createElement("button"); b.type = "button"; b.textContent = rotulo;
      b.addEventListener("click", () => { void this.clicar(chave); });
      this.botoes.set(chave, b); caixa.append(b);
    }
    this.msg = document.createElement("div"); this.msg.id = "reu-msg";
    this.ultima = document.createElement("div"); this.ultima.id = "reu-ultima";

    // Seção de pacote de reunião
    this.secaoPacote = document.createElement("div"); this.secaoPacote.id = "reu-pacote";
    this.raiz.append(this.secaoPacote, p, this.estado, caixa, this.msg, this.ultima);
    this.rotular();
    void this.carregarPacote();
  }

  ativar() { this.ativa = true; void this.puxar(true); clearInterval(this.relogio); this.relogio = window.setInterval(() => { void this.puxar(true); }, 5000); }
  desativar() { this.ativa = false; clearInterval(this.relogio); this.relogio = 0; }

  /** Recarrega pela ponte e pinta (também chamado depois de cada ação e nos testes). */
  async carregar() { await this.puxar(false); }

  /** `comGuarda`: a carga do relógio não pode repintar uma aba que já fechou no meio da espera da ponte. */
  private async puxar(comGuarda: boolean) {
    const [st, lista] = await Promise.all([this.deps.reuniaoStatus(), this.deps.listaReuniao(1)]);
    if (comGuarda && !this.ativa) return;
    this.acoes = acoesDaReuniao(st === null ? null : st.ativa);
    this.estado.textContent = st
      ? (st.ativa ? `Reunião em andamento${st.pasta ? ` (${st.pasta})` : ""}.` : "Nenhuma reunião em andamento.")
      : "Ponte fora do ar ou desligada.";
    this.desenharUltima(lista?.[0] ?? null);
    this.rotular();
  }

  private rotular() {
    for (const [chave] of BOTOES) this.botoes.get(chave)!.disabled = !this.acoes[chave];
  }

  private async clicar(chave: Chave) {
    this.msg.textContent = "Enviando...";
    const r = chave === "iniciar" ? await this.deps.iniciarReuniao()
      : chave === "encerrar" ? await this.deps.encerrarReuniao()
      : await this.deps.gerarAta(chave === "ata" ? "ata" : "relatorio", "ultima");
    this.msg.textContent = r ? r.frase : "A ponte não respondeu.";
    void this.carregar();
  }

  private desenharUltima(r: ReuniaoDaLista | null) {
    this.ultima.innerHTML = "";
    const titulo = document.createElement("h3"); titulo.textContent = "Última reunião";
    this.ultima.append(titulo);
    if (!r) { const vazio = document.createElement("div"); vazio.className = "nota"; vazio.textContent = "Nenhuma reunião registrada."; this.ultima.append(vazio); return; }
    const linhas: [string, string][] = [
      ["Data/hora", r.inicio ? formatarDataHora(r.inicio) : "—"],
      ["Duração", formatarDuracao(r.duracao_s)],
      ["Ata", r.ata ? "pronta" : "não gerada"],
      ["Relatório", r.relatorio ? "pronto" : "não gerado"],
    ];
    for (const [rotulo, valor] of linhas) {
      const linha = document.createElement("div"); linha.className = "linha"; linha.textContent = `${rotulo}: ${valor}`;
      this.ultima.append(linha);
    }
  }

  // ---------------------------------------------------------------------------
  // Seção de instalação/remoção do pacote de reunião
  // ---------------------------------------------------------------------------

  private async carregarPacote(): Promise<void> {
    if (!this.depsPacote) { this.renderizarPacote(); return; }
    try {
      const resp = await fetch(`${this.depsPacote.baseUrl}/pacotes`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const dados = await resp.json() as { pacotes?: Array<{ id: string; versao: string }>; instalados?: Record<string, { versao?: string; saudavel?: boolean }> };
      const pkg = dados.pacotes?.find((p) => p.id === "reuniao");
      const inst = dados.instalados?.["reuniao"];
      this.estadoPacote = {
        instalado: !!inst,
        saudavel: !!inst?.saudavel,
        versao_instalada: inst?.versao,
      };
      void pkg; // manifesto disponível se necessário
    } catch {
      this.estadoPacote = { instalado: false, saudavel: false };
    }
    this.renderizarPacote();
  }

  private renderizarPacote(): void {
    this.secaoPacote.innerHTML = "";
    const fs = document.createElement("fieldset");
    const leg = document.createElement("legend"); leg.textContent = "Pacote de Reunião";
    fs.append(leg);

    if (!this.depsPacote) {
      const nota = document.createElement("p"); nota.className = "nota"; nota.textContent = "Instalação indisponível nesta sessão.";
      fs.append(nota);
      this.secaoPacote.append(fs);
      return;
    }

    const info = document.createElement("div"); info.className = "pacote-info";
    const nome = document.createElement("strong"); nome.textContent = "Reunião (transcrição e diarização)";
    const ver = document.createElement("small"); ver.textContent = ` v${this.estadoPacote.versao_instalada || "0.1.0"}`;
    info.append(nome, ver);

    const desc = document.createElement("p"); desc.className = "descricao";
    desc.textContent = "Serviço de reunião com transcrição, VAD e diarização. Requer Python 3.12 e ~500 MB.";
    info.append(desc);

    const statusEl = document.createElement("p"); statusEl.className = "status";
    if (this.estadoPacote.instalado) {
      statusEl.innerHTML = `<span class="status-instalado">✓ Instalado${this.estadoPacote.saudavel ? " (saudável)" : " (não saudável)"}</span>`;
    } else {
      statusEl.innerHTML = `<span class="status-nao-instalado">Não instalado</span>`;
    }
    info.append(statusEl);
    fs.append(info);

    const acoesDiv = document.createElement("div"); acoesDiv.className = "pacote-acoes";

    if (this.estadoPacote.instalado) {
      const btnRemover = document.createElement("button"); btnRemover.type = "button";
      btnRemover.textContent = "Remover"; btnRemover.dataset.acao = "remover";
      // Só habilita remoção se o pacote estiver saudável (serviço responde)
      btnRemover.disabled = !this.estadoPacote.saudavel;
      btnRemover.addEventListener("click", () => { void this.removerPacote(); });
      acoesDiv.append(btnRemover);
    } else {
      const btnInstalar = document.createElement("button"); btnInstalar.type = "button";
      btnInstalar.textContent = "Instalar reunião"; btnInstalar.dataset.acao = "instalar";
      btnInstalar.addEventListener("click", () => { void this.instalarPacote(); });
      acoesDiv.append(btnInstalar);
    }

    // Container de progresso
    const progContainer = document.createElement("div"); progContainer.className = "progresso-container"; progContainer.id = "prog-reuniao"; progContainer.style.display = "none";
    const progBar = document.createElement("progress"); progBar.max = 100; progBar.value = 0;
    const progTexto = document.createElement("span"); progTexto.className = "progresso-texto"; progTexto.textContent = "0%";
    const btnCancel = document.createElement("button"); btnCancel.type = "button"; btnCancel.className = "btn-cancelar"; btnCancel.textContent = "Cancelar";
    btnCancel.addEventListener("click", () => { void this.cancelarInstalacao(); });
    progContainer.append(progBar, progTexto, btnCancel);
    acoesDiv.append(progContainer);

    fs.append(acoesDiv);
    this.secaoPacote.append(fs);
  }

  private async instalarPacote(): Promise<void> {
    if (!this.depsPacote) return;
    const progContainer = this.secaoPacote.querySelector("#prog-reuniao") as HTMLElement | null;
    const progBar = progContainer?.querySelector("progress") as HTMLProgressElement | null;
    const progTexto = progContainer?.querySelector(".progresso-texto") as HTMLElement | null;
    const btnInstalar = this.secaoPacote.querySelector('button[data-acao="instalar"]') as HTMLButtonElement | null;
    if (progContainer) progContainer.style.display = "";
    if (btnInstalar) btnInstalar.disabled = true;

    this.abortCtrl = new AbortController();
    try {
      const resp = await fetch(`${this.depsPacote.baseUrl}/pacotes/reuniao/instalar`, {
        method: "POST",
        signal: this.abortCtrl.signal,
      });
      if (!resp.ok && !resp.body) {
        const err = await resp.json().catch(() => ({ erro: `HTTP ${resp.status}` })) as { erro?: string };
        this.depsPacote.notificar(`Falha ao iniciar: ${err.erro || resp.status}`, true);
        this.renderizarPacote();
        return;
      }
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
            const dados: ProgressoInstalacaoReuniao = JSON.parse(linha.slice(6)) as ProgressoInstalacaoReuniao;
            this.atualizarProgresso(dados, progBar, progTexto);
            if (dados.estado === "concluido") {
              this.depsPacote.notificar("Reunião instalada com sucesso.");
              this.estadoPacote = { ...this.estadoPacote, instalado: true, saudavel: true };
              this.renderizarPacote();
              return;
            }
            if (dados.estado === "falhou") {
              this.depsPacote.notificar(`Falha na instalação: ${dados.erro || "desconhecido"}`, true);
              this.renderizarPacote();
              return;
            }
            if (dados.estado === "cancelado") {
              this.depsPacote.notificar("Instalação cancelada.");
              this.renderizarPacote();
              return;
            }
          } catch { /* ignora linha malformada */ }
        }
      }
    } catch (exc) {
      if ((exc as Error).name !== "AbortError") {
        this.depsPacote.notificar(`Erro de conexão: ${(exc as Error).message}`, true);
      }
    } finally {
      this.abortCtrl = undefined;
    }
  }

  private atualizarProgresso(
    dados: ProgressoInstalacaoReuniao,
    bar: HTMLProgressElement | null,
    texto: HTMLElement | null,
  ): void {
    if (!texto) return;
    if (bar) {
      // Instalação local não tem bytes; mostra estado textual
      if (dados.estado === "instalando") {
        bar.value = 50;
        texto.textContent = "Instalando...";
      } else if (dados.estado === "concluido") {
        bar.value = 100;
        texto.textContent = "Concluído";
      } else {
        texto.textContent = dados.estado;
      }
    } else {
      texto.textContent = dados.estado;
    }
  }

  private async cancelarInstalacao(): Promise<void> {
    if (this.abortCtrl) this.abortCtrl.abort();
    if (!this.depsPacote) return;
    try {
      await fetch(`${this.depsPacote.baseUrl}/pacotes/reuniao/cancelar`, { method: "POST" });
    } catch { /* melhor esforço */ }
  }

  private async removerPacote(): Promise<void> {
    if (!this.depsPacote) return;
    // Confirmação simples via confirm do DOM (mockável nos testes)
    const confirmar = typeof window !== "undefined" && typeof window.confirm === "function"
      ? window.confirm("Remover o pacote de reunião? Atas e gravações serão preservadas.")
      : true;
    if (!confirmar) return;

    try {
      const resp = await fetch(`${this.depsPacote.baseUrl}/pacotes/reuniao/remover`, { method: "POST" });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ erro: `HTTP ${resp.status}` })) as { erro?: string };
        this.depsPacote.notificar(`Falha ao remover: ${err.erro || resp.status}`, true);
        return;
      }
      this.depsPacote.notificar("Pacote de reunião removido.");
      this.estadoPacote = { instalado: false, saudavel: false };
      this.renderizarPacote();
    } catch (exc) {
      this.depsPacote.notificar(`Erro ao remover: ${(exc as Error).message}`, true);
    }
  }
}