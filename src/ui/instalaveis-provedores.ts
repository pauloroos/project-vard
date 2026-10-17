/** Instalações de Quem responde: confirmação, progresso e cadastro pelo modal existente. */
import { abrirModal, desenharCards, type Card } from "./componentes";

export interface AndamentoInstalacao {
  id: string;
  estado: "aguardando" | "instalando" | "concluido" | "falhou" | "cancelado";
  linhas: string[];
}

export interface Instalavel extends AndamentoInstalacao {
  nome: string;
  descricao: string;
  comando: string[];
  fonte: string;
  tipo_provedor: string;
  url_base: string;
  tamanho_mb: number | null;
  manual: boolean;
  instalado: boolean;
  login: "dispensado" | "ausente" | "conectado" | "nao_verificado";
}

const ESTADOS: Record<AndamentoInstalacao["estado"], string> = {
  aguardando: "Aguardando", instalando: "Instalando", concluido: "Concluído", falhou: "Falhou", cancelado: "Cancelado",
};

export class InstalaveisProvedores {
  private itens: Instalavel[] = [];
  constructor(private raiz: HTMLElement, private base: string, private cadastrar: (item: Instalavel) => void | Promise<void>) {}

  private async requisitar(caminho: string, corpo?: object): Promise<unknown> {
    const resposta = await fetch(`${this.base.replace(/\/+$/, "")}/instalaveis${caminho}`, {
      ...(corpo ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) } : {}),
      signal: AbortSignal.timeout(10000),
    });
    if (!resposta.ok) throw new Error(resposta.status === 409
      ? "Já há uma instalação em andamento. Aguarde ou cancele antes de tentar outra."
      : "Não foi possível concluir o pedido. Confira se os serviços do Vard estão ligados.");
    return resposta.json();
  }

  async carregar(): Promise<void> {
    try {
      const corpo = await this.requisitar("") as { itens?: Instalavel[] };
      this.itens = Array.isArray(corpo.itens) ? corpo.itens : [];
      this.desenhar();
    } catch {
      this.raiz.textContent = "Instalações indisponíveis. Ligue os serviços do Vard e reabra esta aba.";
    }
  }

  private desenhar() {
    this.raiz.replaceChildren();
    const titulo = document.createElement("h3"); titulo.textContent = "Instalar ou conectar";
    const atualizar = document.createElement("button"); atualizar.type = "button"; atualizar.textContent = "Atualizar instalações";
    atualizar.addEventListener("click", () => { void this.carregar(); });
    const lista = document.createElement("div");
    this.raiz.append(titulo, atualizar, lista);
    const cards: Card[] = this.itens.map(item => {
      const acoes: Card["acoes"] = [];
      const emAndamento = item.estado === "instalando" || (item.estado === "aguardando" && item.linhas.length > 0);
      if (emAndamento) acoes.push({ rotulo: "Ver andamento", aoClicar: () => this.acompanhar(item) });
      else if (!item.instalado) acoes.push({
        rotulo: item.manual ? "Instruções de instalação" : "Instalar", primaria: !item.manual,
        aoClicar: () => this.confirmar(item),
      });
      if (item.instalado) {
        if (item.login !== "dispensado" && item.login !== "conectado") {
          acoes.push({ rotulo: "Entrar na conta", aoClicar: () => { void this.login(item); } });
        }
        if (item.tipo_provedor || item.id === "openjarvis") {
          acoes.push({ rotulo: "Cadastrar provedor", aoClicar: () => { void this.cadastrar(item); } });
        } else {
          acoes.push({ rotulo: "Instruções de conexão", aoClicar: () => this.confirmar(item, true) });
        }
      }
      const situacao = emAndamento ? "Instalando" : !item.instalado ? "Não instalado"
        : item.login === "ausente" ? "Falta entrar na conta"
        : item.login === "nao_verificado" ? "Instalado; confira o login" : "Instalado";
      return { id: `instalar-${item.id}`, titulo: item.nome, detalhes: [item.descricao],
        selos: [{ texto: situacao, tom: item.instalado && item.login !== "ausente" ? "ok" : "aviso" }], acoes };
    });
    desenharCards(lista, cards, { vazio: "Nenhuma instalação disponível." });
  }

  private confirmar(item: Instalavel, soInstrucoes = false) {
    const corpo = document.createElement("div");
    const texto = document.createElement("p"); texto.textContent = item.descricao;
    const tamanho = document.createElement("p"); tamanho.textContent = item.tamanho_mb == null
      ? "Tamanho não informado pelo fornecedor. Modelos são baixados separadamente."
      : `Tamanho aproximado: ${item.tamanho_mb} MB. Modelos são baixados separadamente.`;
    const comando = document.createElement("pre"); comando.textContent = item.comando.join(" ");
    const link = document.createElement("a");
    link.href = item.fonte.startsWith("https://") ? item.fonte : `https://github.com/pauloroos/project-vard/blob/main/${item.fonte}`;
    link.textContent = "Instruções oficiais"; link.target = "_blank"; link.rel = "noopener noreferrer";
    corpo.append(texto, tamanho, comando, link);
    if (item.id === "gemini") {
      const aviso = document.createElement("p");
      aviso.textContent = "O Vard ainda não tem um adaptador para Gemini CLI. Para responder pelo Vard, configure a API Google ou use Antigravity.";
      corpo.append(aviso);
    }
    const manual = item.manual || soInstrucoes;
    const modal = abrirModal({ titulo: manual ? `Instruções: ${item.nome}` : `Instalar ${item.nome}?`, corpo,
      acoes: manual ? [{ rotulo: "Fechar" }] : [
        { rotulo: "Cancelar", aoClicar: () => true },
        { rotulo: "Confirmar instalação", primaria: true, aoClicar: async () => {
          await this.requisitar(`/${encodeURIComponent(item.id)}/instalar`, { confirmado: true });
          modal.fechar(); this.acompanhar(item); return false;
        } },
      ],
    }, this.raiz);
  }

  private acompanhar(item: Instalavel) {
    const corpo = document.createElement("div");
    const status = document.createElement("p"); status.setAttribute("role", "status"); status.textContent = "Aguardando";
    const linhas = document.createElement("pre"); linhas.setAttribute("aria-live", "polite");
    corpo.append(status, linhas);
    let fechado = false;
    let relogio: ReturnType<typeof setTimeout> | undefined;
    const modal = abrirModal({ titulo: `Instalação: ${item.nome}`, corpo,
      aoFechar: () => { fechado = true; clearTimeout(relogio); },
      acoes: [
        { rotulo: "Cancelar instalação", aoClicar: async () => {
          await this.requisitar(`/${encodeURIComponent(item.id)}/cancelar`, {});
          modal.avisar("Cancelamento solicitado. Alterações já feitas podem permanecer."); return false;
        } },
        { rotulo: "Fechar", aoClicar: () => true },
      ],
    }, this.raiz);
    const consultar = async () => {
      if (fechado || !modal.elemento.isConnected) return;
      try {
        const atual = await this.requisitar(`/${encodeURIComponent(item.id)}/andamento`) as AndamentoInstalacao;
        if (fechado || !modal.elemento.isConnected) return;
        status.textContent = ESTADOS[atual.estado]; linhas.textContent = atual.linhas.join("\n");
        if (atual.estado === "concluido") {
          modal.fechar();
          await this.carregar();
          const detectado = this.itens.find(i => i.id === item.id) ?? item;
          if (item.tipo_provedor || item.id === "openjarvis") await this.cadastrar(detectado);
          else this.confirmar(detectado, true);
          return;
        }
        if (atual.estado === "falhou" || atual.estado === "cancelado") return;
        relogio = setTimeout(() => { void consultar(); }, 700);
      } catch (erro) {
        if (!fechado) modal.avisar(erro instanceof Error ? erro.message : "Consulta indisponível. Reabra o andamento para tentar novamente.", true);
      }
    };
    void consultar();
  }

  private async login(item: Instalavel) {
    const corpo = document.createElement("p"); corpo.textContent = "Abrindo terminal de login...";
    const modal = abrirModal({ titulo: `Entrar: ${item.nome}`, corpo }, this.raiz);
    try {
      await this.requisitar(`/${encodeURIComponent(item.id)}/login`, { confirmado: true });
      corpo.textContent = "Terminal aberto. Entre na sua conta nele e clique em Atualizar instalações ao voltar.";
    } catch (erro) {
      modal.avisar(erro instanceof Error ? erro.message : "Não foi possível abrir o terminal.", true);
    }
  }
}
