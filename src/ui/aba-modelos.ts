/**
 * Seção "Quem responde" (0.9.3 U1–U4, U8).
 *
 * Cards de provedores (OpenJarvis fixo + cadastrados) com ações Usar este / Reserva / Testar / Editar / Remover.
 * Modal de adicionar/editar com tipo, nome, endpoint, chave (cofre), buscar modelos, modelo padrão e teste.
 * CLIs detectadas aparecem sugeridas; agentes gravados pelo card da CLI.
 * Ponte fora ⇒ aviso claro no topo (U8).
 */
import "./estilos/quem-responde.css";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import type { Cerebro } from "../config/cerebro";
import { atualizarConfig, type Config } from "../config/config";
import { lerPaineis, gravarPaineis, type PaineisConfig, type Provedor, type Agente, type EscolhaAgente } from "../config/paineis";
import { detectarClis, type CliDetectada } from "../config/clis";
import { abrirModal, campoModal, desenharCards, type Card, type TomSelo } from "./componentes";

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

const EH_CLI = new Set(["cli-claude", "cli-agy", "cli-codex", "cli-opencode"]);
const SO_DELEGADA = new Set(["cli-codex", "cli-opencode"]);

export class AbaModelos {
  private cfg!: PaineisConfig;
  private clis: CliDetectada[] = [];
  private ponteOk = true;
  private ojModelos: string[] = [];
  private ojFora = false;

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
    this.desenhar();
  }

  private desenhar() {
    this.raiz.innerHTML = "";
    if (!this.ponteOk) {
      const aviso = document.createElement("div");
      aviso.className = "qr-aviso-ponte";
      aviso.textContent = "Os serviços do Vard estão desligados — abra pelo atalho do Vard ou ligue em Sistema.";
      this.raiz.append(aviso);
    }
    const container = document.createElement("div");
    container.className = "qr-cards-container";
    this.raiz.append(container);
    const cards = this.montarCards();
    desenharCards(container, cards, {
      vazio: "Nenhum provedor cadastrado.",
      adicionar: { rotulo: "Adicionar provedor", aoClicar: () => this.abrirModal() },
    });
  }

  private montarCards(): Card[] {
    const lista: Card[] = [];
    // OpenJarvis fixo
    const ojSelos: { texto: string; tom: TomSelo }[] = [];
    if (this.deps.config.cerebro === "openjarvis") ojSelos.push({ texto: "Responde agora", tom: "ativo" });
    if (this.ojFora) ojSelos.push({ texto: "Fora do ar", tom: "aviso" });
    lista.push({
      id: "__oj__",
      titulo: "OpenJarvis (servidor atual)",
      etiqueta: "openjarvis",
      selos: ojSelos,
      detalhes: [this.deps.config.openjarvis_url],
      fichas: this.ojModelos.slice(0, 12),
      acoes: [
        { rotulo: "Usar este", primaria: true, aoClicar: () => this.usarOpenJarvis() },
        { rotulo: "Testar", aoClicar: () => this.testarOpenJarvis() },
      ],
    });
    // Provedores cadastrados
    for (const p of this.cfg.provedores) {
      const ehCli = EH_CLI.has(p.tipo);
      const soDelegada = SO_DELEGADA.has(p.tipo);
      const selos: { texto: string; tom: TomSelo }[] = [];
      if (this.deps.config.cerebro === "proprio" && this.cfg.ativo === p.id) selos.push({ texto: "Responde agora", tom: "ativo" });
      if (this.cfg.reserva === p.id) selos.push({ texto: "Reserva", tom: "reserva" });
      const acoes: Card["acoes"] = [];
      if (!soDelegada) {
        acoes.push({ rotulo: "Usar este", primaria: true, aoClicar: () => this.usarProvedor(p.id) });
        acoes.push({ rotulo: "Reserva", aoClicar: () => this.definirReserva(p.id) });
      }
      acoes.push({ rotulo: "Testar", aoClicar: () => this.testarProvedor(p) });
      acoes.push({ rotulo: "Editar", aoClicar: () => this.abrirModal(p) });
      acoes.push({ rotulo: "Remover", perigo: true, aoClicar: () => this.remover(p.id) });
      const detalhes = ehCli ? [`tipo: ${p.tipo}`, p.modelo] : [p.url_base, p.modelo];
      lista.push({
        id: p.id,
        titulo: p.nome,
        etiqueta: p.tipo,
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
        body: JSON.stringify({ tipo: p.tipo, base_url: p.url_base, modelo: p.modelo, chave: "" }),
        signal: AbortSignal.timeout(15000),
      });
      const j = await r.json().catch(() => ({ ok: false, detalhe: "sem resposta" }));
      modal.avisar(j.ok ? `Conexão OK (${j.primeiro_token_ms ?? "?"} ms)` : `Falha: ${j.detalhe}`, !j.ok);
    } catch (e) {
      modal.avisar(`Erro: ${String(e)}`, true);
    }
  }

  private abrirModal(provedor?: Provedor) {
    const editando = !!provedor;
    const corpo = document.createElement("div");
    corpo.className = "qr-modal-campos";
    const tipoSel = document.createElement("select");
    for (const [v, t] of TIPOS_PROVEDOR) {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = t;
      tipoSel.append(o);
    }
    tipoSel.value = provedor?.tipo ?? "lmstudio";
    const nomeInp = document.createElement("input");
    nomeInp.type = "text";
    nomeInp.placeholder = "Nome do provedor";
    nomeInp.value = provedor?.nome ?? "";
    const urlInp = document.createElement("input");
    urlInp.type = "url";
    urlInp.placeholder = "http://localhost:1234/v1";
    urlInp.value = provedor?.url_base ?? "";
    const credInp = document.createElement("input");
    credInp.type = "password";
    credInp.placeholder = "Referência da credencial (tipo:id)";
    credInp.value = provedor?.credencial_ref ?? "";
    const modeloSel = document.createElement("select");
    const modeloPadrao = document.createElement("input");
    modeloPadrao.type = "text";
    modeloPadrao.placeholder = "Modelo padrão";
    modeloPadrao.value = provedor?.modelo ?? "";
    const buscaBtn = document.createElement("button");
    buscaBtn.type = "button";
    buscaBtn.textContent = "Buscar modelos";
    const statusEl = document.createElement("div");
    statusEl.className = "qr-modal-status";
    const buscaWrap = document.createElement("div");
    buscaWrap.className = "qr-modal-busca";
    buscaWrap.append(buscaBtn, statusEl);
    // Sugestão de CLI detectada
    const cliSugestao = document.createElement("div");
    cliSugestao.className = "qr-cli-sugestao";
    cliSugestao.hidden = true;
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
      urlInp.disabled = ehCli;
      credInp.disabled = ehCli;
      buscaBtn.disabled = ehCli;
      delegadaLabel.hidden = !ehCli;
      delegadaAviso.hidden = !ehCli;
      if (ehCli) {
        urlInp.value = "";
        credInp.value = "";
        const cli = this.clis.find((c) => c.tipo === tipoSel.value);
        if (cli) {
          cliSugestao.hidden = false;
          cliSugestao.innerHTML = "";
          const txt = document.createElement("span");
          txt.textContent = `Encontrado no PC: ${cli.tipo} ${cli.versao}`;
          const btnUsar = document.createElement("button");
          btnUsar.type = "button";
          btnUsar.textContent = "Usar este";
          btnUsar.addEventListener("click", () => {
            nomeInp.value = nomeInp.value || cli.tipo;
            modeloPadrao.value = modeloPadrao.value || cli.modelos[0] || "";
            preencherModelos(cli.modelos);
          });
          cliSugestao.append(txt, btnUsar);
        } else {
          cliSugestao.hidden = true;
        }
        if (SO_DELEGADA.has(tipoSel.value)) {
          delegadaAviso.textContent = "Este provedor só funciona em tarefas delegadas; não pode ser o cérebro principal.";
          delegadaAviso.hidden = false;
        }
      } else {
        cliSugestao.hidden = true;
        delegadaAviso.hidden = true;
      }
    };
    tipoSel.addEventListener("change", atualizarVisibilidade);
    atualizarVisibilidade();

    const preencherModelos = (ids: string[]) => {
      modeloSel.innerHTML = "";
      for (const m of ids) {
        const o = document.createElement("option");
        o.value = m;
        o.textContent = m;
        modeloSel.append(o);
      }
      if (modeloPadrao.value && ids.includes(modeloPadrao.value)) modeloSel.value = modeloPadrao.value;
    };

    buscaBtn.addEventListener("click", async () => {
      statusEl.textContent = "Buscando...";
      statusEl.classList.remove("ruim");
      try {
        const r = await fetch(`${this.deps.ponteUrl}/primeiro-uso/cerebro/modelos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo: tipoSel.value, base_url: urlInp.value.trim(), chave: credInp.value.trim() }),
          signal: AbortSignal.timeout(15000),
        });
        const j = await r.json().catch(() => ({ ok: false, detalhe: "sem resposta" }));
        if (!j.ok) { statusEl.textContent = `Falha: ${j.detalhe}`; statusEl.classList.add("ruim"); return; }
        const ids = (j.modelos as { id: string }[]).map((m) => m.id);
        preencherModelos(ids);
        statusEl.textContent = `${ids.length} modelo(s) encontrado(s).`;
      } catch (e) {
        statusEl.textContent = `Erro: ${String(e)}`;
        statusEl.classList.add("ruim");
      }
    });

    corpo.append(
      campoModal("Tipo", tipoSel),
      campoModal("Nome", nomeInp),
      campoModal("Endpoint", urlInp, "Vazio para CLIs."),
      campoModal("Credencial", credInp, "Referência ao cofre (tipo:id). Nunca exibida."),
      buscaWrap,
      campoModal("Modelo padrão", modeloPadrao),
      campoModal("Modelos disponíveis", modeloSel),
      cliSugestao,
      delegadaLabel,
      delegadaAviso,
    );

    const salvar = async (): Promise<boolean> => {
      const tipo = tipoSel.value;
      const nome = nomeInp.value.trim();
      const url = urlInp.value.trim();
      const cred = credInp.value.trim();
      const modelo = modeloPadrao.value.trim() || modeloSel.value;
      if (!nome || !tipo || !modelo || (!EH_CLI.has(tipo) && !url)) {
        modal.avisar("Preencha nome, tipo, endpoint e modelo.", true);
        return false;
      }
      const id = provedor?.id ?? (nome.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 32) || `prov-${Date.now()}`);
      const novo: Provedor = {
        id,
        nome,
        tipo,
        url_base: EH_CLI.has(tipo) ? "" : url,
        modelo,
        ...(EH_CLI.has(tipo) ? {} : { credencial_ref: cred || undefined }),
      };
      const idx = this.cfg.provedores.findIndex((p) => p.id === id);
      if (editando && idx >= 0) this.cfg.provedores[idx] = novo;
      else if (!editando && this.cfg.provedores.some((p) => p.id === id)) {
        modal.avisar(`Já existe um provedor com ID "${id}".`, true);
        return false;
      } else this.cfg.provedores.push(novo);
      // Agentes delegados
      if (EH_CLI.has(tipo) && delegadaChk.checked) {
        const ag = tipo.replace("cli-", "") as Agente;
        const modelos = [...modeloSel.options].map((o) => o.value);
        this.cfg.agentes[ag] = { padrao: modelo, modelos } as EscolhaAgente;
      }
      await gravarPaineis(this.cfg);
      this.desenhar();
      return true;
    };

    const modal = abrirModal({
      titulo: editando ? `Editar ${provedor!.nome}` : "Adicionar provedor",
      corpo,
      acoes: [{ rotulo: "Salvar", primaria: true, aoClicar: salvar }],
    }, this.raiz);
  }
}