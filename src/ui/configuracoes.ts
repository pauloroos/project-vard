import { invoke } from "@tauri-apps/api/core";
import { emitTo } from "@tauri-apps/api/event";
import type { Config } from "../config/config";
import { avisosDeUrl, limitarLado, mudancasQueExigemReinicio, salvarConfig, urlLocal } from "../config/config";
import { ACOES_ATALHO, ROTULOS_ATALHO, avisoAltGr, validarAtalhos, type AcaoAtalho, type FalhaAtalho } from "../config/atalhos";
import { campoIdioma } from "../config/idiomas";
import { gravarPerfil, lerPerfil, previaPersona } from "../config/perfil";
import { campoAtalho } from "./campo-atalho";
import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import type { PonteAvisos } from "../avisos/central";
import { AbaAtualizacao } from "./aba-atualizacao";
import "./estilos/geral.css";
import { AbaAvisos } from "./aba-avisos";
import { AbaDiagnostico } from "./aba-diagnostico";
import { AbaModelos } from "./aba-modelos";
import { AbaPerfil } from "./aba-perfil";
import { AbaPaineisMcps } from "./paineis-mcps";
import { AbaReuniao, type PonteReuniao } from "./aba-reuniao";
import { AbaOficina } from "./aba-oficina";
import { AbaSistema } from "./aba-sistema";
import { AbaVoz } from "./aba-voz";
import { InstaladorVozes } from "./instalador-vozes";
import { MonitorRecursos } from "./monitor-recursos";
import "./estilos/monitor-recursos.css";

export interface DepsConfiguracoes {
  /** Cliente do OpenJarvis para o endereço dado (o main decide se passa pelo proxy do dev). */
  criarOj: (url: string, modelo?: string) => OpenJarvis;
  /** Status da ponte no endereço dado (null = fora ou desligada). */
  statusPonte: (url: string) => Promise<StatusPonte | null>;
  /** Dispara um verbo do ciclo da ponte no endereço dado (true = aceitou). */
  modoPonte: (url: string, verbo: string) => Promise<boolean>;
  /** Cliente da ponte no endereço dado (avisos, tarefas, reunião e eventos ao vivo). */
  ponte: (url: string) => PonteAvisos & PonteReuniao;
  /** Depois de gravar: o main avisa o widget (evento config-salva). */
  aoSalvar?: (c: Config) => void;
  /** Fecha a janela do painel. */
  fechar?: () => void;
  /** Release do GitHub: endereço da consulta, GET pelo Rust, instalação do setup e versão instalada. */
  atualizacao: { url: string; buscar: (url: string) => Promise<string>; instalar: (setup: { nome: string; url: string; bytes: number; sha256: string | null }) => Promise<void>; versao: () => Promise<string> };
}

/** Monitor como o comando listar_monitores devolve (pixels físicos). */
export interface MonitorInfo { nome: string; x: number; y: number; largura: number; altura: number; escala: number; principal: boolean }

export type Aba = "geral" | "perfil" | "voz" | "atalhos" | "oficina" | "modelos" | "paineis-mcps" | "sistema" | "reuniao" | "avisos" | "diagnostico";
const ABAS: [Aba, string][] = [
  ["geral", "Geral"], ["perfil", "Perfil"], ["voz", "Voz"], ["atalhos", "Atalhos"], ["oficina", "Oficina"], ["modelos", "Quem responde"],
  ["paineis-mcps", "Ferramentas (MCP)"],
  ["sistema", "Sistema"], ["reuniao", "Reunião"], ["avisos", "Avisos"], ["diagnostico", "Diagnóstico"],
];
const OPCOES_TAMANHO: [Config["tamanho"], string][] = [
  ["pequeno", "Pequeno (240 px)"], ["medio", "Médio (320 px)"], ["grande", "Grande (480 px)"], ["personalizado", "Personalizado"],
];

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Painel de configurações na janela própria "configuracoes": abas e um campo por chave editável do Config. */
export class Configuracoes {
  private msg!: HTMLElement;
  private logon!: HTMLInputElement;
  private logonGuardado = false;
  private atalhos: Config["atalhos"];
  private falhas: FalhaAtalho[] = [];
  private modelos: AbaModelos | null = null;
  private sistema: AbaSistema | null = null;
  private reuniao: AbaReuniao | null = null;
  private avisos: AbaAvisos | null = null;
  private oficina: AbaOficina | null = null;
  private atualizacao: AbaAtualizacao | null = null;
  private diagnostico: AbaDiagnostico | null = null;
  private monitorRecursos: MonitorRecursos | null = null;
  private abaVoz!: AbaVoz;
  private abaPerfil!: AbaPerfil;
    private paineisMcps!: AbaPaineisMcps;
  private linhasAtalho = new Map<AcaoAtalho, { campo: HTMLButtonElement; motivo: HTMLElement }>();
  private ultimaConfigDisco: Config;

