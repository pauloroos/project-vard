import type { StatusPonte } from "../conectores/ponte/cliente";
import { habilidadesFabrica, padraoFabrica, type HabilidadeFabrica } from "../config/habilidades-fabrica";
import { lerHabilidades, gravarHabilidades, HABILIDADES_PADRAO, LIMITES_HABILIDADES, validarHabilidades, type AjusteFabrica, type Habilidade, type HabilidadesConfig } from "../config/habilidades";
import { abrirModal, campoModal, desenharCards, type Card } from "./componentes";

export interface DepsAbaOficina {
  statusPonte: () => Promise<StatusPonte | null>;
  nome: () => string;
  ler?: () => Promise<HabilidadesConfig>;
  gravar?: (valor: HabilidadesConfig) => Promise<void>;
  abrirAba?: (aba: "modelos") => void;
}
const ROTULOS = { capaz: "Capaz", treinada: "Treinada", validada: "Validada" };
type Item = HabilidadeFabrica | Habilidade;
const deFabrica = (h: Item): h is HabilidadeFabrica => h.situacao === "capaz";

/**
 * Receitas do usuário e capacidades de fábrica. Salva cada ação sem depender do botão Geral.
 * Receitas: editar, ligar/desligar, validar e excluir. Fábrica: editar (ajuste em "fabrica"), ligar/desligar
 * e restaurar o padrão; não se exclui, porque mora no código.
 */
export class AbaOficina {
  private cfg = structuredClone(HABILIDADES_PADRAO);
  private itens: Item[] = [];
  private lista!: HTMLElement;
  private aviso!: HTMLElement;
  private busca!: HTMLInputElement;
  private filtro!: HTMLSelectElement;
  private nova!: HTMLButtonElement;
  private carregada = false;
  private ocupada = false;
  private ponteNoAr = false;
  private temProvedorProprio = false;
  private revisao = 0;
  private fecharModal: (() => void) | null = null;

  constructor(private raiz: HTMLElement, private deps: DepsAbaOficina) {}

  montar() {
    this.raiz.innerHTML = "";
    const ajuda = document.createElement("p");
    ajuda.textContent = "Ensine até 200 receitas para o assistente cumprir com as ferramentas disponíveis. Capaz vem de fábrica; Treinada foi cadastrada; Validada já deu certo. As alterações são salvas a cada ação.";
    const topo = document.createElement("div"); topo.className = "oficina-filtros";
    this.busca = document.createElement("input"); this.busca.type = "search"; this.busca.className = "cards-busca"; this.busca.placeholder = "Buscar habilidades…"; this.busca.setAttribute("aria-label", "Buscar habilidades");
    this.filtro = document.createElement("select"); this.filtro.setAttribute("aria-label", "Situação");
    for (const [valor, rotulo] of [["", "Todas as situações"], ...Object.entries(ROTULOS)]) {
      const op = document.createElement("option"); op.value = valor; op.textContent = rotulo; this.filtro.append(op);
    }
    this.nova = document.createElement("button"); this.nova.type = "button"; this.nova.className = "primaria"; this.nova.textContent = "Nova habilidade";
    this.nova.addEventListener("click", () => this.editar());
    this.aviso = document.createElement("p"); this.aviso.setAttribute("role", "status");
    this.lista = document.createElement("div"); this.lista.id = "oficina-habilidades";
    topo.append(this.busca, this.filtro, this.nova); this.raiz.append(ajuda, topo, this.aviso, this.lista);
    this.busca.addEventListener("input", () => this.filtrar()); this.filtro.addEventListener("change", () => this.filtrar());
    this.desenhar();
  }

