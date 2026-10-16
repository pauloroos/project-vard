/**
 * Componentes de tela compartilhados das Configurações (0.9.3): modal de cadastro e lista em cards.
 *
 * Regras do Paulo: cadastrar algo novo abre um MODAL (nada de formulário jogado para baixo); listas são
 * CARDS em blocos, pensando em muitos itens (com busca quando a lista cresce). Janela fixa de PC: o modal
 * tem tamanho máximo fixo e só o miolo rola, na vertical.
 */

export interface AcaoModal {
  rotulo: string;
  /** Botão principal (destacado). Enter dentro do modal aciona o principal. */
  primaria?: boolean;
  /** Devolve false para manter o modal aberto (ex.: validação falhou). */
  aoClicar?: () => boolean | void | Promise<boolean | void>;
}

export interface OpcoesModal {
  titulo: string;
  corpo: HTMLElement;
  /** Sem ações informadas: só "Fechar". */
  acoes?: AcaoModal[];
  /** Chamado sempre que o modal fecha (por ação, Esc ou clique fora). */
  aoFechar?: () => void;
}

export interface ModalAberto {
  fechar: () => void;
  /** Mensagem curta no rodapé do modal (erro de validação, resultado de teste). */
  avisar: (texto: string, ruim?: boolean) => void;
  elemento: HTMLElement;
}

/** Abre um modal sobre a janela. Esc ou clique no fundo fecham; o foco vai para o primeiro campo. */
export function abrirModal(op: OpcoesModal, raiz: HTMLElement = document.body): ModalAberto {
  const fundo = document.createElement("div");
  fundo.className = "modal-fundo";
  const caixa = document.createElement("div");
  caixa.className = "modal";
  caixa.setAttribute("role", "dialog");
  caixa.setAttribute("aria-modal", "true");
  const titulo = document.createElement("h2");
  titulo.className = "modal-titulo";
  titulo.id = `modal-titulo-${Math.random().toString(36).slice(2, 8)}`;
  titulo.textContent = op.titulo;
  caixa.setAttribute("aria-labelledby", titulo.id);
  const miolo = document.createElement("div");
  miolo.className = "modal-miolo";
  miolo.append(op.corpo);
  const rodape = document.createElement("div");
  rodape.className = "modal-rodape";
  const aviso = document.createElement("div");
  aviso.className = "modal-aviso";
  aviso.setAttribute("role", "status");
  const botoes = document.createElement("div");
  botoes.className = "modal-acoes";
  rodape.append(aviso, botoes);
  caixa.append(titulo, miolo, rodape);
  fundo.append(caixa);

  let fechado = false;
  const fechar = () => {
    if (fechado) return;
    fechado = true;
    document.removeEventListener("keydown", teclas, true);
    fundo.remove();
    op.aoFechar?.();
  };
  const avisar = (texto: string, ruim = false) => {
    aviso.textContent = texto;
    aviso.classList.toggle("ruim", ruim);
  };

  const acoes = op.acoes?.length ? op.acoes : [{ rotulo: "Fechar" }];
  let principal: HTMLButtonElement | null = null;
  for (const a of acoes) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = a.rotulo;
    if (a.primaria) { b.classList.add("primaria"); principal = b; }
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await a.aoClicar?.();
        if (r !== false) fechar();
      } catch (e) {
        avisar(e instanceof Error ? e.message : String(e), true);
      } finally {
        b.disabled = false;
      }
    });
    botoes.append(b);
  }

  const teclas = (e: KeyboardEvent) => {
    if (fechado) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fechar(); return; }
    if (e.key === "Enter" && principal && (e.target as HTMLElement)?.tagName !== "TEXTAREA") {
      e.preventDefault();
      principal.click();
    }
  };
  document.addEventListener("keydown", teclas, true);
  fundo.addEventListener("mousedown", (e) => { if (e.target === fundo) fechar(); });

  raiz.append(fundo);
  const primeiro = caixa.querySelector<HTMLElement>("input, select, textarea, button");
  primeiro?.focus();
  return { fechar, avisar, elemento: caixa };
}

export type TomSelo = "ativo" | "reserva" | "ok" | "aviso" | "neutro";

export interface AcaoCard {
  rotulo: string;
  aoClicar: () => void;
  perigo?: boolean;
  /** Ação principal do card (ex.: "Usar este"): destacada. */
  primaria?: boolean;
}

export interface Card {
  id: string;
  titulo: string;
  /** Etiqueta curta ao lado do título (ex.: tipo do provedor). */
  etiqueta?: string;
  selos?: { texto: string; tom: TomSelo }[];
  /** Linhas técnicas em monoespaçada (endpoint, modelo, comando). Quebram em vez de vazar. */
  detalhes?: string[];
  /** Lista curta de itens (ex.: modelos) mostrada como fichas. */
  fichas?: string[];
  acoes?: AcaoCard[];
  /** Texto usado pela busca além do título. */
  busca?: string;
}

