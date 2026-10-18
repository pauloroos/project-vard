/**
 * Seção "Ferramentas (MCP)" das Configurações (0.9.3, U6 e U8).
 *
 * Os servidores MCP dão ferramentas ao Vard; aqui eles aparecem em cards (nome, stdio/http,
 * habilitado e, quando existe, o resultado do teste de credencial), com adicionar/editar em
 * modal. A credencial nunca aparece na tela: fica no cofre e o cadastro guarda só a
 * referência tipo:id; o "Testar" confere a existência sem expor valor.
 *
 * Com a ponte/núcleo fora, um aviso claro no topo diz que os serviços estão desligados (U8):
 * sem eles os MCPs ficam cadastrados, mas não são usados de verdade.
 */
import "./estilos/mcp.css";
import { cofreExiste } from "../config/segredos";
import type { Mcp, PaineisConfig } from "../config/paineis";
import { gravarPaineis, lerPaineis } from "../config/paineis";
import { Ponte } from "../conectores/ponte/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import { abrirModal, campoModal, desenharCards } from "./componentes";
import type { Card, ModalAberto, TomSelo } from "./componentes";

/** Aviso do topo quando a ponte/núcleo não responde (U8). */
export const AVISO_SERVICOS_DESLIGADOS =
  "Os serviços do Vard estão desligados — abra pelo atalho do Vard ou ligue em Sistema.";

/** Texto do card quando a lista não tem nenhum servidor. */
export const VAZIO_LISTA = "Nenhum servidor MCP cadastrado.";

/**
 * Modelo pronto do Windows-MCP (CursorTouch, MIT): comando recomendado pelo projeto,
 * `uvx windows-mcp serve` (README do repositório e PyPI `windows-mcp`). Ver docs/windows-mcp.md.
 */
export const MODELO_WINDOWS_MCP = {
  id: "windows-mcp",
  nome: "Windows-MCP (controle do computador)",
  command: "uvx",
  args: ["windows-mcp", "serve"],
} as const;

/** Aviso mostrado no cadastro pelo modelo pronto. */
export const AVISO_WINDOWS_MCP =
  "Projeto de terceiros (Windows-MCP, licença MIT). Habilitado, permite ao assistente clicar e digitar " +
  "no computador, abrir janelas e ler a tela. Precisa do uv instalado; o Vard não instala nada. " +
  "Fica desabilitado até você habilitar no card.";

/** Cadastro pré-preenchido vindo de um modelo pronto. */
interface ModeloMcp {
  id: string;
  nome: string;
  command: string;
  args: readonly string[];
  aviso: string;
}

type TipoMcp = "stdio" | "http";
type EstadoCredencial = "ok" | "ausente";

export interface DepsMcps {
  /** Notifica quando a config mudou para que o painel possa reagir. */
  aoMudar?: () => void;
  /** Status da ponte (null = fora do ar). Sem isto, a seção sonda o endereço da aba Sistema. */
  statusPonte?: () => Promise<StatusPonte | null>;
}

export class AbaPaineisMcps {
  private cfg!: PaineisConfig;
  private lista!: HTMLElement;
  private aviso!: HTMLElement;
  private recado!: HTMLElement;
  private modal: ModalAberto | null = null;
  /** Resultado do último "Testar" por servidor (fica só nesta sessão da tela). */
  private testeCredencial = new Map<string, EstadoCredencial>();

  constructor(
    private raiz: HTMLElement,
    private deps: DepsMcps = {},
  ) {}

  async montar() {
    this.cfg = await lerPaineis();
    this.montarEstrutura();
    this.desenhar();
    void this.atualizarAvisoServicos();
  }

