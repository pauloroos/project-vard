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

const CAMPOS = ["perfil-nome", "perfil-usuario", "perfil-tom", "perfil-personalidade", "perfil-instrucoes", "perfil-sobre-usuario"];

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
    ler: () => lerPerfil(),
    gravar: async () => {},
    previa: async () => null,
    ...deps,
  });
  await aba.montar();
  return { raiz, aba };
}

describe("aba-perfil (T14a)", () => {
  beforeEach(() => {
    estado.chamadas = [];
    estado.perfilLido = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("mostra os 6 campos", async () => {
    const { raiz } = await criarAba();
    for (const id of CAMPOS) expect(raiz.querySelector(`#${id}`), id).toBeTruthy();
    expect(raiz.querySelectorAll("input, textarea").length).toBe(6);
    expect(raiz.querySelector("legend")!.textContent).toBe("Perfil do agente");
  });

  it("carrega o perfil salvo nos campos e o padrão quando não existe", async () => {
    estado.perfilLido = { versao: 1, tom: "direto e calmo", personalidade: "responde pouco", instrucoes: "frases curtas.", sobre_usuario: "gosta de café." };
    const { raiz } = await criarAba();
    expect((raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe("direto e calmo");
    expect((raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value).toBe("frases curtas.");
    expect((raiz.querySelector("#perfil-nome") as HTMLInputElement).value).toBe("Aurora");
    expect((raiz.querySelector("#perfil-usuario") as HTMLInputElement).value).toBe("Fulano");

    document.body.innerHTML = "";
    estado.perfilLido = null;
    const semArquivo = await criarAba();
    expect((semArquivo.raiz.querySelector("#perfil-tom") as HTMLInputElement).value).toBe("");
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
  });

  it("prévia monta a persona pela ponte com nome e usuário", async () => {
    const buscar = vi.fn(async (_url: string) => new Response(JSON.stringify({ texto: "# Perfil do agente\nNome do assistente: Aurora" }), { status: 200 }));
    vi.stubGlobal("fetch", buscar);
    const { raiz } = await criarAba({ previa: () => previaPersona("http://127.0.0.1:4700", "Aurora", "Fulano") });
    (raiz.querySelector("#perfil-previa") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(raiz.querySelector("#perfil-texto")!.textContent).toContain("Nome do assistente: Aurora"));
    const url = String(buscar.mock.calls[0][0]);
    expect(url).toContain("/perfil/persona");
    expect(url).toContain("nome=Aurora");
    expect(url).toContain("usuario=Fulano");
  });

  it("prévia com a ponte fora mostra o aviso em vez de travar", async () => {
    const { raiz } = await criarAba({ previa: async () => null });
    (raiz.querySelector("#perfil-previa") as HTMLButtonElement).click();
    await vi.waitFor(() => expect((raiz.querySelector("#perfil-texto") as HTMLPreElement).hidden).toBe(false));
    expect(raiz.querySelector("#perfil-texto")!.textContent).toContain("ponte");
  });

  it("prévia sem ponte configurada não faz requisição", async () => {
    const buscar = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", buscar);
    expect(await previaPersona("", "Aurora", "Fulano")).toBeNull();
    expect(buscar).not.toHaveBeenCalled();
  });

  it("está registrada na tela de configurações", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    const botoes = Array.from(raiz.querySelectorAll<HTMLButtonElement>("nav button")).map((b) => b.dataset.aba);
    expect(botoes).toContain("perfil");
    painel.abrirAba("perfil");
    for (const id of CAMPOS) expect(raiz.querySelector(`#${id}`), id).toBeTruthy();
    expect(raiz.querySelector("#cfg-perfil")!.innerHTML.length).toBeGreaterThan(0);
  });

  it("salvar grava o config.json e o perfil.json", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("perfil");
    (raiz.querySelector("#cfg-nome") as HTMLInputElement).value = "Aurora";
    (raiz.querySelector("#cfg-usuario") as HTMLInputElement).value = "Fulano";
    (raiz.querySelector("#perfil-tom") as HTMLInputElement).value = "direto e calmo";
    (raiz.querySelector("#perfil-instrucoes") as HTMLTextAreaElement).value = "Responda em português.";
    (raiz.querySelector("#cfg-salvar") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(raiz.querySelector("#cfg-msg")!.textContent).toContain("Salvo"));

    const config = estado.chamadas.find((c) => c.cmd === "gravar_config");
    expect(config, "gravar_config chamado").toBeTruthy();
    expect((config!.args.config as Config).nome).toBe("Aurora");
    expect((config!.args.config as Config).usuario).toBe("Fulano");

    const perfil = estado.chamadas.find((c) => c.cmd === "gravar_perfil");
    expect(perfil, "gravar_perfil chamado").toBeTruthy();
    expect(perfil!.args.valor).toEqual({
      versao: 1, tom: "direto e calmo", personalidade: "", instrucoes: "Responda em português.", sobre_usuario: "",
    });
  });

  it("nome digitado na aba Perfil acompanha a aba Geral", async () => {
    const raiz = criarRaiz();
    const painel = new Configuracoes({ ...CONFIG_PADRAO } as Config, raiz, criarDeps());
    await painel.montar();
    painel.abrirAba("perfil");
    const campoGeral = raiz.querySelector("#cfg-nome") as HTMLInputElement;
    const campoPerfil = raiz.querySelector("#perfil-nome") as HTMLInputElement;
    campoGeral.value = "Vardzinha";
    campoGeral.dispatchEvent(new Event("input", { bubbles: true }));
    expect(campoPerfil.value).toBe("Vardzinha");
    campoPerfil.value = "Aurora";
    campoPerfil.dispatchEvent(new Event("input", { bubbles: true }));
    expect(campoGeral.value).toBe("Aurora");
  });
});
