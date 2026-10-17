/**
 * Aba "Núcleo" (antes "Quem responde"; 0.9.3 U1–U4, U8; disposição 0.9.7).
 *
 * Blocos, de cima para baixo:
 *  1. Em uso agora — o cérebro que responde (OpenJarvis ou provedor ativo), modelo, estado e reserva.
 *  2. Provedores cadastrados — cards com Usar este / Reserva / Testar / Editar / Remover; cadastro em modal
 *     (tipo, nome, endpoint, chave no cofre, buscar modelos, modelo padrão; CLIs detectadas sugeridas).
 *  3. Instalar ou conectar — só o que ainda não está instalado ou cadastrado.
 *  4. Opções avançadas (recolhidas) — OpenJarvis opcional: card compacto e "manter ligado".
 * Ponte fora ⇒ aviso claro no topo (U8).
 */
import "./estilos/quem-responde.css";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import type { Cerebro } from "../config/cerebro";
import { atualizarConfig, type Config } from "../config/config";
import { lerPaineis, gravarPaineis, type PaineisConfig, type Provedor, type Agente, type EscolhaAgente } from "../config/paineis";
import { detectarClis, type CliDetectada } from "../config/clis";
import { cofreExiste, cofreGravar } from "../config/segredos";
import { abrirModal, campoModal, desenharCards, type Card, type TomSelo } from "./componentes";
import { InstalaveisProvedores } from "./instalaveis-provedores";

