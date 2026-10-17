import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const estado = vi.hoisted(() => ({
  chamadas: [] as { cmd: string; args: Record<string, unknown> }[],
  perfilLido: null as unknown,
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async (cmd: string, args?: Record<string, unknown>) => {
    estado.chamadas.push({ cmd, args: args ?? {} });
    if (cmd === "ler_perfil") return estado.perfilLido;
    if (cmd === "falhas_de_atalho") return [];
    if (cmd === "inicio_no_logon_ativo") return false;
    if (cmd === "listar_monitores") return [];
    return null;
  }),
}));

import { AbaPerfil, type DepsAbaPerfil } from "../src/ui/aba-perfil";
import { lerPerfil, previaPersona } from "../src/config/perfil";
import { Configuracoes } from "../src/ui/configuracoes";
import { CONFIG_PADRAO, type Config } from "../src/config/config";
import { PERFIS_PRONTOS } from "../src/ui/perfis-prontos";

const CAMPOS_CHAMADA = ["perfil-nome", "perfil-variantes", "perfil-usuario"];
const CAMPOS_PERFIL = ["perfil-tom", "perfil-personalidade", "perfil-instrucoes", "perfil-sobre-usuario"];
const TODOS_CAMPOS = [...CAMPOS_CHAMADA, ...CAMPOS_PERFIL];

function criarRaiz(): HTMLElement {
  const el = document.createElement("div");
  el.id = "painel";
  document.body.appendChild(el);
  return el;
}

function criarDeps() {
  return {
    criarOj: () => ({ saude: async () => true, fala: async () => true, modelos: async () => [] }) as any,
    statusPonte: async () => null,
    modoPonte: async () => false,
    ponte: () => ({}) as any,
    atualizacao: { url: "", buscar: async () => "", instalar: async () => {}, versao: async () => "0.8.0" },
  };
}

async function criarAba(deps: Partial<DepsAbaPerfil> = {}): Promise<{ raiz: HTMLElement; aba: AbaPerfil }> {
  const raiz = criarRaiz();
  const aba = new AbaPerfil(raiz, {
    nome: () => "Aurora",
    usuario: () => "Fulano",
    variantes: () => ["Auri", "Au"],
    ler: () => lerPerfil(),
    gravar: async () => {},
    previa: async () => null,
    ...deps,
  });
  await aba.montar();
  return { raiz, aba };
}

