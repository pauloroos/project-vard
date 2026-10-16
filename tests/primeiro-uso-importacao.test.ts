import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte, ErroPonte } from "../src/conectores/ponte/cliente";
import {
  CAMPOS_HUD_IMPORTAVEIS,
  aplicarHudEscolhido,
  montarImportacao,
  montarPedidoPrevia,
  normalizarPrevia,
  resumirHudAtual,
  sugerirEscolhas,
  type DepsImportacao,
  type PreviaImportacao,
} from "../src/ui/primeiro-uso-importacao";
import { CONFIG_PADRAO, type Config } from "../src/config/config";

const BASE = "http://127.0.0.1:4700";

function responder(corpo: unknown, status = 200): Response {
  return new Response(typeof corpo === "string" ? corpo : JSON.stringify(corpo), { status });
}

function cfgBase(): Config {
  return { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos }, nome: "vard", variantes: ["vard"] };
}

const PREVIA_EXEMPLO = {
  schema: 1,
  previa_id: "previa-1",
  origem: "X:/ANTIGA",
  ja_ativo: false,
  categorias: [
    {
      id: "chamada", titulo: "Nome de chamada", estado: "pronta",
      itens: [{ campo: "nome", origem: "Coruja", destino: "vard", conflito: true }],
      avisos: [],
    },
    {
      id: "segredos", titulo: "Segredos", estado: "pronta",
      itens: [{ campo: "telegram", origem_tem: true, destino_tem: false, conflito: false }],
      avisos: [],
    },
  ],
  avisos: [],
};

describe("resumirHudAtual", () => {
  it("leva_so_os_campos_permitidos_e_nunca_chaves", () => {
    const cfg = { ...cfgBase(), elevenlabs_chave: "SEGREDO", gemini_chave: "OUTRO" };
    const r = resumirHudAtual(cfg);
    expect(r.nome).toBe("vard");
    expect(r.variantes).toEqual(["vard"]);
    expect(JSON.stringify(r)).not.toContain("SEGREDO");
    expect(JSON.stringify(r)).not.toContain("OUTRO");
    for (const k of Object.keys(r)) expect(CAMPOS_HUD_IMPORTAVEIS).toContain(k);
  });
});

describe("montarPedidoPrevia", () => {
  it("monta_origem_e_hud_sem_segredos", () => {
    const corpo = montarPedidoPrevia("X:/ANTIGA", { ...cfgBase(), elevenlabs_chave: "SEGREDO" });
    expect(corpo.origem).toBe("X:/ANTIGA");
    expect(JSON.stringify(corpo)).not.toContain("SEGREDO");
  });
});

describe("normalizarPrevia", () => {
  it("aceita_previa_valida", () => {
    expect(normalizarPrevia(PREVIA_EXEMPLO)?.previa_id).toBe("previa-1");
  });

  it("recusa_forma_errada_e_categoria_desconhecida", () => {
    expect(normalizarPrevia(null)).toBeNull();
    expect(normalizarPrevia({ ...PREVIA_EXEMPLO, categorias: [{ id: "ufo", estado: "pronta", itens: [] }] })).toBeNull();
    expect(normalizarPrevia({ ...PREVIA_EXEMPLO, previa_id: 42 })).toBeNull();
  });
});

describe("sugerirEscolhas", () => {
  it("propoe_importar_sem_conflito_e_manter_com_conflito", () => {
    const pv = normalizarPrevia(PREVIA_EXEMPLO)!;
    expect(sugerirEscolhas(pv)).toEqual({ chamada: "manter", segredos: "importar" });
  });
});

describe("aplicarHudEscolhido", () => {
  it("copia_so_campos_permitidos_com_tipo_certo", () => {
    const atual = cfgBase();
    const saida = aplicarHudEscolhido(atual, { nome: "Coruja", voz: "pm_sara", elevenlabs_chave: "SEGREDO", ufo: 1 });
    expect(saida.nome).toBe("Coruja");
    expect(saida.voz).toBe("pm_sara");
    expect(saida.elevenlabs_chave).toBe("");
    expect(atual.nome).toBe("vard"); // não mexe no objeto de entrada
  });

  it("ignora_valor_com_tipo_errado", () => {
    const saida = aplicarHudEscolhido(cfgBase(), { velocidade: "rapido", nome: "  " });
    expect(saida.velocidade).toBe(CONFIG_PADRAO.velocidade);
    expect(saida.nome).toBe("vard");
  });
});

