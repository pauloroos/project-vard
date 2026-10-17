import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AbaOficina } from "../src/ui/aba-oficina";
import { HABILIDADES_PADRAO, type HabilidadesConfig, type Habilidade } from "../src/config/habilidades";
import { habilidadesFabrica } from "../src/config/habilidades-fabrica";

const receita: Habilidade = { id: "rotina-dia", nome: "Começar o dia", quando: ["bom dia"], instrucoes: "1. Consultar a agenda.", ligada: true, situacao: "treinada", criada_em: "2026-10-17T12:00:00Z", validada_em: null };
let cfg: HabilidadesConfig;
let raiz: HTMLElement;
let aba: AbaOficina;
let gravar: ReturnType<typeof vi.fn<(v: HabilidadesConfig) => Promise<void>>>;
const assentar = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
function botao(rotulo: string, alvo: ParentNode = document): HTMLButtonElement {
  const el = [...alvo.querySelectorAll("button")].find((b) => b.textContent === rotulo);
  expect(el, rotulo).toBeDefined();
  return el!;
}
function campo(rotulo: string): HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement {
  const label = [...document.querySelectorAll("label")].find((l) => l.querySelector("span")?.textContent === rotulo);
  return label!.querySelector("input, textarea, select")!;
}
function card(id: string): HTMLElement { return raiz.querySelector(`[data-id="${id}"]`)!; }

beforeEach(async () => {
  cfg = structuredClone(HABILIDADES_PADRAO);
  raiz = document.createElement("div"); document.body.append(raiz);
  gravar = vi.fn(async (v: HabilidadesConfig) => { cfg = structuredClone(v); });
  aba = new AbaOficina(raiz, { nome: () => "aurora", statusPonte: async () => null, ler: async () => structuredClone(cfg), gravar });
  aba.montar(); await aba.ativar();
});
afterEach(() => { aba.desativar(); document.querySelectorAll<HTMLButtonElement>(".modal-acoes button").forEach((b) => { if (b.textContent === "Cancelar") b.click(); }); document.body.innerHTML = ""; });