export interface OpcoesCards {
  /** Mensagem quando a lista está vazia. */
  vazio: string;
  /** Ação do estado vazio e do topo (ex.: "Adicionar provedor"). */
  adicionar?: { rotulo: string; aoClicar: () => void };
  /** A partir de quantos itens mostrar a busca. Padrão: 6. */
  buscaAPartirDe?: number;
}

/** Desenha uma grade de cards (com busca quando cresce) dentro de `alvo`, substituindo o conteúdo. */
export function desenharCards(alvo: HTMLElement, cards: Card[], op: OpcoesCards): void {
  alvo.innerHTML = "";
  alvo.classList.add("cards-bloco");
  const topo = document.createElement("div");
  topo.className = "cards-topo";
  let busca: HTMLInputElement | null = null;
  if (cards.length >= (op.buscaAPartirDe ?? 6)) {
    busca = document.createElement("input");
    busca.type = "search";
    busca.className = "cards-busca";
    busca.placeholder = "Buscar…";
    busca.setAttribute("aria-label", "Buscar");
    topo.append(busca);
  }
  if (op.adicionar && cards.length > 0) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "primaria cards-adicionar";
    b.textContent = op.adicionar.rotulo;
    b.addEventListener("click", op.adicionar.aoClicar);
    topo.append(b);
  }
  if (topo.childElementCount) alvo.append(topo);

  if (cards.length === 0) {
    const v = document.createElement("div");
    v.className = "cards-vazio";
    const p = document.createElement("p");
    p.textContent = op.vazio;
    v.append(p);
    if (op.adicionar) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "primaria";
      b.textContent = op.adicionar.rotulo;
      b.addEventListener("click", op.adicionar.aoClicar);
      v.append(b);
    }
    alvo.append(v);
    return;
  }

  const grade = document.createElement("div");
  grade.className = "cards-grade";
  const elementos: { el: HTMLElement; texto: string }[] = [];
  for (const c of cards) {
    const el = document.createElement("article");
    el.className = "card";
    el.dataset.id = c.id;
    const cab = document.createElement("div");
    cab.className = "card-cabeca";
    const h = document.createElement("h3");
    h.textContent = c.titulo;
    cab.append(h);
    if (c.etiqueta) {
      const e = document.createElement("span");
      e.className = "card-etiqueta";
      e.textContent = c.etiqueta;
      cab.append(e);
    }
    for (const s of c.selos ?? []) {
      const e = document.createElement("span");
      e.className = `selo selo-${s.tom}`;
      e.textContent = s.texto;
      cab.append(e);
    }
    el.append(cab);
    for (const d of c.detalhes ?? []) {
      const p = document.createElement("p");
      p.className = "card-detalhe";
      p.textContent = d;
      el.append(p);
    }
    if (c.fichas?.length) {
      const f = document.createElement("div");
      f.className = "card-fichas";
      for (const t of c.fichas) {
        const s = document.createElement("span");
        s.className = "ficha";
        s.textContent = t;
        f.append(s);
      }
      el.append(f);
    }
    if (c.acoes?.length) {
      const a = document.createElement("div");
      a.className = "card-acoes";
      for (const ac of c.acoes) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = ac.rotulo;
        if (ac.perigo) b.classList.add("perigo");
        if (ac.primaria) b.classList.add("primaria");
        b.addEventListener("click", ac.aoClicar);
        a.append(b);
      }
      el.append(a);
    }
    grade.append(el);
    elementos.push({ el, texto: `${c.titulo} ${c.etiqueta ?? ""} ${c.busca ?? ""} ${(c.fichas ?? []).join(" ")}`.toLowerCase() });
  }
  alvo.append(grade);
  busca?.addEventListener("input", () => {
    const q = busca!.value.trim().toLowerCase();
    for (const { el, texto } of elementos) el.hidden = q !== "" && !texto.includes(q);
  });
}

/** Campo rotulado padrão para formulários de modal (rótulo em cima, campo em largura total). */
export function campoModal(rotulo: string, campo: HTMLElement, ajuda?: string): HTMLElement {
  const l = document.createElement("label");
  l.className = "campo-modal";
  const t = document.createElement("span");
  t.className = "campo-modal-rotulo";
  t.textContent = rotulo;
  l.append(t, campo);
  if (ajuda) {
    const a = document.createElement("span");
    a.className = "campo-modal-ajuda";
    a.textContent = ajuda;
    l.append(a);
  }
  return l;
}