  constructor(private cfg: Config, private raiz: HTMLElement, private deps: DepsConfiguracoes) {
    this.atalhos = { ...cfg.atalhos };
    this.ultimaConfigDisco = structuredClone(cfg);
  }

  /** Desenha as abas e lê o que só o Rust sabe (início no logon, atalhos que não registraram). */
  async montar() {
    this.desenhar();
    this.abaVoz = new AbaVoz(this.raiz.querySelector<HTMLElement>("#cfg-voz")!, this.cfg, {
      criarOj: () => this.deps.criarOj(this.cfg.openjarvis_url),
      velocidade: () => { const n = Number(this.el("velocidade").value.trim().replace(",", ".")); return Number.isFinite(n) && n > 0 ? n : this.cfg.velocidade; },
      dizer: (t, ruim) => this.dizer(t, ruim),
    });
    this.abaVoz.montar();
    // Instalador de vozes opcionais (T5c): monta abaixo da aba Voz; sem pacotes, a seção fica vazia.
    const raizInstalador = this.raiz.querySelector<HTMLElement>("#cfg-instalador-vozes");
    if (raizInstalador) {
      const instalador = new InstaladorVozes(raizInstalador, {
        baseUrl: this.cfg.ponte_url.replace(/\/$/, ""),
        notificar: (msg, erro) => this.dizer(msg, erro),
        aoMudar: (id, instalado) => {
          if (id === "xtts-v2") this.abaVoz.definirPacoteXttsInstalado(instalado);
          return this.abaVoz.atualizar();
        },
      });
      const pronto = instalador.montar().then(() => this.abaVoz.definirPacoteXttsInstalado(instalador.estaInstalado("xtts-v2")));
      this.abaVoz.definirInstalador(async (id) => {
        await pronto;
        raizInstalador.scrollIntoView?.({ block: "nearest" });
        await instalador.instalar(id);
      });
    }
    this.marcarUrl("voz_url");
    this.modelos = new AbaModelos(this.raiz.querySelector<HTMLElement>("#cfg-modelos")!, {
      criarOj: (modelo) => this.deps.criarOj(this.cfg.openjarvis_url, modelo),
      statusPonte: () => this.deps.statusPonte(this.cfg.ponte_url),
      ponteUrl: this.cfg.ponte_url,
      config: this.cfg,
      aoMudarCerebro: (cerebro) => { this.cfg.cerebro = cerebro; void salvarConfig(this.cfg); },
      aoMudarUsoOpenJarvis: () => { this.deps.aoSalvar?.(this.cfg); },
    });
    void this.modelos.carregar();
    this.paineisMcps = new AbaPaineisMcps(this.raiz.querySelector<HTMLElement>("#cfg-paineis-mcps")!);
    this.abaPerfil = new AbaPerfil(this.raiz.querySelector<HTMLElement>("#cfg-perfil")!, {
      nome: () => this.cfg.nome,
      usuario: () => this.cfg.usuario,
      variantes: () => this.cfg.variantes,
      ler: () => lerPerfil(),
      gravar: (p) => gravarPerfil(p),
      previa: () => previaPersona(this.el("ponte_url").value, this.cfg.nome.trim(), this.cfg.usuario.trim()),
      aoMudar: (campo, valor) => {
        if (campo === "variantes") {
          this.cfg.variantes = valor.split(",").map((v) => v.trim()).filter(Boolean);
          if (this.cfg.variantes.length === 0) this.cfg.variantes = [this.cfg.nome];
        } else {
          (this.cfg as unknown as Record<string, unknown>)[campo] = valor;
        }
      },
    });
    await this.abaPerfil.montar();
    const urlPonte = () => this.el("ponte_url").value.trim(); // vazio = sem ponte (desliga), não "usar a salva"
    this.sistema = new AbaSistema(this.raiz.querySelector<HTMLElement>("#cfg-sistema")!, {
      statusPonte: () => this.deps.statusPonte(urlPonte()),
      modo: (v) => this.deps.modoPonte(urlPonte(), v),
    });
    this.sistema.montar();
    this.reuniao = new AbaReuniao(this.raiz.querySelector<HTMLElement>("#cfg-reuniao")!, {
      reuniaoStatus: () => this.deps.ponte(urlPonte()).reuniaoStatus(),
      iniciarReuniao: () => this.deps.ponte(urlPonte()).iniciarReuniao(),
      encerrarReuniao: () => this.deps.ponte(urlPonte()).encerrarReuniao(),
      listaReuniao: (n) => this.deps.ponte(urlPonte()).listaReuniao(n),
      gerarAta: (tipo, qual) => this.deps.ponte(urlPonte()).gerarAta(tipo, qual),
    });
    this.reuniao.montar();
    this.avisos = new AbaAvisos(this.raiz.querySelector<HTMLElement>("#cfg-avisos")!, {
      avisos: () => this.deps.ponte(urlPonte()).avisos(),
      marcarLidos: (ids) => this.deps.ponte(urlPonte()).marcarLidos(ids),
      resultadoTarefa: (n) => this.deps.ponte(urlPonte()).resultadoTarefa(n),
      eventos: (cb) => this.deps.ponte(urlPonte()).eventos(cb),
    });
    this.avisos.montar();
    this.oficina = new AbaOficina(this.raiz.querySelector<HTMLElement>("#cfg-oficina")!, {
      statusPonte: () => this.deps.statusPonte(urlPonte()),
      nome: () => this.cfg.nome,
      abrirAba: (aba) => this.abrirAba(aba),
    });
    this.oficina.montar();
    // Atualização embutida na aba Geral (sem aba própria no menu).
    const blocoAtualizacao = this.raiz.querySelector<HTMLElement>("#cfg-atualizacao-bloco");
    if (blocoAtualizacao) {
      this.atualizacao = new AbaAtualizacao(blocoAtualizacao, this.deps.atualizacao);
      this.atualizacao.montar();
      if (this.cfg.atualizacao_ao_abrir) this.atualizacao.aoAbrir();
    }
    this.montarAparencia();
    this.diagnostico = new AbaDiagnostico(this.raiz.querySelector<HTMLElement>("#cfg-diagnostico")!);
    this.diagnostico.montar();
    const recursosRaiz = this.raiz.querySelector<HTMLElement>("#cfg-recursos");
    if (recursosRaiz) {
      this.monitorRecursos = new MonitorRecursos(recursosRaiz, { urlNucleo: () => urlPonte() });
      this.monitorRecursos.montar();
    }
    this.abrirAba("geral");
    try { this.logonGuardado = await invoke<boolean>("inicio_no_logon_ativo"); } catch { this.logonGuardado = false; }
    this.logon.checked = this.logonGuardado;
    try { this.preencherMonitores(await invoke<MonitorInfo[]>("listar_monitores")); } catch { this.preencherMonitores([]); }
    try { this.falhas = await invoke<FalhaAtalho[]>("falhas_de_atalho"); } catch { this.falhas = []; }
    this.marcarAtalhos({});
    if (this.falhas.length) this.dizer("Há atalhos que o Windows não aceitou: veja a aba Atalhos.", true);
  }