describe("Oficina", () => {
  it("mostra os limites e atualiza o contador de instruções ao criar e editar", async () => {
    botao("Nova habilidade").click();
    expect((campo("Nome") as HTMLInputElement).maxLength).toBe(80);
    expect((campo("Quando usar (uma frase por linha)") as HTMLTextAreaElement).maxLength).toBe(2009);
    expect((campo("O que fazer") as HTMLTextAreaElement).maxLength).toBe(4000);
    const dialogo = document.querySelector('[role="dialog"]')!;
    expect(dialogo.textContent).toContain("Até 80 caracteres");
    expect(dialogo.textContent).toContain("Até 10 frases de até 200 caracteres");
    expect(dialogo.textContent).toContain("0/4000 caracteres");
    campo("O que fazer").value = "Passo";
    campo("O que fazer").dispatchEvent(new Event("input"));
    expect(dialogo.textContent).toContain("5/4000 caracteres");
    botao("Cancelar").click();
    cfg.habilidades = [structuredClone(receita)]; await aba.ativar();
    botao("Editar", card(receita.id)).click();
    expect(document.querySelector('[role="dialog"]')!.textContent).toContain(`${receita.instrucoes.length}/4000 caracteres`);
  });
  it.each([
    ["Nome", "a".repeat(81), "Nome deve ter até 80 caracteres"],
    ["Quando usar (uma frase por linha)", Array(11).fill("oi").join("\n"), "Use até 10 frases de exemplo"],
    ["Quando usar (uma frase por linha)", "a".repeat(201), "Cada frase deve ter até 200 caracteres"],
    ["O que fazer", "a".repeat(4001), "Instruções devem ter até 4000 caracteres"],
  ])("recusa excesso em %s sem gravar e mantém o modal aberto", async (rotulo, valor, erro) => {
    botao("Nova habilidade").click();
    campo("Nome").value = "Planejar";
    campo("Quando usar (uma frase por linha)").value = "bom dia";
    campo("O que fazer").value = "Consultar agenda.";
    campo(rotulo).value = valor;
    botao("Salvar").click(); await assentar();
    expect(gravar).not.toHaveBeenCalled();
    const dialogo = document.querySelector('[role="dialog"]');
    expect(dialogo).not.toBeNull();
    expect(dialogo!.textContent).toContain(erro);
  });
  it("recusa a habilidade 201 sem persistir", async () => {
    cfg.habilidades = Array.from({ length: 200 }, (_, i) => ({ ...receita, id: `receita-${i}` }));
    await aba.ativar(); botao("Nova habilidade").click();
    campo("Nome").value = "Planejar";
    campo("Quando usar (uma frase por linha)").value = "bom dia";
    campo("O que fazer").value = "Consultar agenda.";
    botao("Salvar").click(); await assentar();
    expect(gravar).not.toHaveBeenCalled();
    expect(document.querySelector('[role="dialog"]')!.textContent).toContain("Cadastre até 200 habilidades");
    expect(cfg.habilidades).toHaveLength(200);
  });
  it("sete capacidades com frases personalizadas e ações restritas", () => {
    expect(habilidadesFabrica("aurora", false).map((h) => h.nome)).toEqual(["Conversa", "Computador", "Oficina", "Consultas", "Memória", "Reunião", "Sistema", "Resumo da manhã", "Pesquisa", "Agente remoto"]);
    expect(raiz.querySelectorAll("article")).toHaveLength(10);
    expect(card("conversa").textContent).toContain("Aurora, que horas são?");
    expect(card("computador").textContent).toContain("precisa da instalação");
    for (const c of raiz.querySelectorAll("article")) {
      expect(c.textContent).toContain("Capaz");
    }
  });
  it("três novas habilidades de fábrica aparecem como capazes com etiqueta quando falta configuração", () => {
    const lista = habilidadesFabrica("aurora", false);
    const manha = lista.find((h) => h.id === "resumo-manha");
    const pesquisa = lista.find((h) => h.id === "pesquisa");
    const remoto = lista.find((h) => h.id === "agente-remoto");
    expect(manha).toBeDefined();
    expect(pesquisa).toBeDefined();
    expect(remoto).toBeDefined();
    expect(manha!.situacao).toBe("capaz");
    expect(pesquisa!.situacao).toBe("capaz");
    expect(remoto!.situacao).toBe("capaz");
    expect(manha!.etiqueta).toBe("precisa de um agente configurado");
    expect(pesquisa!.etiqueta).toBe("precisa de um agente configurado");
    expect(remoto!.etiqueta).toBe("precisa de um agente configurado");
  });
  it("novas habilidades mostram botão Configurar que chama abrirAba com modelos", async () => {
    const abrirAba = vi.fn();
    aba.desativar(); raiz.innerHTML = "";
    aba = new AbaOficina(raiz, { nome: () => "aurora", statusPonte: async () => null, ler: async () => structuredClone(cfg), gravar, abrirAba });
    aba.montar(); await aba.ativar();
    const btnManha = botao("Configurar", card("resumo-manha"));
    const btnPesquisa = botao("Configurar", card("pesquisa"));
    const btnRemoto = botao("Configurar", card("agente-remoto"));
    expect(btnManha).toBeDefined();
    expect(btnPesquisa).toBeDefined();
    expect(btnRemoto).toBeDefined();
    btnManha.click();
    expect(abrirAba).toHaveBeenCalledWith("modelos");
    abrirAba.mockClear();
    btnPesquisa.click();
    expect(abrirAba).toHaveBeenCalledWith("modelos");
    abrirAba.mockClear();
    btnRemoto.click();
    expect(abrirAba).toHaveBeenCalledWith("modelos");
  });
  it("fábrica edita no mesmo modal já preenchido e restaura o padrão com confirmação", async () => {
    expect([...card("pesquisa").querySelectorAll("button")].map((b) => b.textContent)).not.toContain("Excluir");
    expect(card("pesquisa").textContent).not.toContain("Restaurar padrão");
    botao("Editar", card("pesquisa")).click();
    const dialogo = document.querySelector('[role="dialog"]')!;
    expect(dialogo.querySelector("h2")!.textContent).toBe("Editar habilidade");
    expect(campo("Nome").value).toBe("Pesquisa");
    expect(campo("Quando usar (uma frase por linha)").value).toBe("pesquisa sobre ...\nbusca informações sobre ...");
    expect(campo("O que fazer").value).toBe("");
    expect((campo("Ligada") as HTMLInputElement).checked).toBe(true);
    expect([...dialogo.querySelectorAll("label span")].map((s) => s.textContent)).not.toContain("Situação");
    campo("Nome").value = "Pesquisar na web";
    campo("O que fazer").value = "Cite as fontes.";
    botao("Salvar").click(); await assentar();
    expect(cfg).toEqual({ versao: 1, habilidades: [], desligadas: [], fabrica: { pesquisa: { nome: "Pesquisar na web", instrucoes: "Cite as fontes." } } });
    expect(card("pesquisa").querySelector("h3")!.textContent).toBe("Pesquisar na web");
    expect(card("pesquisa").textContent).toContain("Personalizada");
    expect(card("pesquisa").textContent).toContain("Aurora, pesquisa sobre ...");
    botao("Editar", card("pesquisa")).click();
    expect(campo("Nome").value).toBe("Pesquisar na web");
    expect(campo("O que fazer").value).toBe("Cite as fontes.");
    (campo("Ligada") as HTMLInputElement).checked = false;
    botao("Salvar").click(); await assentar();
    expect(cfg.desligadas).toEqual(["pesquisa"]);
    expect(card("pesquisa").textContent).toContain("Desligada");
    botao("Restaurar padrão", card("pesquisa")).click();
    expect(cfg.fabrica).toBeDefined();
    botao("Cancelar").click(); expect(cfg.fabrica).toBeDefined();
    botao("Restaurar padrão", card("pesquisa")).click();
    botao("Restaurar padrão", document.querySelector('[role="dialog"]')!).click(); await assentar();
    expect(cfg).toEqual({ versao: 1, habilidades: [], desligadas: ["pesquisa"] });
    expect(card("pesquisa").querySelector("h3")!.textContent).toBe("Pesquisa");
    expect(card("pesquisa").textContent).not.toContain("Restaurar padrão");
  });
  it("editar fábrica sem mudar nada não grava ajuste e recusa nome vazio", async () => {
    botao("Editar", card("conversa")).click();
    botao("Salvar").click(); await assentar();
    expect(cfg).toEqual({ versao: 1, habilidades: [], desligadas: [] });
    botao("Editar", card("conversa")).click();
    campo("Nome").value = " ";
    botao("Salvar").click(); await assentar();
    expect(document.querySelector('[role="dialog"]')!.textContent).toContain("Preencha nome, frases de exemplo e instruções");
    expect(cfg.fabrica).toBeUndefined();
  });
  it("fábrica só liga/desliga e não entra na lista persistida", async () => {
    botao("Desligar", card("computador")).click(); await assentar();
    expect(cfg).toEqual({ versao: 1, habilidades: [], desligadas: ["computador"] });
    expect(card("computador").textContent).toContain("Desligada");
    botao("Ligar", card("computador")).click(); await assentar();
    expect(cfg.desligadas).toEqual([]);
  });
  it("cadastra em modal, edita e marca validada com data", async () => {
    botao("Nova habilidade").click();
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    campo("Nome").value = "Começar o dia";
    campo("Quando usar (uma frase por linha)").value = "bom dia\nvamos começar";
    campo("O que fazer").value = "1. Consultar a agenda.";
    botao("Salvar").click(); await assentar();
    expect(cfg.habilidades).toHaveLength(1);
    const h = cfg.habilidades[0];
    expect(h.quando).toEqual(["bom dia", "vamos começar"]);
    expect(h.situacao).toBe("treinada");
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    botao("Editar", card(h.id)).click(); campo("Nome").value = "Planejar o dia";
    botao("Salvar").click(); await assentar();
    expect(cfg.habilidades[0].nome).toBe("Planejar o dia");
    expect(cfg.habilidades[0].criada_em).toBe(h.criada_em);
    botao("Marcar como validada", card(h.id)).click(); await assentar();
    expect(cfg.habilidades[0].situacao).toBe("validada");
    expect(cfg.habilidades[0].validada_em).toMatch(/^\d{4}-/);
    expect(card(h.id).textContent).toContain("Validada");
  });
  it("exclui somente depois de confirmação", async () => {
    cfg.habilidades = [structuredClone(receita)]; await aba.ativar();
    botao("Excluir", card(receita.id)).click();
    expect(cfg.habilidades).toHaveLength(1);
    botao("Cancelar").click(); expect(cfg.habilidades).toHaveLength(1);
    botao("Excluir", card(receita.id)).click(); botao("Excluir habilidade", document.querySelector('[role="dialog"]')!).click(); await assentar();
    expect(cfg.habilidades).toEqual([]);
  });
  it("filtra texto e situação juntos preservando a busca após alteração", async () => {
    cfg.habilidades = [structuredClone(receita), { ...receita, id: "rotina-noite", nome: "Fechar o dia", situacao: "validada", validada_em: "2026-10-17T13:00:00Z" }]; await aba.ativar();
    const busca = raiz.querySelector<HTMLInputElement>('input[type="search"]')!;
    busca.value = "agenda"; busca.dispatchEvent(new Event("input"));
    const filtro = raiz.querySelector<HTMLSelectElement>('select[aria-label="Situação"]')!;
    filtro.value = "treinada"; filtro.dispatchEvent(new Event("change"));
    expect([...raiz.querySelectorAll<HTMLElement>("article")].filter((el) => !el.hidden).map((el) => el.dataset.id)).toEqual([receita.id]);
    botao("Desligar", card(receita.id)).click(); await assentar();
    expect(busca.value).toBe("agenda");
    expect(card(receita.id).hidden).toBe(false);
    expect(card("rotina-noite").hidden).toBe(true);
  });
  it("validação mantém modal aberto e falha de escrita preserva estado", async () => {
    botao("Nova habilidade").click(); botao("Salvar").click(); await assentar();
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    expect(gravar).not.toHaveBeenCalled();
    botao("Cancelar").click();
    gravar.mockRejectedValueOnce(new Error("disco indisponível"));
    botao("Desligar", card("computador")).click(); await assentar();
    expect(card("computador").textContent).toContain("Ligada");
    expect(raiz.textContent).toContain("disco indisponível");
  });
  it("falha de leitura impede sobrescrever o arquivo", async () => {
    aba.desativar(); raiz.innerHTML = "";
    aba = new AbaOficina(raiz, { nome: () => "vard", statusPonte: async () => null, ler: async () => { throw new Error("arquivo inválido"); }, gravar });
    aba.montar(); await aba.ativar();
    expect(raiz.textContent).toContain("arquivo inválido");
    expect(botao("Nova habilidade").disabled).toBe(true);
    botao("Desligar", card("computador")).click(); await assentar();
    expect(gravar).not.toHaveBeenCalled();
  });
  it("resposta tardia de aba desativada não repinta nem sobrescreve", async () => {
    aba.desativar(); raiz.innerHTML = "";
    let liberar!: (v: HabilidadesConfig) => void;
    aba = new AbaOficina(raiz, { nome: () => "vard", statusPonte: async () => null, ler: () => new Promise((r) => { liberar = r; }), gravar });
    aba.montar(); const aguardando = aba.ativar(); aba.desativar();
    liberar({ ...structuredClone(HABILIDADES_PADRAO), habilidades: [receita] }); await aguardando;
    expect(raiz.querySelector(`[data-id="${receita.id}"]`)).toBeNull();
  });
});