  private montarEstrutura() {
    this.raiz.innerHTML = "";

    this.aviso = document.createElement("div");
    this.aviso.id = "mcp-aviso-servicos";
    this.aviso.className = "mcp-aviso";
    this.aviso.setAttribute("role", "alert");
    this.aviso.textContent = AVISO_SERVICOS_DESLIGADOS;
    this.aviso.hidden = true;

    const titulo = document.createElement("div");
    titulo.className = "mcp-titulo";
    const h2 = document.createElement("h2");
    h2.textContent = "Ferramentas (MCP)";
    const explicacao = document.createElement("p");
    explicacao.textContent = "Servidores MCP dão ferramentas ao Vard, como arquivos, banco de dados e a web.";
    titulo.append(h2, explicacao);

    const modelos = document.createElement("div");
    modelos.className = "mcp-modelos";
    const botaoWindows = document.createElement("button");
    botaoWindows.type = "button";
    botaoWindows.id = "mcp-modelo-windows-mcp";
    botaoWindows.textContent = "Adicionar Windows-MCP (controle do computador)";
    botaoWindows.addEventListener("click", () => this.abrirModelo({ ...MODELO_WINDOWS_MCP, aviso: AVISO_WINDOWS_MCP }));
    modelos.append(botaoWindows);

    this.lista = document.createElement("div");
    this.lista.id = "mcp-lista";

    this.recado = document.createElement("div");
    this.recado.id = "msg-mcps";
    this.recado.setAttribute("role", "status");

    this.raiz.append(this.aviso, titulo, modelos, this.lista, this.recado);
  }

  private desenhar() {
    const cards: Card[] = this.cfg.mcps.map((m) => this.cardDe(m));
    desenharCards(this.lista, cards, {
      vazio: VAZIO_LISTA,
      adicionar: { rotulo: "Adicionar servidor", aoClicar: () => this.abrirModal() },
    });
  }

  private cardDe(m: Mcp): Card {
    const selos: { texto: string; tom: TomSelo }[] = [
      m.habilitado ? { texto: "Habilitado", tom: "ok" } : { texto: "Desabilitado", tom: "neutro" },
    ];
    const teste = this.testeCredencial.get(m.id);
    if (teste) selos.push({ texto: teste === "ok" ? "credencial ok" : "credencial ausente", tom: teste === "ok" ? "ok" : "aviso" });

    const detalhes: string[] = [];
    if (m.command) detalhes.push(`comando: ${m.command}${m.args?.length ? ` ${m.args.join(" ")}` : ""}`);
    if (m.url) detalhes.push(`url: ${m.url}`);
    if (m.credencial_ref) detalhes.push(`credencial: ${m.credencial_ref}`);

    return {
      id: m.id,
      titulo: m.nome,
      etiqueta: m.command ? "stdio" : "http",
      selos,
      detalhes,
      busca: m.id,
      acoes: [
        { rotulo: m.habilitado ? "Desabilitar" : "Habilitar", aoClicar: () => void this.alternar(m.id) },
        ...(m.credencial_ref ? [{ rotulo: "Testar", aoClicar: () => void this.testarCredencial(m.id) }] : []),
        { rotulo: "Editar", aoClicar: () => this.abrirModal(m.id) },
        { rotulo: "Remover", perigo: true, aoClicar: () => void this.remover(m.id) },
      ],
    };
  }

  /** Modelo pronto: se já existe um cadastro com o mesmo id, abre a edição dele; senão, o cadastro pré-preenchido. */
  private abrirModelo(modelo: ModeloMcp) {
    if (this.cfg.mcps.some((m) => m.id === modelo.id)) this.abrirModal(modelo.id);
    else this.abrirModal(undefined, modelo);
  }

