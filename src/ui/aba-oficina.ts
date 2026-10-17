import type { StatusPonte } from "../conectores/ponte/cliente";
import { habilidadesFabrica } from "../config/habilidades-fabrica";
import { lerHabilidades, gravarHabilidades, HABILIDADES_PADRAO, LIMITES_HABILIDADES, validarHabilidades, type Habilidade, type HabilidadesConfig } from "../config/habilidades";
import { abrirModal, campoModal, desenharCards, type Card } from "./componentes";

export interface DepsAbaOficina {
  statusPonte: () => Promise<StatusPonte | null>;
  nome: () => string;
  ler?: () => Promise<HabilidadesConfig>;
  gravar?: (valor: HabilidadesConfig) => Promise<void>;
}
const ROTULOS = { capaz: "Capaz", treinada: "Treinada", validada: "Validada" };

/** Receitas do usuário e capacidades de fábrica. Salva cada ação sem depender do botão Geral. */
export class AbaOficina {
  private cfg = structuredClone(HABILIDADES_PADRAO);
  private lista!: HTMLElement;
  private aviso!: HTMLElement;
  private busca!: HTMLInputElement;
  private filtro!: HTMLSelectElement;
  private nova!: HTMLButtonElement;
  private carregada = false;
  private ocupada = false;
  private ponteNoAr = false;
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
    const fabrica = habilidadesFabrica(this.deps.nome(), this.ponteNoAr, this.cfg.desligadas);
    const cards: Card[] = [...fabrica, ...this.cfg.habilidades].map((h) => ({
      id: h.id, titulo: h.nome, etiqueta: h.situacao === "capaz" ? h.etiqueta ?? undefined : undefined,
      selos: [{ texto: ROTULOS[h.situacao], tom: h.situacao === "validada" ? "ok" : "neutro" }, { texto: h.ligada ? "Ligada" : "Desligada", tom: h.ligada ? "ativo" : "neutro" }],
      detalhes: h.quando,
      acoes: [
        { rotulo: h.ligada ? "Desligar" : "Ligar", aoClicar: () => this.executar(async () => {
          if (h.situacao === "capaz") {
            const proximo = structuredClone(this.cfg);
            proximo.desligadas = h.ligada ? [...proximo.desligadas, h.id] : proximo.desligadas.filter((id) => id !== h.id);
            await this.salvar(proximo);
          } else await this.alterar(h.id, (item) => { item.ligada = !item.ligada; });
        }) },
        ...(h.situacao === "capaz" ? [] : [
          { rotulo: "Editar", aoClicar: () => this.editar(h) },
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
    const habilidades = [...habilidadesFabrica(this.deps.nome(), this.ponteNoAr, this.cfg.desligadas), ...this.cfg.habilidades];
    for (const el of this.lista.querySelectorAll<HTMLElement>("article")) {
      const h = habilidades.find((h) => h.id === el.dataset.id)!;
      const texto = `${h.nome} ${h.quando.join(" ")} ${"instrucoes" in h ? h.instrucoes : ""}`.toLocaleLowerCase("pt-BR");
      el.hidden = (!!busca && !texto.includes(busca)) || (!!this.filtro.value && h.situacao !== this.filtro.value);
    }
  }
  private editar(h?: Habilidade) {
    if (this.bloqueada()) return;
    const corpo = document.createElement("div"); corpo.className = "oficina-formulario";
    const nome = document.createElement("input"); nome.value = h?.nome ?? "";
    const quando = document.createElement("textarea"); quando.rows = 3; quando.value = h?.quando.join("\n") ?? "";
    const instrucoes = document.createElement("textarea"); instrucoes.rows = 6; instrucoes.value = h?.instrucoes ?? "";
    nome.maxLength = LIMITES_HABILIDADES.nome;
    quando.maxLength = LIMITES_HABILIDADES.frases * LIMITES_HABILIDADES.frase + LIMITES_HABILIDADES.frases - 1;
    instrucoes.maxLength = LIMITES_HABILIDADES.instrucoes;
    const contador = document.createElement("p"); contador.setAttribute("role", "status");
    const contar = () => { contador.textContent = `${instrucoes.value.length}/${LIMITES_HABILIDADES.instrucoes} caracteres`; };
    instrucoes.addEventListener("input", contar); contar();
    const ligada = document.createElement("input"); ligada.type = "checkbox"; ligada.checked = h?.ligada ?? true;
    const situacao = document.createElement("select");
    for (const [valor, rotulo] of [["treinada", "Treinada"], ["validada", "Validada"]]) {
      const op = document.createElement("option"); op.value = valor; op.textContent = rotulo; situacao.append(op);
    }
    situacao.value = h?.situacao ?? "treinada";
    corpo.append(campoModal("Nome", nome, "Até 80 caracteres."), campoModal("Quando usar (uma frase por linha)", quando, "Até 10 frases de até 200 caracteres cada."), campoModal("O que fazer", instrucoes, "Instruções em português, passo a passo. Até 4000 caracteres."), contador, campoModal("Ligada", ligada), campoModal("Situação", situacao));
    const modal = abrirModal({ titulo: h ? "Editar habilidade" : "Nova habilidade", corpo, aoFechar: () => { this.fecharModal = null; }, acoes: [
      { rotulo: "Cancelar" },
      { rotulo: "Salvar", primaria: true, aoClicar: async () => {
        const data = new Date().toISOString();
        const item: Habilidade = { ...h, id: h?.id ?? `habilidade-${crypto.randomUUID()}`, nome: nome.value.trim(), quando: quando.value.split("\n").map((v) => v.trim()).filter(Boolean), instrucoes: instrucoes.value.trim(), ligada: ligada.checked, situacao: situacao.value as Habilidade["situacao"], criada_em: h?.criada_em ?? data, validada_em: situacao.value === "validada" ? h?.validada_em ?? data : null };
        const proximo = structuredClone(this.cfg);
        if (h) proximo.habilidades = proximo.habilidades.map((atual) => atual.id === h.id ? item : atual);
        else proximo.habilidades.push(item);
        await this.salvar(proximo);
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