  abrirAba(aba: Aba) {
    for (const s of this.raiz.querySelectorAll<HTMLElement>("section[data-aba]")) s.hidden = s.dataset.aba !== aba;
    for (const b of this.raiz.querySelectorAll<HTMLButtonElement>("nav button")) b.classList.toggle("ativa", b.dataset.aba === aba);
    // Atualiza título da seção ativa no topo da área de conteúdo
    const tituloEl = this.raiz.querySelector<HTMLElement>("#cfg-titulo-secao");
    if (tituloEl) {
      const mapaRotulo = new Map(ABAS);
      tituloEl.textContent = mapaRotulo.get(aba) ?? aba;
    }
    if (aba === "paineis-mcps") void this.paineisMcps?.montar();
    if (aba === "modelos") void this.modelos?.carregar(); // reconsulta o núcleo: o aviso e as instalações refletem o estado atual
    if (aba === "voz") {
      void this.abaVoz.atualizar();
    }
    if (aba === "perfil") {
      this.abaPerfil.definir("nome", this.cfg.nome);
      this.abaPerfil.definir("usuario", this.cfg.usuario);
      this.abaPerfil.definir("variantes", this.cfg.variantes.join(", "));
    }
    if (aba === "geral") this.monitorRecursos?.ativar(); else this.monitorRecursos?.desativar();
    if (aba === "sistema") this.sistema?.ativar(); else this.sistema?.desativar();
    if (aba === "reuniao") this.reuniao?.ativar(); else this.reuniao?.desativar();
    if (aba === "avisos") this.avisos?.ativar(); else this.avisos?.desativar();
    if (aba === "oficina") void this.oficina?.ativar(); else this.oficina?.desativar();
    if (aba === "geral" && this.cfg.atualizacao_ao_abrir) this.atualizacao?.aoAbrir();
  }