describe("Ponte.importacao", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("previa_chama_a_rota_com_origem_e_hud", async () => {
    const urls: string[] = [];
    let corpo: unknown = null;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      urls.push(url); corpo = JSON.parse(String(init.body)); return responder(PREVIA_EXEMPLO);
    }));
    const pv = await new Ponte(BASE).previaImportacao("X:/ANTIGA", { nome: "vard" });
    expect(urls).toEqual([`${BASE}/primeiro-uso/importacao/previa`]);
    expect(corpo).toEqual({ origem: "X:/ANTIGA", hud_atual: { nome: "vard" } });
    expect(pv.previa_id).toBe("previa-1");
  });

  it("aplicar_e_reverter_chamam_as_rotas", async () => {
    const urls: string[] = [];
    const corpos: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      urls.push(url);
      corpos.push(JSON.parse(String(init.body)));
      if (url.endsWith("/aplicar")) return responder({ ok: true, operacao_id: "op-1", aplicadas: ["chamada"], hud: { nome: "Coruja" }, avisos: [] });
      return responder({ ok: true, operacao_id: "op-1", restaurados: ["delegada.toml"], mantidos: [], avisos: [] });
    }));
    const ponte = new Ponte(BASE);
    expect((await ponte.aplicarImportacao("previa-1", { chamada: "importar" })).operacao_id).toBe("op-1");
    expect((await ponte.reverterImportacao("op-1")).ok).toBe(true);
    expect(urls).toEqual([`${BASE}/primeiro-uso/importacao/aplicar`, `${BASE}/primeiro-uso/importacao/reverter`]);
    expect(corpos).toEqual([
      { previa_id: "previa-1", escolhas: { chamada: "importar" } },
      { operacao_id: "op-1" },
    ]);
  });

  it("erro_da_ponte_vira_ErroPonte_com_o_codigo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ erro: "origem_invalida" }, 422)));
    await expect(new Ponte(BASE).previaImportacao("X:/nada", {})).rejects.toMatchObject({ codigo: "origem_invalida" });
    vi.stubGlobal("fetch", vi.fn(async () => responder({ erro: "previa_obsoleta" }, 409)));
    await expect(new Ponte(BASE).aplicarImportacao("p", {})).rejects.toMatchObject({ codigo: "previa_obsoleta" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    await expect(new Ponte(BASE).reverterImportacao("op")).rejects.toBeInstanceOf(ErroPonte);
  });
});

function depsFake(salvos: Config[]): DepsImportacao {
  return {
    previa: async () => structuredClone(PREVIA_EXEMPLO) as unknown as PreviaImportacao,
    aplicar: async () => ({ ok: true, operacao_id: "op-1", aplicadas: ["chamada"], hud: { nome: "Coruja" }, avisos: [] }),
    reverter: async () => ({ ok: true, operacao_id: "op-1", restaurados: [], mantidos: [], avisos: [] }),
    lerHud: () => cfgBase(),
    salvarHud: async (c) => { salvos.push(c); },
  };
}

describe("montarImportacao (ligação)", () => {
  it("previa_renderiza_categorias_e_aplicar_salva_o_hud", async () => {
    const salvos: Config[] = [];
    const raiz = document.createElement("div");
    montarImportacao(raiz, depsFake(salvos));
    const origem = raiz.querySelector<HTMLInputElement>("#primeiro-uso-importacao-origem")!;
    origem.value = "X:/ANTIGA";
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-previa")!).click();
    await vi.waitFor(() => expect(raiz.querySelector("#primeiro-uso-importacao-categorias")).not.toBeNull());
    expect(raiz.textContent).toContain("Coruja");
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-aplicar")!).click();
    await vi.waitFor(() => expect(salvos.length).toBe(1));
    expect(salvos[0].nome).toBe("Coruja");
    expect(raiz.querySelector("#primeiro-uso-importacao-reverter")).not.toBeNull();
  });

  it("reverter_chama_a_ponte_e_devolve_o_hud_anterior", async () => {
    const salvos: Config[] = [];
    const chamadas: string[] = [];
    const deps = depsFake(salvos);
    deps.reverter = async (id) => { chamadas.push(id); return { ok: true, operacao_id: id, restaurados: [], mantidos: [], avisos: [] }; };
    const raiz = document.createElement("div");
    montarImportacao(raiz, deps);
    (raiz.querySelector<HTMLInputElement>("#primeiro-uso-importacao-origem")!).value = "X:/ANTIGA";
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-previa")!).click();
    await vi.waitFor(() => expect(raiz.querySelector("#primeiro-uso-importacao-aplicar")).not.toBeNull());
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-aplicar")!).click();
    await vi.waitFor(() => expect(salvos.length).toBe(1));
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-reverter")!).click();
    await vi.waitFor(() => expect(chamadas).toEqual(["op-1"]));
    expect(salvos.length).toBe(2);
    expect(salvos[1].nome).toBe("vard");
  });

  it("origem_vazia_mostra_erro_sem_chamar_a_ponte", async () => {
    let chamadas = 0;
    const deps = depsFake([]);
    deps.previa = async () => { chamadas += 1; throw new ErroPonte("rede"); };
    const raiz = document.createElement("div");
    montarImportacao(raiz, deps);
    (raiz.querySelector<HTMLButtonElement>("#primeiro-uso-importacao-previa")!).click();
    await vi.waitFor(() => expect(raiz.querySelector("#primeiro-uso-importacao-msg")!.textContent).not.toBe(""));
    expect(chamadas).toBe(0);
  });
});