  /** Abre o modal de adicionar (sem id), de adicionar por modelo pronto ou de editar (com o id de um existente). */
  private abrirModal(id?: string, modelo?: ModeloMcp) {
    this.modal?.fechar(); // nunca dois modais um em cima do outro
    const atual = id ? this.cfg.mcps.find((m) => m.id === id) : undefined;
    const inicial = atual ?? (modelo ? { id: modelo.id, nome: modelo.nome, command: modelo.command, args: [...modelo.args] } : undefined);

    const campoId = document.createElement("input");
    campoId.id = "mcp-id";
    campoId.type = "text";
    if (atual) { campoId.value = atual.id; campoId.readOnly = true; }
    else if (modelo) campoId.value = modelo.id;

    const campoNome = document.createElement("input");
    campoNome.id = "mcp-nome";
    campoNome.type = "text";
    campoNome.value = inicial?.nome ?? "";

    const tipoInicial: TipoMcp = inicial ? (inicial.command ? "stdio" : "http") : "stdio";
    const campoTipo = document.createElement("select");
    campoTipo.id = "mcp-tipo";
    for (const [valor, rotulo] of [["stdio", "stdio (comando local)"], ["http", "http (servidor remoto)"]] as const) {
      const opcao = document.createElement("option");
      opcao.value = valor;
      opcao.textContent = rotulo;
      campoTipo.append(opcao);
    }
    campoTipo.value = tipoInicial;

    const campoCommand = document.createElement("input");
    campoCommand.id = "mcp-command";
    campoCommand.type = "text";
    campoCommand.value = inicial?.command ?? "";

    const campoArgs = document.createElement("input");
    campoArgs.id = "mcp-args";
    campoArgs.type = "text";
    campoArgs.value = inicial?.args?.join(" ") ?? "";

    const campoUrl = document.createElement("input");
    campoUrl.id = "mcp-url";
    campoUrl.type = "text";
    campoUrl.value = atual?.url ?? "";

    const campoCred = document.createElement("input");
    campoCred.id = "mcp-cred";
    campoCred.type = "text";
    campoCred.value = atual?.credencial_ref ?? "";

    const grupoStdio = document.createElement("div");
    grupoStdio.id = "mcp-grupo-stdio";
    grupoStdio.append(
      campoModal("Comando", campoCommand, "O programa que roda o servidor, sozinho, sem shell."),
      campoModal("Argumentos (um por vez, separados por espaço)", campoArgs, "Cada argumento vai direto ao programa; nada de aspas nem comandos encadeados."),
    );

    const grupoHttp = document.createElement("div");
    grupoHttp.id = "mcp-grupo-http";
    grupoHttp.append(
      campoModal("URL", campoUrl, "Endereço do servidor MCP no formato http."),
      campoModal("Referência da credencial (opcional)", campoCred, "Formato tipo:id, como mcp:github. O valor fica no cofre e nunca aparece aqui."),
    );

    const corpo = document.createElement("div");
    if (modelo) {
      const aviso = document.createElement("p");
      aviso.id = "mcp-aviso-modelo";
      aviso.className = "mcp-aviso";
      aviso.textContent = modelo.aviso;
      corpo.append(aviso);
    }
    corpo.append(
      campoModal("Identificador", campoId, atual ? "O identificador não muda depois de criado." : "Único na lista; use letras, números, ponto ou hífen."),
      campoModal("Nome", campoNome),
      campoModal("Tipo", campoTipo),
      grupoStdio,
      grupoHttp,
    );
    grupoStdio.hidden = tipoInicial !== "stdio";
    grupoHttp.hidden = tipoInicial !== "http";
    campoTipo.addEventListener("change", () => {
      grupoStdio.hidden = campoTipo.value !== "stdio";
      grupoHttp.hidden = campoTipo.value !== "http";
    });

    let modal: ModalAberto;
    modal = abrirModal({
      titulo: atual ? "Editar servidor MCP" : modelo ? `Adicionar ${modelo.nome}` : "Adicionar servidor MCP",
      corpo,
      acoes: [
        {
          rotulo: "Salvar",
          primaria: true,
          aoClicar: () => this.salvar(modal, {
            id: campoId.value.trim(),
            nome: campoNome.value.trim(),
            tipo: campoTipo.value === "http" ? "http" : "stdio",
            command: campoCommand.value.trim(),
            args: campoArgs.value.trim(),
            url: campoUrl.value.trim(),
            credencial: campoCred.value.trim(),
          }, atual?.id, !modelo),
        },
        { rotulo: "Cancelar" },
      ],
      aoFechar: () => { this.modal = null; },
    });
    this.modal = modal;
  }