  /** O widget gravou topo ou compacto pelos próprios botões: acompanha sem perder o resto do formulário. */
  mudouNoWidget(c: Pick<Config, "sempre_no_topo" | "compacto">) {
    this.cfg.sempre_no_topo = c.sempre_no_topo;
    this.cfg.compacto = c.compacto;
    this.el("sempre_no_topo").checked = c.sempre_no_topo;
    this.el("compacto").checked = c.compacto;
  }

  /** A bandeja mudou "Sempre no topo": reflete no painel sem mexer no resto do formulário. */
  mudouTopo(ligado: boolean) {
    this.cfg.sempre_no_topo = ligado;
    this.el("sempre_no_topo").checked = ligado;
  }

  /** O widget mudou "não ouvir"/"não falar" (HUD, atalho ou bandeja): sem isto um Salvar gravaria os valores antigos. */
  mudouNaoOuvirFalar(c: Pick<Config, "nao_ouvir" | "nao_falar">) {
    this.cfg.nao_ouvir = c.nao_ouvir;
    this.cfg.nao_falar = c.nao_falar;
    this.el("nao_ouvir").checked = c.nao_ouvir;
    this.el("nao_falar").checked = c.nao_falar;
  }

  mudouInvisivel(ligado: boolean) {
    this.cfg.invisivel = ligado;
    this.el("invisivel").checked = ligado;
  }

  /** Aplica apenas valores que mudaram no disco, preservando os outros campos em edição. */
  mudouExternamente(novo: Config) {
    const mudou = Object.keys(novo).filter((k) => JSON.stringify(novo[k as keyof Config]) !== JSON.stringify(this.ultimaConfigDisco[k as keyof Config]));
    for (const chave of mudou) Object.assign(this.cfg, { [chave]: novo[chave as keyof Config] });
    this.ultimaConfigDisco = structuredClone(novo);
    for (const chave of mudou) {
      const id = chave === "cor_elementos" ? "cor-elementos" : chave === "opacidade_elementos" ? "opacidade-elementos" : chave;
      const campo = this.raiz.querySelector<HTMLInputElement | HTMLSelectElement>(`#cfg-${id}`);
      if (!campo) continue;
      const valor = novo[chave as keyof Config];
      if (campo instanceof HTMLInputElement && campo.type === "checkbox") campo.checked = valor === true;
      else if (typeof valor === "string" || typeof valor === "number") campo.value = String(valor || (chave === "cor_elementos" ? "#00f0ff" : valor));
    }
    if (mudou.includes("cor_elementos") || mudou.includes("opacidade_elementos")) {
      const preview = this.raiz.querySelector<HTMLElement>("#cfg-aparencia-preview");
      if (preview) { preview.style.color = novo.cor_elementos || "#00f0ff"; preview.style.borderColor = preview.style.color; preview.style.opacity = String(novo.opacidade_elementos); }
      const rotulo = this.raiz.querySelector<HTMLElement>("#cfg-opacidade-valor");
      if (rotulo) rotulo.textContent = `${Math.round(novo.opacidade_elementos * 100)}%`;
    }
    if (mudou.some((k) => k.startsWith("voz") || k.endsWith("_voz"))) void this.abaVoz?.atualizar();
    for (const campo of ["nome", "usuario", "variantes"] as const) if (mudou.includes(campo)) this.abaPerfil?.definir(campo, campo === "variantes" ? novo.variantes.join(", ") : novo[campo]);
    if (mudou.includes("atalhos")) { this.atalhos = { ...novo.atalhos }; this.marcarAtalhos({}); }
  }

  async paineisMudaram() {
    await this.modelos?.carregar();
    await this.abaVoz?.atualizar();
    await this.paineisMcps?.montar();
  }

  async habilidadesMudaram() { await this.oficina?.ativar(); }
  async perfilMudou() { await this.abaPerfil?.recarregar(); }

  private campo(id: string, rotulo: string, valor: string | number, tipo = "text", extra = ""): string {
    return `<label>${rotulo}<input id="cfg-${id}" type="${tipo}" value="${esc(String(valor))}" ${extra}></label>`;
  }
  private marca(id: string, rotulo: string, valor: boolean): string {
    return `<label class="marca"><input id="cfg-${id}" type="checkbox" ${valor ? "checked" : ""}> ${rotulo}</label>`;
  }
  private el(id: string): HTMLInputElement { return this.raiz.querySelector<HTMLInputElement>(`#cfg-${id}`)!; }
  private sel(id: string): HTMLSelectElement { return this.raiz.querySelector<HTMLSelectElement>(`#cfg-${id}`)!; }