describe("aba-perfil (0.9.4)", () => {
  beforeEach(() => {
    estado.chamadas = [];
    estado.perfilLido = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("mostra os campos de chamada e do perfil", async () => {
    const { raiz } = await criarAba();
    for (const id of TODOS_CAMPOS) expect(raiz.querySelector(`#${id}`), id).toBeTruthy();
    // 7 campos do formulário + 1 input de busca dos cards (desenhado pelo desenharCards)
    expect(raiz.querySelectorAll("input, textarea").length).toBe(8);
    const legends = Array.from(raiz.querySelectorAll("legend")).map((l) => l.textContent);
    expect(legends).toContain("Chamada");
    expect(legends).toContain("Perfis prontos");
    expect(legends).toContain("Perfil do agente");
  });

  it("carrega o perfil salvo e os dados de chamada", async () => {
    estado.perfilLido = { versao: 1, tom: "direto e calmo", personalidade: "responde pouco", instrucoes: "frases curtas.", sobre_usuario: "gosta de café." };
    const { raiz } = await criarAba();
    expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe("direto e calmo");
    expect((raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value).toBe("frases curtas.");
    expect((raiz.querySelector("#perfil-nome") as HTMLInputElement).value).toBe("Aurora");
    expect((raiz.querySelector("#perfil-usuario") as HTMLInputElement).value).toBe("Fulano");
    expect((raiz.querySelector("#perfil-variantes") as HTMLInputElement).value).toBe("Auri, Au");
  });

  it("lerPerfil e gravar usam só os 4 campos do perfil.json", async () => {
    let gravado: unknown = null;
    const { raiz, aba } = await criarAba({ gravar: async (p) => { gravado = p; } });
    (raiz.querySelector("#perfil-tom") as HTMLInputElement).value = "direto";
    (raiz.querySelector("#perfil-personalidade") as HTMLTextAreaElement).value = "responde pouco";
    (raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value = "frases curtas.";
    (raiz.querySelector("#perfil-sobre-usuario") as HTMLTextAreaElement).value = "gosta de café.";
    const esperado = { versao: 1, tom: "direto", personalidade: "responde pouco", instrucoes: "frases curtas.", sobre_usuario: "gosta de café." };
    expect(aba.lerPerfil()).toEqual(esperado);
    await aba.gravar();
    expect(gravado).toEqual(esperado);
    expect(gravado).not.toHaveProperty("nome");
    expect(gravado).not.toHaveProperty("usuario");
    expect(gravado).not.toHaveProperty("variantes");
  });

  it("perfis prontos aparecem como cards", async () => {
    const { raiz } = await criarAba();
    const cards = raiz.querySelectorAll(".card");
    expect(cards.length).toBe(PERFIS_PRONTOS.length);
    for (const p of PERFIS_PRONTOS) {
      expect(raiz.textContent).toContain(p.rotulo);
    }
  });

  it("escolher perfil pronto preenche os campos sem confirmação quando vazios", async () => {
    const { raiz } = await criarAba();
    const botao = raiz.querySelector('.card button') as HTMLButtonElement;
    expect(botao).toBeTruthy();
    botao.click();
    const primeiro = PERFIS_PRONTOS[0];
    expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe(primeiro.tom);
    expect((raiz.querySelector("#perfil-personalidade") as HTMLTextAreaElement).value).toBe(primeiro.personalidade);
    expect((raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value).toBe(primeiro.instrucoes);
    // sobre_usuario não é alterado
    expect((raiz.querySelector("#perfil-sobre-usuario") as HTMLTextAreaElement).value).toBe("");
  });

  it("escolher perfil pronto pede confirmação quando já há texto", async () => {
    estado.perfilLido = { versao: 1, tom: "existente", personalidade: "texto", instrucoes: "conteúdo", sobre_usuario: "" };
    const { raiz } = await criarAba();
    const botao = raiz.querySelector('.card button') as HTMLButtonElement;
    botao.click();
    // Modal deve aparecer
    const modal = document.querySelector(".modal");
    expect(modal).toBeTruthy();
    expect(modal!.textContent).toContain("Substituir");
    // Campos ainda têm o valor antigo antes de confirmar
    expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe("existente");
    // Confirmar substituição
    const btnSubstituir = Array.from(document.querySelectorAll<HTMLButtonElement>(".modal button")).find((b) => b.textContent === "Substituir");
    expect(btnSubstituir).toBeTruthy();
    btnSubstituir!.click();
    await vi.waitFor(() => {
      expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe(PERFIS_PRONTOS[0].tom);
    });
  });

  it("cancelar modal de perfil pronto mantém os valores anteriores", async () => {
    estado.perfilLido = { versao: 1, tom: "original", personalidade: "", instrucoes: "", sobre_usuario: "" };
    const { raiz } = await criarAba();
    const botao = raiz.querySelector('.card button') as HTMLButtonElement;
    botao.click();
    const btnCancelar = Array.from(document.querySelectorAll<HTMLButtonElement>(".modal button")).find((b) => b.textContent === "Cancelar");
    expect(btnCancelar).toBeTruthy();
    btnCancelar!.click();
    await vi.waitFor(() => {
      expect(document.querySelector(".modal")).toBeFalsy();
    });
    expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe("original");
  });

  it("prévia monta a persona pela ponte com nome e usuário", async () => {
    const buscar = vi.fn(async (_url: string) => new Response(JSON.stringify({ texto: "# Perfil do agente\nNome: Aurora" }), { status: 200 }));
    vi.stubGlobal("fetch", buscar);
    const { raiz } = await criarAba({ previa: () => previaPersona("http://127.0.0.1:4700", "Aurora", "Fulano") });
    (raiz.querySelector("#perfil-previa") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(raiz.querySelector("#perfil-texto")!.textContent).toContain("Nome: Aurora"));
    const url = String(buscar.mock.calls[0][0]);
    expect(url).toContain("/perfil/persona");
    expect(url).toContain("nome=Aurora");
    expect(url).toContain("usuario=Fulano");
  });

  it("prévia com a ponte fora mostra aviso", async () => {
    const { raiz } = await criarAba({ previa: async () => null });
    (raiz.querySelector("#perfil-previa") as HTMLButtonElement).click();
    await vi.waitFor(() => expect((raiz.querySelector("#perfil-texto") as HTMLPreElement).hidden).toBe(false));
    expect(raiz.querySelector("#perfil-texto")!.textContent).toContain("ponte");
  });

  it("definir reflete mudanças externas nos campos de chamada", async () => {
    const { raiz, aba } = await criarAba();
    aba.definir("nome", "Vardzinha");
    expect((raiz.querySelector("#perfil-nome") as HTMLInputElement).value).toBe("Vardzinha");
    aba.definir("variantes", "Var, Vard");
    expect((raiz.querySelector("#perfil-variantes") as HTMLInputElement).value).toBe("Var, Vard");
    aba.definir("usuario", "Ana");
    expect((raiz.querySelector("#perfil-usuario") as HTMLInputElement).value).toBe("Ana");
  });

  it("está registrada na tela de configurações", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    const botoes = Array.from(raiz.querySelectorAll<HTMLButtonElement>("nav button")).map((b) => b.dataset.aba);
    expect(botoes).toContain("perfil");
    painel.abrirAba("perfil");
    for (const id of TODOS_CAMPOS) expect(raiz.querySelector(`#${id}`), id).toBeTruthy();
    expect(raiz.querySelector("#cfg-perfil")!.innerHTML.length).toBeGreaterThan(0);
  });

  it("salvar grava config.json e perfil.json com os valores certos", async () => {
    const raiz = criarRaiz();
    const cfg = { ...CONFIG_PADRAO, nome: "Aurora", usuario: "Fulano", variantes: ["Auri"] } as Config;
    const painel = new Configuracoes(cfg, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("perfil");
    (raiz.querySelector("#perfil-tom") as HTMLInputElement).value = "direto e calmo";
    (raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value = "Responda em português.";
    (raiz.querySelector("#cfg-salvar") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(raiz.querySelector("#cfg-msg")!.textContent).toContain("Salvo"));
    const config = estado.chamadas.find((c) => c.cmd === "gravar_config");
    expect(config, "gravar_config chamado").toBeTruthy();
    const perfil = estado.chamadas.find((c) => c.cmd === "gravar_perfil");
    expect(perfil, "gravar_perfil chamado").toBeTruthy();
    expect(perfil!.args.valor).toEqual({
      versao: 1, tom: "direto e calmo", personalidade: "", instrucoes: "Responda em português.", sobre_usuario: "",
    });
  });
});