  private async salvar(
    modal: ModalAberto,
    v: { id: string; nome: string; tipo: TipoMcp; command: string; args: string; url: string; credencial: string },
    editando?: string,
    habilitadoNovo = true,
  ): Promise<boolean> {
    if (!v.id || !v.nome) { modal.avisar("Preencha o identificador e o nome.", true); return false; }
    if (!editando && this.cfg.mcps.some((m) => m.id === v.id)) {
      modal.avisar(`Já existe um servidor com o identificador "${v.id}".`, true);
      return false;
    }
    if (v.tipo === "stdio" && !v.command) { modal.avisar("stdio exige o campo Comando.", true); return false; }
    if (v.tipo === "http" && !v.url) { modal.avisar("http exige o campo URL.", true); return false; }
    if (v.credencial && !/^[\w.-]+:[\w.-]+$/.test(v.credencial)) {
      modal.avisar("A referência da credencial precisa estar no formato tipo:id.", true);
      return false;
    }

    const anterior = editando ? this.cfg.mcps.find((m) => m.id === editando) : undefined;
    const novo: Mcp = {
      id: v.id,
      nome: v.nome,
      habilitado: anterior?.habilitado ?? habilitadoNovo,
      ...(v.tipo === "stdio"
        ? { command: v.command, args: v.args ? v.args.split(/\s+/) : undefined }
        : { url: v.url }),
      credencial_ref: v.credencial || undefined,
    };
    if (editando) {
      const idx = this.cfg.mcps.findIndex((m) => m.id === editando);
      this.cfg.mcps[idx] = novo;
    } else {
      this.cfg.mcps.push(novo);
    }
    // Cadastro mudou: o teste anterior da credencial não vale mais.
    this.testeCredencial.delete(v.id);

    try {
      await gravarPaineis(this.cfg);
    } catch (e) {
      this.msg(`Não consegui salvar: ${e instanceof Error ? e.message : String(e)}`, true);
      return false;
    }
    this.deps.aoMudar?.();
    this.desenhar();
    this.msg(anterior || novo.habilitado ? "Salvo." : `Salvo desabilitado. Use Habilitar no card de ${novo.nome} quando quiser.`);
    return true;
  }

  private async alternar(id: string) {
    const m = this.cfg.mcps.find((x) => x.id === id);
    if (!m) return;
    m.habilitado = !m.habilitado;
    await this.persistir(m.habilitado ? `${m.nome} habilitado.` : `${m.nome} desabilitado.`);
  }

  private async remover(id: string) {
    const m = this.cfg.mcps.find((x) => x.id === id);
    if (!m) return;
    this.cfg.mcps = this.cfg.mcps.filter((x) => x.id !== id);
    this.testeCredencial.delete(id);
    await this.persistir(`${m.nome} removido.`);
  }

  private async persistir(recado: string) {
    try {
      await gravarPaineis(this.cfg);
    } catch (e) {
      this.msg(`Não consegui salvar: ${e instanceof Error ? e.message : String(e)}`, true);
      return;
    }
    this.deps.aoMudar?.();
    this.desenhar();
    this.msg(recado);
  }

  /** Confere se a credencial existe no cofre, sem expor o valor; o card ganha o selo do resultado. */
  private async testarCredencial(id: string) {
    const m = this.cfg.mcps.find((x) => x.id === id);
    if (!m?.credencial_ref) return;
    const [tipo, refId] = m.credencial_ref.split(":");
    const ok = await cofreExiste(tipo, refId);
    this.testeCredencial.set(id, ok ? "ok" : "ausente");
    this.desenhar();
    this.msg(
      ok ? `Credencial de ${m.nome} encontrada no cofre.` : `Credencial de ${m.nome} não está no cofre.`,
      !ok,
    );
  }

  /** U8: com a ponte/núcleo fora, o aviso claro fica no topo da seção. */
  private async atualizarAvisoServicos() {
    const fora = (await this.sondarPonte()) === null;
    this.aviso.hidden = !fora;
  }

  private async sondarPonte(): Promise<StatusPonte | null> {
    if (this.deps.statusPonte) return this.deps.statusPonte();
    // Sem injecção, o endereço é o da aba Sistema, que é o que vale na hora.
    const url = document.querySelector<HTMLInputElement>("#cfg-ponte_url")?.value.trim() ?? "";
    if (!url) return null;
    try {
      return await new Ponte(url).status();
    } catch {
      return null;
    }
  }

  private msg(texto: string, ruim = false) {
    this.recado.textContent = texto;
    this.recado.classList.toggle("ruim", ruim);
  }
}