  private desenhar() {
    const c = this.cfg;
    // Grupos do menu lateral (ordem visual)
    const GRUPOS: [string, Aba[]][] = [
      ["Conversa", ["geral", "perfil"]],
      ["Voz e áudio", ["voz", "atalhos"]],
      ["Cérebro", ["oficina", "modelos", "paineis-mcps"]],
            ["Sistema", ["sistema", "reuniao", "avisos", "diagnostico"]],
    ];
    const mapaRotulo = new Map(ABAS);
    const navHtml = GRUPOS.map(([titulo, ids]) =>
      `<div class="grupo-titulo">${titulo}</div>` +
      ids.map((id) => `<button type="button" data-aba="${id}">${mapaRotulo.get(id) ?? id}</button>`).join("")
    ).join("");

    this.raiz.innerHTML = `
      <nav>${navHtml}</nav>
      <div class="conteudo">
        <div id="cfg-titulo-secao" class="conteudo-titulo"></div>
        <section data-aba="geral">
          <fieldset><legend>OpenJarvis</legend>
            ${this.campo("openjarvis_url", "Endereço", c.openjarvis_url)}
            ${this.campo("gui_url", "Interface de texto", c.gui_url)}
            <button id="cfg-testar" type="button">Testar</button>
          </fieldset>
          <fieldset><legend>Idioma</legend>
            ${campoIdioma(c.idioma)}
          </fieldset>
          <fieldset><legend>Aparência</legend>
            <label>Cor dos elementos</label>
            <div class="aparencia-linha">
              <div class="aparencia-cores" id="cfg-aparencia-cores"></div>
              <div class="aparencia-personalizada">
                <label for="cfg-cor-elementos">Personalizada</label>
                <input id="cfg-cor-elementos" type="color" value="${esc(c.cor_elementos || "#00f0ff")}" title="Cor personalizada">
              </div>
              <div class="aparencia-preview" id="cfg-aparencia-preview">Prévia</div>
            </div>
            <label>Opacidade dos elementos</label>
            <div class="aparencia-slider">
              <input id="cfg-opacidade-elementos" type="range" min="0.2" max="1" step="0.05" value="${c.opacidade_elementos}">
              <span id="cfg-opacidade-valor">${Math.round(c.opacidade_elementos * 100)}%</span>
            </div>
          </fieldset>
          <fieldset id="cfg-janela"><legend>Janela</legend>
            <label>Tamanho do widget<select id="cfg-tamanho">${OPCOES_TAMANHO.map(([v, r]) => `<option value="${v}" ${v === c.tamanho ? "selected" : ""}>${r}</option>`).join("")}</select></label>
            ${this.campo("tamanho_px", "Lado em px (personalizado, 160 a 800)", c.tamanho_px, "number", 'step="10" min="160" max="800"')}
            ${this.marca("compacto", "Compacto (só o holograma)", c.compacto)}
            ${this.marca("sempre_no_topo", "Sempre no topo", c.sempre_no_topo)}
            ${this.marca("click_through", "Clique atravessa a janela", c.click_through)}
            ${this.marca("invisivel", "Modo invisível (aparece só durante a conversa)", c.invisivel)}
            ${this.marca("logon", "Iniciar com o Windows", false)}
            <label>Monitor da tela cheia<select id="cfg-sala_monitor"></select></label>
          </fieldset>
          <fieldset><legend>Ouvir e falar</legend>
            ${this.marca("nao_ouvir", "Não ouvir (microfone desligado)", c.nao_ouvir)}
            ${this.marca("nao_falar", "Não falar (resposta só em texto)", c.nao_falar)}
            ${this.marca("falar_avisos", "Falar os avisos de tarefas (desligado por padrão)", c.falar_avisos)}
          </fieldset>
          <fieldset><legend>Assistente</legend>
            <button id="cfg-primeiro-uso" type="button">Configurar primeiro uso</button>
          </fieldset>
          <fieldset><legend>Atualização</legend>
            <div id="cfg-atualizacao-bloco"></div>
            ${this.marca("atualizacao_ao_abrir", "Verificar ao abrir as Configurações", c.atualizacao_ao_abrir)}
            <p class="nota">A consulta vai ao GitHub (api.github.com) só quando você clica em Verificar ou marca esta caixa.</p>
          </fieldset>
          <div id="cfg-recursos"></div>
        </section>
        <section data-aba="perfil"><div id="cfg-perfil"></div></section>
        <section data-aba="paineis-mcps"><div id="cfg-paineis-mcps"></div></section>
        <section data-aba="voz">
          <div id="cfg-voz">
          <fieldset><legend>Fala</legend>
            ${this.campo("velocidade", "Velocidade da fala", c.velocidade, "number", 'step="0.05" min="0.5" max="2"')}
            ${this.campo("instrucao_formato", "Instrução de formato", c.instrucao_formato)}
          </fieldset>
          <fieldset><legend>Ouvido</legend>
            ${this.campo("finish_ms", "Silêncio para encerrar a fala (ms)", c.finish_ms, "number", 'step="50" min="200" max="3000"')}
            ${this.campo("limiar_vad", "Limiar do microfone", c.limiar_vad, "number", 'step="0.005" min="0.001" max="0.5"')}
            ${this.campo("conversa_s", "Modo conversa: segundos ouvindo sem o nome depois de uma resposta (0 desliga)", c.conversa_ms / 1000, "number", 'step="1" min="0" max="300"')}
          </fieldset>
          </div>
          <div id="cfg-instalador-vozes"></div>
        </section>
        <section data-aba="atalhos">
          <p class="nota">Clique num atalho e pressione a nova combinação (Ctrl, Alt ou Win mais uma tecla). Esc cancela. Valem depois de reiniciar o Vard.</p>
          <div id="cfg-atalhos"></div>
        </section>
        <section data-aba="sistema">
          ${this.campo("ponte_url", "Ponte do Vard (opcional; vazio desliga)", c.ponte_url)}
          <div id="cfg-sistema"></div>
          <div id="cfg-importacao"></div>
        </section>
        <section data-aba="reuniao"><div id="cfg-reuniao"></div></section>
        <section data-aba="oficina"><div id="cfg-oficina"></div></section>
        <section data-aba="avisos"><div id="cfg-avisos"></div></section>
                <section data-aba="modelos" id="cfg-modelos"></section>
        <section data-aba="diagnostico"><div id="cfg-diagnostico"></div></section>
      </div>
      <footer>
        <div id="cfg-msg" role="status"></div>
        <div class="acoes"><button id="cfg-salvar" type="button">Salvar</button><button id="cfg-fechar" type="button">Fechar</button></div>
      </footer>`;
    this.msg = this.raiz.querySelector<HTMLElement>("#cfg-msg")!;
    this.logon = this.el("logon");
    for (const b of this.raiz.querySelectorAll<HTMLButtonElement>("nav button")) b.addEventListener("click", () => this.abrirAba(b.dataset.aba as Aba));
    this.raiz.querySelector("#cfg-fechar")!.addEventListener("click", () => this.deps.fechar?.());
    this.raiz.querySelector("#cfg-salvar")!.addEventListener("click", () => { void this.salvar(); });
    this.raiz.querySelector("#cfg-testar")!.addEventListener("click", () => { void this.testar(); });
    this.raiz.querySelector("#cfg-primeiro-uso")?.addEventListener("click", () => {
      void emitTo("main", "reabrir-primeiro-uso").catch(() => {});
    });
    this.montarAtalhos(this.raiz.querySelector<HTMLElement>("#cfg-atalhos")!);
    for (const id of ["openjarvis_url", "gui_url", "ponte_url"]) this.marcarUrl(id);
  }