  async ativar() {
    const revisao = ++this.revisao;
    try {
      const [cfg, st] = await Promise.all([(this.deps.ler ?? lerHabilidades)(), this.deps.statusPonte().catch(() => null)]);
      if (revisao !== this.revisao) return;
      this.cfg = validarHabilidades(cfg); this.carregada = true; this.ponteNoAr = st !== null;
      this.temProvedorProprio = st?.cerebro_proprio === true;
      this.aviso.textContent = "";
    } catch (e) {
      if (revisao !== this.revisao) return;
      this.carregada = false; this.aviso.textContent = `Não foi possível ler a Oficina: ${this.mensagem(e)}`;
    }
    this.desenhar();
  }
  desativar() { this.revisao++; this.fecharModal?.(); }

  private mensagem(e: unknown): string { return e instanceof Error ? e.message : String(e); }
  private bloqueada() { return !this.carregada || this.ocupada; }
  private async salvar(proximo: HabilidadesConfig) {
    if (this.bloqueada()) throw new Error("Aguarde a leitura ou gravação das habilidades");
    this.ocupada = true; this.desabilitar();
    try {
      const cfg = validarHabilidades(proximo);
      await (this.deps.gravar ?? gravarHabilidades)(cfg);
      this.cfg = cfg; this.aviso.textContent = "Habilidades salvas.";
    } finally { this.ocupada = false; this.desenhar(); }
  }
  private executar(acao: () => Promise<void>) { void acao().catch((e) => { this.aviso.textContent = this.mensagem(e); }); }
  private async alterar(id: string, alterar: (h: Habilidade) => void) {
    const proximo = structuredClone(this.cfg);
    const h = proximo.habilidades.find((h) => h.id === id);
    if (!h) throw new Error("Habilidade não encontrada");
    alterar(h); await this.salvar(proximo);
  }
  private desenhar() {
    const fabrica = habilidadesFabrica(this.deps.nome(), this.ponteNoAr, this.cfg.desligadas, this.temProvedorProprio, this.cfg.fabrica);
    this.itens = [...fabrica, ...this.cfg.habilidades];
    const cards: Card[] = this.itens.map((h) => ({
      id: h.id, titulo: h.nome, etiqueta: deFabrica(h) ? h.etiqueta ?? undefined : undefined,
      selos: [{ texto: ROTULOS[h.situacao], tom: h.situacao === "validada" ? "ok" : "neutro" }, { texto: h.ligada ? "Ligada" : "Desligada", tom: h.ligada ? "ativo" : "neutro" },
        ...(deFabrica(h) && h.personalizada ? [{ texto: "Personalizada", tom: "neutro" as const }] : [])],
      detalhes: h.quando,
      acoes: [
        ...(deFabrica(h) && h.etiqueta === "precisa de um agente configurado" && this.deps.abrirAba
          ? [{ rotulo: "Configurar", primaria: true, aoClicar: () => this.deps.abrirAba!("modelos") }]
          : []),
        { rotulo: h.ligada ? "Desligar" : "Ligar", aoClicar: () => this.executar(async () => {
          if (deFabrica(h)) {
            const proximo = structuredClone(this.cfg);
            proximo.desligadas = h.ligada ? [...proximo.desligadas, h.id] : proximo.desligadas.filter((id) => id !== h.id);
            await this.salvar(proximo);
          } else await this.alterar(h.id, (item) => { item.ligada = !item.ligada; });
        }) },
        { rotulo: "Editar", aoClicar: () => deFabrica(h) ? this.editarFabrica(h) : this.editar(h) },
        ...(deFabrica(h)
          ? (h.personalizada ? [{ rotulo: "Restaurar padrão", aoClicar: () => this.restaurar(h) }] : [])
          : [
            ...(h.situacao === "validada" ? [] : [{ rotulo: "Marcar como validada", aoClicar: () => this.executar(() => this.alterar(h.id, (item) => { item.situacao = "validada"; item.validada_em = new Date().toISOString(); })) }]),
            { rotulo: "Excluir", perigo: true, aoClicar: () => this.excluir(h) },
          ]),
      ],
    }));
    desenharCards(this.lista, cards, { vazio: "Nenhuma habilidade cadastrada.", buscaAPartirDe: Infinity });
    this.filtrar(); this.desabilitar();
  }
  private desabilitar() { for (const b of this.raiz.querySelectorAll<HTMLButtonElement>("button")) b.disabled = this.bloqueada(); }
  private filtrar() {
    const busca = this.busca.value.trim().toLocaleLowerCase("pt-BR");
    for (const el of this.lista.querySelectorAll<HTMLElement>("article")) {
      const h = this.itens.find((h) => h.id === el.dataset.id)!;
      const texto = `${h.nome} ${h.quando.join(" ")} ${h.instrucoes}`.toLocaleLowerCase("pt-BR");
      el.hidden = (!!busca && !texto.includes(busca)) || (!!this.filtro.value && h.situacao !== this.filtro.value);
    }
  }
  /** Mesmo formulário para receitas e fábrica; fábrica não escolhe situação e tem "O que fazer" opcional. */
  private formulario(valores: { nome: string; frases: string[]; instrucoes: string; ligada: boolean }, fabrica: boolean) {
    const corpo = document.createElement("div"); corpo.className = "oficina-formulario";
    const nome = document.createElement("input"); nome.value = valores.nome;
    const quando = document.createElement("textarea"); quando.rows = 3; quando.value = valores.frases.join("\n");
    const instrucoes = document.createElement("textarea"); instrucoes.rows = 6; instrucoes.value = valores.instrucoes;
    nome.maxLength = LIMITES_HABILIDADES.nome;
    quando.maxLength = LIMITES_HABILIDADES.frases * LIMITES_HABILIDADES.frase + LIMITES_HABILIDADES.frases - 1;
    instrucoes.maxLength = LIMITES_HABILIDADES.instrucoes;
    const contador = document.createElement("p"); contador.setAttribute("role", "status");
    const contar = () => { contador.textContent = `${instrucoes.value.length}/${LIMITES_HABILIDADES.instrucoes} caracteres`; };
    instrucoes.addEventListener("input", contar); contar();
    const ligada = document.createElement("input"); ligada.type = "checkbox"; ligada.checked = valores.ligada;
    corpo.append(campoModal("Nome", nome, "Até 80 caracteres."),
      campoModal("Quando usar (uma frase por linha)", quando, fabrica ? "Até 10 frases de até 200 caracteres cada, sem o nome do assistente: ele entra sozinho." : "Até 10 frases de até 200 caracteres cada."),
      campoModal("O que fazer", instrucoes, fabrica ? "Opcional: orientações extras para esta capacidade de fábrica. Até 4000 caracteres." : "Instruções em português, passo a passo. Até 4000 caracteres."),
      contador, campoModal("Ligada", ligada));
    const frases = () => quando.value.split("\n").map((v) => v.trim()).filter(Boolean);
    return { corpo, nome, instrucoes, ligada, frases };
  }
  private editar(h?: Habilidade) {
    if (this.bloqueada()) return;
    const { corpo, nome, instrucoes, ligada, frases } = this.formulario({ nome: h?.nome ?? "", frases: h?.quando ?? [], instrucoes: h?.instrucoes ?? "", ligada: h?.ligada ?? true }, false);
    const situacao = document.createElement("select");
    for (const [valor, rotulo] of [["treinada", "Treinada"], ["validada", "Validada"]]) {
      const op = document.createElement("option"); op.value = valor; op.textContent = rotulo; situacao.append(op);
    }
    situacao.value = h?.situacao ?? "treinada";
    corpo.append(campoModal("Situação", situacao));
    const modal = abrirModal({ titulo: h ? "Editar habilidade" : "Nova habilidade", corpo, aoFechar: () => { this.fecharModal = null; }, acoes: [
      { rotulo: "Cancelar" },
      { rotulo: "Salvar", primaria: true, aoClicar: async () => {
        const data = new Date().toISOString();
        const item: Habilidade = { ...h, id: h?.id ?? `habilidade-${crypto.randomUUID()}`, nome: nome.value.trim(), quando: frases(), instrucoes: instrucoes.value.trim(), ligada: ligada.checked, situacao: situacao.value as Habilidade["situacao"], criada_em: h?.criada_em ?? data, validada_em: situacao.value === "validada" ? h?.validada_em ?? data : null };
        const proximo = structuredClone(this.cfg);
        if (h) proximo.habilidades = proximo.habilidades.map((atual) => atual.id === h.id ? item : atual);
        else proximo.habilidades.push(item);
        await this.salvar(proximo);
      } },
    ] });
    this.fecharModal = modal.fechar;
  }
  /** Grava só o que difere da fábrica (campos desconhecidos do ajuste ficam); sem diferença, a entrada sai. */
  private editarFabrica(h: HabilidadeFabrica) {
    if (this.bloqueada()) return;
    const { corpo, nome, instrucoes, ligada, frases } = this.formulario(h, true);
    const modal = abrirModal({ titulo: "Editar habilidade", corpo, aoFechar: () => { this.fecharModal = null; }, acoes: [
      { rotulo: "Cancelar" },
      { rotulo: "Salvar", primaria: true, aoClicar: async () => {
        const padrao = padraoFabrica(h.id);
        const proximo = structuredClone(this.cfg);
        const ajuste: AjusteFabrica = { ...proximo.fabrica?.[h.id] };
        const n = nome.value.trim(), q = frases(), i = instrucoes.value.trim();
        if (n === padrao.nome) delete ajuste.nome; else ajuste.nome = n;
        if (q.join("\n") === padrao.frases.join("\n")) delete ajuste.quando; else ajuste.quando = q;
        if (i) ajuste.instrucoes = i; else delete ajuste.instrucoes;
        this.trocarAjuste(proximo, h.id, Object.keys(ajuste).length ? ajuste : null);
        proximo.desligadas = proximo.desligadas.filter((id) => id !== h.id);
        if (!ligada.checked) proximo.desligadas.push(h.id);
        await this.salvar(proximo);
      } },
    ] });
    this.fecharModal = modal.fechar;
  }
  /** Põe ou tira o ajuste de uma capacidade; sem nenhum ajuste, "fabrica" some do arquivo. */
  private trocarAjuste(cfg: HabilidadesConfig, id: string, ajuste: AjusteFabrica | null) {
    const fabrica = { ...cfg.fabrica };
    if (ajuste) fabrica[id] = ajuste; else delete fabrica[id];
    if (Object.keys(fabrica).length) cfg.fabrica = fabrica; else delete cfg.fabrica;
  }
  private restaurar(h: HabilidadeFabrica) {
    if (this.bloqueada()) return;
    const corpo = document.createElement("p"); corpo.textContent = `Restaurar o padrão de “${h.nome}”? Nome, frases e orientações voltam aos de fábrica; ligada ou desligada continua como está.`;
    const modal = abrirModal({ titulo: "Restaurar padrão", corpo, aoFechar: () => { this.fecharModal = null; }, acoes: [
      { rotulo: "Cancelar" }, { rotulo: "Restaurar padrão", primaria: true, aoClicar: async () => {
        const proximo = structuredClone(this.cfg); this.trocarAjuste(proximo, h.id, null); await this.salvar(proximo);
      } },
    ] });
    this.fecharModal = modal.fechar;
  }
  private excluir(h: Habilidade) {
    if (this.bloqueada()) return;
    const corpo = document.createElement("p"); corpo.textContent = `Excluir a habilidade “${h.nome}”? Esta receita será removida.`;
    const modal = abrirModal({ titulo: "Excluir habilidade", corpo, aoFechar: () => { this.fecharModal = null; }, acoes: [
      { rotulo: "Cancelar" }, { rotulo: "Excluir habilidade", primaria: true, aoClicar: async () => {
        const proximo = structuredClone(this.cfg); proximo.habilidades = proximo.habilidades.filter((item) => item.id !== h.id); await this.salvar(proximo);
      } },
    ] });
    this.fecharModal = modal.fechar;
  }
}
