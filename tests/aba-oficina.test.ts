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
  it("sete capacidades com frases personalizadas e ações restritas", () => {
    expect(habilidadesFabrica("aurora", false).map((h) => h.nome)).toEqual(["Conversa", "Computador", "Oficina", "Consultas", "Memória", "Reunião", "Sistema"]);
    expect(raiz.querySelectorAll("article")).toHaveLength(7);
    expect(card("conversa").textContent).toContain("Aurora, que horas são?");
    expect(card("computador").textContent).toContain("precisa da instalação");
    for (const c of raiz.querySelectorAll("article")) {
      expect(c.textContent).toContain("Capaz");
      expect([...c.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["Desligar"]);
    }
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