  /** Marca em aviso o campo de endereço que não é local; nos opcionais (ponte, voz) vazio desliga e não é aviso. */
  private marcarUrl(id: string) {
    const campo = this.el(id);
    const opcional = id === "ponte_url" || id === "voz_url";
    const marcar = () => campo.classList.toggle("aviso", !(opcional && campo.value.trim() === "") && !urlLocal(campo.value.trim()));
    campo.addEventListener("input", marcar); marcar();
  }

  private montarAtalhos(caixa: HTMLElement) {
    this.linhasAtalho.clear();
    for (const acao of ACOES_ATALHO) {
      const linha = document.createElement("div");
      linha.className = "linha-atalho";
      const rotulo = document.createElement("span");
      rotulo.textContent = ROTULOS_ATALHO[acao];
      const campo = campoAtalho(this.atalhos[acao], (nova) => { this.atalhos[acao] = nova; this.marcarAtalhos(validarAtalhos(this.atalhos)); });
      const motivo = document.createElement("small");
      motivo.className = "motivo";
      linha.append(rotulo, campo, motivo);
      caixa.append(linha);
      this.linhasAtalho.set(acao, { campo, motivo });
    }
  }

  /** Marca cada campo com o erro de validação ou com a falha de registro do arranque (enquanto a combinação for a mesma). */
  private marcarAtalhos(erros: Partial<Record<AcaoAtalho, string>>) {
    for (const [acao, { campo, motivo }] of this.linhasAtalho) {
      const falha = this.falhas.find((f) => f.chave === acao && f.combinacao === this.atalhos[acao]);
      const texto = erros[acao] ?? (falha ? `Não registrou no Windows: ${falha.erro}. Outro programa pode estar usando; troque e reinicie.` : "");
      const altgr = texto === "" ? avisoAltGr(this.atalhos[acao]) : null;
      campo.classList.toggle("aviso", texto !== "" || altgr !== null);
      motivo.textContent = texto || altgr || "";
    }
  }