/** Formata milissegundos como "1,8 s" (PT-BR). */
export function formatarSegundos(ms: number): string {
  return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

export interface DepsQuemResponde {
  criarOj: (modelo?: string) => OpenJarvis;
  statusPonte: () => Promise<StatusPonte | null>;
  ponteUrl: string;
  config: Config;
  aoMudarCerebro?: (cerebro: Cerebro) => void;
  aoMudarUsoOpenJarvis?: (usar: boolean) => void;
}

const TIPOS_PROVEDOR: [string, string][] = [
  ["lmstudio", "LM Studio"],
  ["ollama", "Ollama / llama-server"],
  ["openai_compat", "OpenAI compatível"],
  ["openai_nativo", "OpenAI"],
  ["anthropic", "Anthropic"],
  ["google", "Google"],
  ["cli-claude", "Claude Code CLI"],
  ["cli-agy", "Antigravity CLI"],
  ["cli-codex", "Codex CLI"],
  ["cli-opencode", "OpenCode CLI"],
];

const NOMES_TIPO = new Map(TIPOS_PROVEDOR);

const EH_CLI = new Set(["cli-claude", "cli-agy", "cli-codex", "cli-opencode"]);
const SO_DELEGADA = new Set(["cli-codex", "cli-opencode"]);

/** Texto do resultado do Testar; Codex/OpenCode só confirmam a instalação (sem tempo de resposta). */
export function resumoTeste(j: { ok?: boolean; detalhe?: string; primeiro_token_ms?: number | null }): string {
  if (!j.ok) return j.detalhe === "cli_nao_encontrada" ? "CLI não encontrada neste PC." : `Falha: ${j.detalhe ?? "sem resposta"}`;
  return j.primeiro_token_ms != null ? `Conexão OK (${j.primeiro_token_ms} ms)` : `OK: ${j.detalhe ?? ""}`.trim();
}

/** Normaliza endpoint: aceita com ou sem /v1 no final. */
function normalizarEndpoint(url: string): string {
  const t = url.trim().replace(/\/+$/, "");
  if (!t) return "";
  // LM Studio e Ollama usam /v1; outros podem não usar. Deixamos como o usuário digitou.
  return t;
}

export class AbaModelos {
  private cfg!: PaineisConfig;
  private clis: CliDetectada[] = [];
  private ponteOk = true;
  private ojModelos: string[] = [];
  private ojFora = false;
  /** Lembra se o usuário abriu as opções avançadas: ações redesenham a aba. */
  private avancadoAberto = false;

  constructor(
    private raiz: HTMLElement,
    private deps: DepsQuemResponde,
  ) {}

  async carregar() {
    this.cfg = await lerPaineis();
    this.clis = await detectarClis(this.deps.ponteUrl).catch(() => []);
    const st = await this.deps.statusPonte().catch(() => null);
    this.ponteOk = st !== null;
    try {
      this.ojModelos = await this.deps.criarOj("").modelos();
      this.ojFora = false;
    } catch {
      this.ojModelos = [];
      this.ojFora = true;
    }
    await this.desenhar();
  }

  private desenhar() {
    this.raiz.innerHTML = "";
    if (!this.ponteOk) {
      const aviso = document.createElement("div");
      aviso.className = "qr-aviso-ponte";
      aviso.textContent = "Os serviços do Vard estão desligados — abra pelo atalho do Vard ou ligue em Sistema.";
      this.raiz.append(aviso);
    }
    // 1. Em uso agora
    const agora = this.bloco("Em uso agora", "nucleo-agora");
    desenharCards(agora, [this.cardEmUso()], { vazio: "" });
    // 2. Provedores cadastrados
    const cadastrados = this.bloco("Provedores cadastrados", "nucleo-provedores");
    desenharCards(cadastrados, this.montarCards(), {
      vazio: "Nenhum provedor cadastrado. Adicione um ou instale um dos sugeridos abaixo.",
      adicionar: { rotulo: "Adicionar provedor", aoClicar: () => this.abrirModal() },
    });
    // 3. Instalar ou conectar (só com os serviços ligados: a lista vem do núcleo)
    const instalacoes = this.ponteOk ? this.bloco("Instalar ou conectar", "nucleo-instalar") : null;
    // 4. Opções avançadas, recolhidas
    const avancado = document.createElement("details");
    avancado.className = "nucleo-avancado";
    avancado.open = this.avancadoAberto;
    avancado.addEventListener("toggle", () => { this.avancadoAberto = avancado.open; });
    const resumo = document.createElement("summary");
    resumo.textContent = "Opções avançadas: OpenJarvis (opcional)";
    const containerOj = document.createElement("div");
    avancado.append(resumo, containerOj);
    this.raiz.append(avancado);
    desenharCards(containerOj, [this.cardOpenJarvis()], { vazio: "" });
    const cardOj = containerOj.querySelector<HTMLElement>('[data-id="__oj__"]')!;
    const rotulo = document.createElement("label");
    const usarOj = document.createElement("input");
    usarOj.type = "checkbox";
    usarOj.checked = this.deps.config.usar_openjarvis;
    rotulo.append(usarOj, " Manter o OpenJarvis ligado mesmo quando ele não responde");
    const avisoOj = document.createElement("p");
    avisoOj.setAttribute("role", "status");
    usarOj.addEventListener("change", async () => {
      usarOj.disabled = true;
      try {
        await atualizarConfig({ usar_openjarvis: usarOj.checked });
        this.deps.config.usar_openjarvis = usarOj.checked;
        this.deps.aoMudarUsoOpenJarvis?.(usarOj.checked);
        avisoOj.textContent = "Alteração salva. Vale após reiniciar os serviços em Sistema.";
      } catch {
        usarOj.checked = this.deps.config.usar_openjarvis;
        avisoOj.textContent = "Não consegui salvar. Tente novamente.";
      } finally { usarOj.disabled = false; }
    });
    cardOj.append(rotulo, avisoOj);
    if (instalacoes) {
      return new InstalaveisProvedores(instalacoes, this.deps.ponteUrl, async (item) => {
        if (item.id === "openjarvis") { this.abrirModalOpenJarvis(); return; }
        this.clis = await detectarClis(this.deps.ponteUrl).catch(() => []);
        if (item.instalado && EH_CLI.has(item.tipo_provedor) && !this.clis.some(c => c.tipo === item.tipo_provedor && c.instalada)) {
          this.clis = this.clis.filter(c => c.tipo !== item.tipo_provedor);
          this.clis.push({ tipo: item.tipo_provedor, instalada: true, versao: "", modelos: [] });
        }
        this.abrirModal(undefined, { tipo: item.tipo_provedor, nome: item.nome, url_base: item.url_base });
      }, () => this.cfg.provedores).carregar();
    }
    return Promise.resolve();
  }

  /** Bloco com título, no estilo dos demais da janela (fieldset + legenda). */
  private bloco(titulo: string, classe: string): HTMLElement {
    const f = document.createElement("fieldset");
    f.className = `nucleo-bloco ${classe}`;
    const l = document.createElement("legend");
    l.textContent = titulo;
    const miolo = document.createElement("div");
    f.append(l, miolo);
    this.raiz.append(f);
    return miolo;
  }

  private ojSelos(): { texto: string; tom: TomSelo }[] {
    return this.ojFora ? [{ texto: "Fora do ar", tom: "aviso" }] : [{ texto: "No ar", tom: "ok" }];
  }

  /** Card do topo: quem responde agora, com o estado e a reserva. */
  private cardEmUso(): Card {
    if (this.deps.config.cerebro === "openjarvis") {
      return {
        id: "__agora__",
        titulo: "OpenJarvis",
        etiqueta: "openjarvis",
        selos: [{ texto: "Responde agora", tom: "ativo" }, ...this.ojSelos()],
        detalhes: [`modelo: ${this.deps.config.modelo || "automático"}`, this.deps.config.openjarvis_url],
        acoes: [
          { rotulo: "Testar", aoClicar: () => this.testarOpenJarvis() },
          { rotulo: "Editar", aoClicar: () => this.abrirModalOpenJarvis() },
        ],
      };
    }
    const p = this.cfg.provedores.find((x) => x.id === this.cfg.ativo);
    if (!p) {
      return {
        id: "__agora__",
        titulo: "Nenhum provedor escolhido",
        selos: [{ texto: "Sem cérebro", tom: "aviso" }],
        detalhes: ["Escolha um provedor cadastrado com “Usar este” ou adicione um novo."],
      };
    }
    const reserva = this.cfg.provedores.find((x) => x.id === this.cfg.reserva);
    const selos: { texto: string; tom: TomSelo }[] = [{ texto: "Responde agora", tom: "ativo" }];
    if (!this.ponteOk) selos.push({ texto: "Serviços desligados", tom: "aviso" });
    return {
      id: "__agora__",
      titulo: p.nome,
      etiqueta: NOMES_TIPO.get(p.tipo) ?? p.tipo,
      selos,
      detalhes: [`modelo: ${p.modelo}`, ...(p.url_base ? [p.url_base] : []), reserva ? `Reserva: ${reserva.nome}` : "Sem reserva"],
      acoes: [
        { rotulo: "Testar", aoClicar: () => this.testarProvedor(p) },
        { rotulo: "Editar", aoClicar: () => this.abrirModal(p) },
      ],
    };
  }

  /** OpenJarvis fixo — card compacto (modelo em uso ou "automático" + "+N modelos"). */
  private cardOpenJarvis(): Card {
    const ojSelos: { texto: string; tom: TomSelo }[] = [];
    if (this.deps.config.cerebro === "openjarvis") ojSelos.push({ texto: "Responde agora", tom: "ativo" });
    if (this.ojFora) ojSelos.push({ texto: "Fora do ar", tom: "aviso" });
    const ojFichasCompactas = [this.deps.config.modelo || "automático"];
    if (this.ojModelos.length > 1) {
      ojFichasCompactas.push(`+${this.ojModelos.length - 1} modelos`);
    }
    return {
      id: "__oj__",
      titulo: "OpenJarvis (servidor atual)",
      etiqueta: "openjarvis",
      selos: ojSelos,
      detalhes: [this.deps.config.openjarvis_url],
      fichas: ojFichasCompactas,
      acoes: [
        { rotulo: "Usar este", primaria: true, aoClicar: () => this.usarOpenJarvis() },
        { rotulo: "Testar", aoClicar: () => this.testarOpenJarvis() },
        { rotulo: "Editar", aoClicar: () => this.abrirModalOpenJarvis() },
      ],
    };
  }

  private montarCards(): Card[] {
    const lista: Card[] = [];
    for (const p of this.cfg.provedores) {
      const ehCli = EH_CLI.has(p.tipo);
      const soDelegada = SO_DELEGADA.has(p.tipo);
      const selos: { texto: string; tom: TomSelo }[] = [];
      const respondeAgora = this.deps.config.cerebro === "proprio" && this.cfg.ativo === p.id;
      if (respondeAgora) selos.push({ texto: "Responde agora", tom: "ativo" });
      if (this.cfg.reserva === p.id) selos.push({ texto: "Reserva", tom: "reserva" });
      const acoes: Card["acoes"] = [];
      // Quem já responde não precisa de "Usar este" nem pode ser a própria reserva (Reserva clicada de novo desmarca).
      if (!soDelegada && !respondeAgora) {
        acoes.push({ rotulo: "Usar este", primaria: true, aoClicar: () => this.usarProvedor(p.id) });
        acoes.push({ rotulo: "Reserva", aoClicar: () => this.definirReserva(p.id) });
      }
      acoes.push({ rotulo: "Testar", aoClicar: () => this.testarProvedor(p) });
      acoes.push({ rotulo: "Editar", aoClicar: () => this.abrirModal(p) });
      acoes.push({ rotulo: "Remover", perigo: true, aoClicar: () => this.remover(p.id) });
      const detalhes = ehCli ? [`modelo: ${p.modelo}`] : [p.url_base, `modelo: ${p.modelo}`];
      if (soDelegada) detalhes.push("Só para tarefas longas (delegadas)");
      lista.push({
        id: p.id,
        titulo: p.nome,
        etiqueta: NOMES_TIPO.get(p.tipo) ?? p.tipo,
        selos,
        detalhes,
        acoes,
        busca: `${p.nome} ${p.tipo} ${p.url_base} ${p.modelo}`,
      });
    }
    return lista;
  }

  private async usarOpenJarvis() {
    await atualizarConfig({ cerebro: "openjarvis" });
    this.deps.config.cerebro = "openjarvis";
    this.deps.aoMudarCerebro?.("openjarvis");
    this.desenhar();
  }

  private async usarProvedor(id: string) {
    this.cfg.ativo = id;
    await gravarPaineis(this.cfg);
    await atualizarConfig({ cerebro: "proprio" });
    this.deps.config.cerebro = "proprio";
    this.deps.aoMudarCerebro?.("proprio");
    this.desenhar();
  }

  private async definirReserva(id: string) {
    this.cfg.reserva = this.cfg.reserva === id ? null : id;
    await gravarPaineis(this.cfg);
    this.desenhar();
  }

  private async remover(id: string) {
    this.cfg.provedores = this.cfg.provedores.filter((p) => p.id !== id);
    if (this.cfg.ativo === id) this.cfg.ativo = null;
    if (this.cfg.reserva === id) this.cfg.reserva = null;
    await gravarPaineis(this.cfg);
    this.desenhar();
  }

  private async testarOpenJarvis() {
    const corpoTesteOj = document.createElement("p");
    corpoTesteOj.textContent = "Perguntando...";
    const modal = abrirModal({ titulo: "Testando OpenJarvis", corpo: corpoTesteOj }, this.raiz);
    try {
      const t0 = performance.now();
      const resp = await this.deps.criarOj("").perguntar([{ role: "user", content: "Responda apenas: ok." }]);
      const ms = ((performance.now() - t0) / 1000).toFixed(1).replace(".", ",");
      modal.avisar(`OK em ${ms} s: "${resp.slice(0, 60)}"`);
    } catch (e) {
      modal.avisar(`Falhou: ${String(e)}`, true);
    }
  }

  private async testarProvedor(p: Provedor) {
    const corpoTesteProv = document.createElement("p");
    corpoTesteProv.textContent = "Conectando...";
    const modal = abrirModal({ titulo: `Testando ${p.nome}`, corpo: corpoTesteProv }, this.raiz);
    try {
      const r = await fetch(`${this.deps.ponteUrl}/primeiro-uso/cerebro/testar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // A chave fica no cofre: o núcleo usa a do provedor salvo pelo id.
        body: JSON.stringify({ tipo: p.tipo, base_url: p.url_base, modelo: p.modelo, chave: "", provedor_id: p.id }),
        signal: AbortSignal.timeout(35000),
      });
      const j = await r.json().catch(() => ({ ok: false, detalhe: "sem resposta" }));
      modal.avisar(resumoTeste(j), !j.ok);
    } catch (e) {
      modal.avisar(`Erro: ${String(e)}`, true);
    }
  }

  /** Modal de edição do OpenJarvis: escolha do modelo entre os disponíveis. */
  private abrirModalOpenJarvis() {
    const corpo = document.createElement("div");
    corpo.className = "qr-modal-campos";
    const modeloSel = document.createElement("select");
    const opAuto = document.createElement("option");
    opAuto.value = "";
    opAuto.textContent = "automático";
    modeloSel.append(opAuto);
    for (const m of this.ojModelos) {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      modeloSel.append(o);
    }
    modeloSel.value = this.deps.config.modelo || "";
    corpo.append(campoModal("Modelo do OpenJarvis", modeloSel, "Escolha um modelo específico ou deixe em automático."));

    const salvar = async (): Promise<boolean> => {
      await atualizarConfig({ modelo: modeloSel.value });
      this.deps.config.modelo = modeloSel.value;
      this.desenhar();
      return true;
    };

    abrirModal({
      titulo: "Editar OpenJarvis",
      corpo,
      acoes: [
        { rotulo: "Cancelar", aoClicar: () => true },
        { rotulo: "Salvar", primaria: true, aoClicar: salvar },
      ],
    }, this.raiz);
  }

  private abrirModal(provedor?: Provedor, sugestao?: Partial<Provedor>) {
    const editando = !!provedor;
    const inicial = provedor ?? sugestao;
    const corpo = document.createElement("div");
    corpo.className = "qr-modal-campos";
    const tipoSel = document.createElement("select");
    for (const [v, t] of TIPOS_PROVEDOR) {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = t;
      tipoSel.append(o);
    }
    tipoSel.value = inicial?.tipo ?? "lmstudio";
    const nomeInp = document.createElement("input");
    nomeInp.type = "text";
    nomeInp.placeholder = "Nome do provedor";
    nomeInp.value = inicial?.nome ?? "";
    const urlInp = document.createElement("input");
    urlInp.type = "url";
    urlInp.placeholder = "http://localhost:1234/v1";
    urlInp.value = inicial?.url_base ?? "";
    // Chave de API (cofre) — nunca mostra o valor salvo
    const chaveInp = document.createElement("input");
    chaveInp.type = "password";
    chaveInp.placeholder = "Chave de API (opcional)";
    let chaveExistente = false;
    if (editando && provedor!.credencial_ref) {
      // Verifica se existe no cofre; se sim, mostra placeholder informativo
      void cofreExiste("provedor", provedor!.id).then((existe) => {
        if (existe) {
          chaveExistente = true;
          chaveInp.placeholder = "Chave salva ✓ (deixe vazio para manter)";
        }
      });
    }
    // Select de modelo padrão (preenchido após Buscar modelos)
    const modeloSel = document.createElement("select");
    const modeloPadraoInput = document.createElement("input");
    modeloPadraoInput.type = "text";
    modeloPadraoInput.placeholder = "Modelo padrão (ou digite outro)";
    modeloPadraoInput.value = inicial?.modelo ?? "";
    // Container que alterna entre input e select após busca
    const modeloContainer = document.createElement("div");
    modeloContainer.className = "qr-modelo-container";
    modeloContainer.append(modeloPadraoInput);
    const buscaBtn = document.createElement("button");
    buscaBtn.type = "button";
    buscaBtn.textContent = "Buscar modelos";
    const statusEl = document.createElement("div");
    statusEl.className = "qr-modal-status";
    const buscaWrap = document.createElement("div");
    buscaWrap.className = "qr-modal-busca";
    buscaWrap.append(buscaBtn, statusEl);
    // Containers de campos que aparecem/desaparecem conforme o tipo
    const campoEndpoint = campoModal("Endpoint", urlInp, "Vazio para CLIs. Aceita com ou sem /v1.");
    const campoChave = campoModal("Chave de API", chaveInp, "Salva no cofre; nunca exibida.");
    const campoBusca = buscaWrap;

    // Linha de detecção CLI
    const cliDetectadoEl = document.createElement("div");
    cliDetectadoEl.className = "qr-cli-detectado";
    cliDetectadoEl.hidden = true;

    // Aviso CLI não encontrada
    const cliNaoEncontradoEl = document.createElement("div");
    cliNaoEncontradoEl.className = "qr-cli-nao-encontrado qr-modal-status ruim";
    cliNaoEncontradoEl.hidden = true;
    cliNaoEncontradoEl.textContent = "Não encontrado neste PC — instale e faça login nele antes.";

    // Aviso C11 (sempre visível quando é CLI)
    const avisoC11El = document.createElement("div");
    avisoC11El.className = "qr-aviso-c11 qr-modal-status";
    avisoC11El.hidden = true;
    avisoC11El.textContent = "Atenção: a CLI roda com poder completo no seu PC; com yolo, sem pedir permissão.";

    // Yolo / Enxuto checkboxes
    const yoloLabel = document.createElement("label");
    yoloLabel.className = "marca";
    yoloLabel.hidden = true;
    const yoloChk = document.createElement("input");
    yoloChk.type = "checkbox";
    yoloChk.checked = true; // padrão do 0.8
    yoloLabel.append(yoloChk, document.createTextNode(" Rodar sem pedir permissão (yolo)"));

    const enxutoLabel = document.createElement("label");
    enxutoLabel.className = "marca";
    enxutoLabel.hidden = true;
    const enxutoChk = document.createElement("input");
    enxutoChk.type = "checkbox";
    enxutoLabel.append(enxutoChk, document.createTextNode(" Modo enxuto"));

    // Checkbox delegada (agentes)
    const delegadaLabel = document.createElement("label");
    delegadaLabel.className = "marca";
    delegadaLabel.hidden = true;
    const delegadaChk = document.createElement("input");
    delegadaChk.type = "checkbox";
    delegadaLabel.append(delegadaChk, document.createTextNode(" Usar também em tarefas longas (delegadas)"));
    const delegadaAviso = document.createElement("div");
    delegadaAviso.className = "qr-delegada-aviso";
    delegadaAviso.hidden = true;

    const atualizarVisibilidade = () => {
      const ehCli = EH_CLI.has(tipoSel.value);
      const soDelegada = SO_DELEGADA.has(tipoSel.value);

      // Esconde/mostra campos conforme tipo
      campoEndpoint.hidden = ehCli;
      campoChave.hidden = ehCli;
      campoBusca.hidden = ehCli;
      cliDetectadoEl.hidden = !ehCli;
      cliNaoEncontradoEl.hidden = !ehCli;
      avisoC11El.hidden = !ehCli;
      yoloLabel.hidden = !ehCli;
      enxutoLabel.hidden = !ehCli;
      delegadaLabel.hidden = !ehCli;
      delegadaAviso.hidden = !ehCli;

      if (ehCli) {
        urlInp.value = "";
        chaveInp.value = "";

        // Detecção da CLI
        const cli = this.clis.find((c) => c.tipo === tipoSel.value);
        if (cli && cli.instalada) {
          cliDetectadoEl.hidden = false;
          cliDetectadoEl.innerHTML = "";
          const txt = document.createElement("span");
          const ROTULOS_CLI: Record<string, string> = {
  "cli-claude": "Claude Code",
  "cli-agy": "Antigravity",
  "cli-codex": "Codex",
  "cli-opencode": "OpenCode",
};
txt.textContent = `Encontrado no PC: ${ROTULOS_CLI[cli.tipo] ?? cli.tipo} ${cli.versao}`;
          const btnUsar = document.createElement("button");
          btnUsar.type = "button";
          btnUsar.textContent = "Usar modelos detectados";
          btnUsar.addEventListener("click", () => {
            nomeInp.value = nomeInp.value || cli.tipo.replace("cli-", "");
            modeloPadraoInput.value = modeloPadraoInput.value || cli.modelos[0] || "";
            preencherModelosSelect(cli.modelos);
          });
          cliDetectadoEl.append(txt, btnUsar);
          cliNaoEncontradoEl.hidden = true;
        } else {
          cliDetectadoEl.hidden = true;
          cliNaoEncontradoEl.hidden = false;
        }

        // Tarefas longas: Codex/OpenCode sempre marcado e travado
        if (soDelegada) {
          delegadaChk.checked = true;
          delegadaChk.disabled = true;
          delegadaAviso.textContent = "Este provedor serve só para tarefas longas (delegadas); não pode ser o cérebro principal.";
          delegadaAviso.hidden = false;
        } else {
          delegadaChk.disabled = false;
          delegadaAviso.hidden = true;
        }
      } else {
        // Ajuda contextual para LM Studio
        if (tipoSel.value === "lmstudio") {
          chaveInp.placeholder = chaveExistente
            ? "Chave salva ✓ (deixe vazio para manter)"
            : "Chave do servidor local, se ele pedir (opcional)";
        } else {
          chaveInp.placeholder = chaveExistente
            ? "Chave salva ✓ (deixe vazio para manter)"
            : "Chave de API (opcional)";
        }
      }
    };
    tipoSel.addEventListener("change", atualizarVisibilidade);
    atualizarVisibilidade();

    /** Troca o container de modelo para um select com os modelos achados. */
    const preencherModelosSelect = (ids: string[]) => {
      modeloContainer.innerHTML = "";
      modeloSel.innerHTML = "";
      for (const m of ids) {
        const o = document.createElement("option");
        o.value = m;
        o.textContent = m;
        modeloSel.append(o);
      }
      // Se já tinha um valor digitado e está na lista, seleciona
      if (modeloPadraoInput.value && ids.includes(modeloPadraoInput.value)) {
        modeloSel.value = modeloPadraoInput.value;
      }
      modeloContainer.append(modeloSel);
    };

    buscaBtn.addEventListener("click", async () => {
      statusEl.textContent = "Buscando...";
      statusEl.classList.remove("ruim");
      try {
        const endpoint = normalizarEndpoint(urlInp.value);
        const r = await fetch(`${this.deps.ponteUrl}/primeiro-uso/cerebro/modelos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo: tipoSel.value, base_url: endpoint, chave: chaveInp.value.trim(), provedor_id: provedor?.id }),
          signal: AbortSignal.timeout(15000),
        });
        const j = await r.json().catch(() => ({ ok: false, detalhe: "sem resposta" }));
        if (!j.ok) { statusEl.textContent = `Falha: ${j.detalhe}`; statusEl.classList.add("ruim"); return; }
        const ids = (j.modelos as { id: string }[]).map((m) => m.id);
        preencherModelosSelect(ids);
        statusEl.textContent = `${ids.length} modelo(s) encontrado(s).`;
      } catch (e) {
        statusEl.textContent = `Erro: ${String(e)}`;
        statusEl.classList.add("ruim");
      }
    });

    corpo.append(
      campoModal("Tipo", tipoSel),
      campoModal("Nome", nomeInp),
      campoEndpoint,
      campoChave,
      campoBusca,
      cliDetectadoEl,
      cliNaoEncontradoEl,
      campoModal("Modelo", modeloContainer, "Opcional para CLIs: escolha da lista detectada ou digite outro."),
      yoloLabel,
      enxutoLabel,
      avisoC11El,
      delegadaLabel,
      delegadaAviso,
    );

    let modalRef: ReturnType<typeof abrirModal> | undefined;

    const testarNoModal = async () => {
      const tipo = tipoSel.value;
      const ehCli = EH_CLI.has(tipo);
      const url = normalizarEndpoint(urlInp.value);
      const modelo = (modeloContainer.querySelector("select") as HTMLSelectElement)?.value || modeloPadraoInput.value.trim();
      if (ehCli) {
        // CLI: verifica se está instalada antes de testar
        const cli = this.clis.find((c) => c.tipo === tipo);
        if (!cli || !cli.instalada) {
          modalRef?.avisar("CLI não encontrada neste PC. Instale e faça login antes de testar.", true);
          return;
        }
      } else if (!url) {
        modalRef?.avisar("Preencha o endpoint para testar.", true);
        return;
      }
      if (!modelo && !ehCli) {
        modalRef?.avisar("Preencha o modelo para testar.", true);
        return;
      }
      modalRef?.avisar("Testando...");
      try {
        const r = await fetch(`${this.deps.ponteUrl}/primeiro-uso/cerebro/testar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo, base_url: ehCli ? "" : url, modelo, chave: ehCli ? "" : chaveInp.value.trim(), provedor_id: provedor?.id }),
          signal: AbortSignal.timeout(35000),
        });
        const j = await r.json().catch(() => ({ ok: false, detalhe: "sem resposta" }));
        modalRef?.avisar(resumoTeste(j), !j.ok);
      } catch (e) {
        modalRef?.avisar(`Erro: ${String(e)}`, true);
      }
    };

    const salvar = async (): Promise<boolean> => {
      const tipo = tipoSel.value;
      const nome = nomeInp.value.trim();
      const url = normalizarEndpoint(urlInp.value);
      const chave = chaveInp.value.trim();
      const modelo = (modeloContainer.querySelector("select") as HTMLSelectElement)?.value || modeloPadraoInput.value.trim();
      if (!nome || !tipo || !modelo || (!EH_CLI.has(tipo) && !url)) {
        modalRef?.avisar("Preencha nome, tipo, endpoint e modelo.", true);
        return false;
      }
      const id = provedor?.id ?? (nome.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 32) || `prov-${Date.now()}`);
      // Grava chave no cofre se fornecida
      let credRef: string | undefined;
      if (!EH_CLI.has(tipo)) {
        if (chave) {
          try {
            await cofreGravar("provedor", id, chave);
          } catch (e) {
            modalRef?.avisar(`Erro ao salvar chave: ${String(e)}`, true);
            return false;
          }
        }
        credRef = chave ? `provedor:${id}` : (editando ? provedor!.credencial_ref : undefined);
      }
      const novo: Provedor = {
        id,
        nome,
        tipo,
        url_base: EH_CLI.has(tipo) ? "" : url,
        modelo,
        ...(EH_CLI.has(tipo)
          ? { yolo: yoloChk.checked, enxuto: enxutoChk.checked }
          : { credencial_ref: credRef }),
      };
      const idx = this.cfg.provedores.findIndex((p) => p.id === id);
      if (editando && idx >= 0) {
        this.cfg.provedores[idx] = novo;
      } else if (!editando && this.cfg.provedores.some((p) => p.id === id)) {
        modalRef?.avisar(`Já existe um provedor com ID "${id}".`, true);
        return false;
      } else {
        this.cfg.provedores.push(novo);
      }

      // Agentes delegados (CLI)
      if (EH_CLI.has(tipo) && delegadaChk.checked) {
        const ag = tipo.replace("cli-", "") as Agente;
        const modelos = modeloContainer.querySelector("select")
          ? Array.from((modeloContainer.querySelector("select") as HTMLSelectElement).options).map((o) => o.value)
          : [];
        this.cfg.agentes[ag] = { padrao: modelo, modelos } as EscolhaAgente;
      }

      await gravarPaineis(this.cfg);
      this.desenhar();
      return true;
    };

    modalRef = abrirModal({
      titulo: editando ? `Editar ${provedor!.nome}` : "Adicionar provedor",
      corpo,
      acoes: [
        { rotulo: "Testar", aoClicar: () => { void testarNoModal(); return false; } },
        { rotulo: "Cancelar", aoClicar: () => true },
        { rotulo: "Salvar", primaria: true, aoClicar: salvar },
      ],
    }, this.raiz);
  }
}