  /** "Principal" mais os monitores conectados; um escolhido que sumiu continua na lista, marcado, para não se perder. */
  private preencherMonitores(lista: MonitorInfo[]) {
    const sel = this.sel("sala_monitor");
    const atual = this.cfg.sala_monitor;
    const opcoes: [string, string][] = [
      ["", "Principal"],
      ...lista.map((m, i): [string, string] => [m.nome, `Monitor ${i + 1}: ${m.largura}x${m.altura}${m.principal ? " (principal)" : ""}`]),
    ];
    if (atual && !lista.some((m) => m.nome === atual)) opcoes.push([atual, "Desconectado (a sala abre no principal)"]);
    sel.replaceChildren(...opcoes.map(([valor, rotulo]) => new Option(rotulo, valor, false, valor === atual)));
  }

  private dizer(t: string, ruim = false) { this.msg.textContent = t; this.msg.classList.toggle("ruim", ruim); }

  /** Cores prontas para a seção Aparência (bolinhas). */
  private static CORES_PRONTAS: [string, string][] = [
    ["#00f0ff", "Ciano"], ["#00a2ff", "Azul"], ["#a855f7", "Roxo"], ["#22c55e", "Verde"],
    ["#f59e0b", "Âmbar"], ["#ef4444", "Vermelho"], ["#ec4899", "Rosa"], ["#ffffff", "Branco"],
  ];

  /** Monta as bolinhas de cor, o input personalizado, o slider de opacidade e a prévia; aplica ao vivo no preview. */
  private montarAparencia() {
    const caixaCores = this.raiz.querySelector<HTMLElement>("#cfg-aparencia-cores");
    const inputCor = this.raiz.querySelector<HTMLInputElement>("#cfg-cor-elementos");
    const sliderOpacidade = this.raiz.querySelector<HTMLInputElement>("#cfg-opacidade-elementos");
    const labelOpacidade = this.raiz.querySelector<HTMLElement>("#cfg-opacidade-valor");
    const preview = this.raiz.querySelector<HTMLElement>("#cfg-aparencia-preview");
    if (!caixaCores || !inputCor || !sliderOpacidade || !labelOpacidade || !preview) return;

    const aplicarPreview = () => {
      const cor = inputCor.value || "#00f0ff";
      const op = Number(sliderOpacidade.value) || 1;
      preview.style.color = cor;
      preview.style.borderColor = cor;
      preview.style.opacity = String(op);
      for (const btn of caixaCores.querySelectorAll<HTMLButtonElement>(".aparencia-cor")) {
        btn.classList.toggle("ativa", btn.dataset.cor === cor);
      }
      inputCor.closest(".aparencia-personalizada")?.classList.toggle("ativa",
        !Configuracoes.CORES_PRONTAS.some(([hex]) => hex === cor));
    };

    caixaCores.replaceChildren();
    for (const [hex, titulo] of Configuracoes.CORES_PRONTAS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "aparencia-cor";
      btn.dataset.cor = hex;
      btn.style.background = hex;
      btn.title = titulo;
      btn.setAttribute("aria-label", titulo);
      btn.addEventListener("click", () => { inputCor.value = hex; aplicarPreview(); });
      caixaCores.append(btn);
    }

    inputCor.addEventListener("input", aplicarPreview);
    sliderOpacidade.addEventListener("input", () => {
      labelOpacidade.textContent = `${Math.round(Number(sliderOpacidade.value) * 100)}%`;
      aplicarPreview();
    });
    aplicarPreview();
  }

  /** Lê o formulário; números inválidos e textos obrigatórios vazios mantêm o valor atual. */
  lerFormulario(): Config {
    const num = (id: string, atual: number) => {
      const bruto = this.el(id).value.trim().replace(",", ".");
      const n = Number(bruto);
      return bruto !== "" && Number.isFinite(n) ? n : atual;
    };
    const txt = (id: string, atual: string) => this.el(id).value.trim() || atual;
    const opc = (id: string) => this.el(id).value.trim(); // vazio é valor válido (desliga, tira o nome, idioma automático)
    const c = this.cfg;
    const cor = this.el("cor-elementos")?.value || c.cor_elementos;
    return {
      ...c,
      openjarvis_url: txt("openjarvis_url", c.openjarvis_url), gui_url: txt("gui_url", c.gui_url), ponte_url: opc("ponte_url"),
      ...this.abaVoz.ler(), voz_url: this.abaVoz.vozUrl(),
      nome: c.nome, usuario: c.usuario, variantes: c.variantes,
      idioma: this.sel("idioma").value,
      velocidade: num("velocidade", c.velocidade), finish_ms: num("finish_ms", c.finish_ms), limiar_vad: num("limiar_vad", c.limiar_vad),
      conversa_ms: Math.round(Math.max(0, num("conversa_s", c.conversa_ms / 1000)) * 1000),
      instrucao_formato: txt("instrucao_formato", c.instrucao_formato),
      tamanho: this.sel("tamanho").value as Config["tamanho"], tamanho_px: limitarLado(num("tamanho_px", c.tamanho_px)),
      compacto: this.el("compacto").checked,
      sempre_no_topo: this.el("sempre_no_topo").checked, click_through: this.el("click_through").checked, invisivel: this.el("invisivel").checked,
      atualizacao_ao_abrir: this.el("atualizacao_ao_abrir").checked,
      nao_ouvir: this.el("nao_ouvir").checked,
      nao_falar: this.el("nao_falar").checked,
      falar_avisos: this.el("falar_avisos").checked,
      atalhos: { ...this.atalhos },
      modelo: c.modelo,
      sala_monitor: this.sel("sala_monitor").options.length ? this.sel("sala_monitor").value : c.sala_monitor, // lista ainda não chegou: mantém
      cor_elementos: !c.cor_elementos && cor === "#00f0ff" ? "" : cor,
      opacidade_elementos: Number(this.el("opacidade-elementos")?.value) || c.opacidade_elementos,
    };
  }

  private async salvar() {
    const erroVoz = this.abaVoz.erro();
    if (erroVoz) { this.abrirAba("voz"); this.dizer(erroVoz, true); return; }
    const novo = this.lerFormulario();
    if (novo.variantes.length === 0) novo.variantes = [novo.nome];
    const erros = validarAtalhos(novo.atalhos);
    for (const acao of ACOES_ATALHO) {
      if (erros[acao]) continue;
      try { await invoke("validar_atalho", { combinacao: novo.atalhos[acao] }); }
      catch (e) { erros[acao] = `O Windows não aceita essa combinação (${String(e)}).`; }
    }
    this.marcarAtalhos(erros);
    if (Object.keys(erros).length) { this.abrirAba("atalhos"); this.dizer("Corrija os atalhos marcados antes de salvar.", true); return; }
    const reiniciar = mudancasQueExigemReinicio(this.cfg, novo);
    try { await salvarConfig(novo); }
    catch (erro) { this.dizer(`Não consegui salvar: ${String(erro)}`, true); return; }
    Object.assign(this.cfg, novo);
    this.ultimaConfigDisco = structuredClone(novo);
    // O perfil do agente é outro arquivo: falha aqui não desfaz o config.json salvo.
    let erroPerfil = "";
    try { await this.abaPerfil.gravar(); }
    catch (erro) { erroPerfil = erro instanceof Error ? erro.message : String(erro); }
    // O atalho de início só é mexido quando a caixa mudou (evita regravar o .lnk a cada Salvar).
    let falhouLogon = false;
    if (this.logon.checked !== this.logonGuardado) {
      try { await invoke("definir_inicio_no_logon", { ligado: this.logon.checked }); this.logonGuardado = this.logon.checked; }
      catch { falhouLogon = true; this.logon.checked = this.logonGuardado; }
    }
    this.deps.aoSalvar?.(this.cfg);
    const avisos = avisosDeUrl(novo);
    const partes = [falhouLogon ? "Configuração salva, mas não consegui criar o atalho de início." : "Salvo; tamanho, janela e usuário já valem no widget."];
    if (erroPerfil) partes.push(`O perfil do agente não foi gravado: ${erroPerfil}.`);
    if (reiniciar.length) partes.push(`Reinicie o Vard para aplicar: ${reiniciar.join(", ")}.`);
    if (avisos.length) partes.push(`Atenção: ${avisos.join("; ")}.`);
    this.dizer(partes.join(" "), avisos.length > 0 || falhouLogon || erroPerfil !== "");
  }

  private async testar() {
    const url = this.el("openjarvis_url").value.trim();
    this.dizer("Testando...");
    try {
      const oj = this.deps.criarOj(url);
      if (!(await oj.saude())) { this.dizer("OpenJarvis não respondeu nesse endereço.", true); return; }
      if (!(await oj.fala())) { this.dizer("OpenJarvis no ar, mas a fala está desligada. Veja docs/ligar-a-fala.md.", true); return; }
      this.dizer("OpenJarvis no ar e a fala está ligada.");
    } catch (erro) { this.dizer(`Falha no teste: ${String(erro)}`, true); }
  }
}
