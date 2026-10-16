/**
 * @vitest-environment jsdom
 */
/**
 * Testes da lista de vozes em cards da seção Voz (0.9.3, U5/U8):
 * escolher grava a seleção como hoje, cadastro/edição/remoção pelo modal,
 * motor ausente mostra o card de instalar, busca filtra e serviço fora avisa.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PaineisConfig } from "../src/config/paineis";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import { CONFIG_PADRAO } from "../src/config/config";
import type { OpenJarvis } from "../src/conectores/openjarvis/cliente";

let paineisMem: PaineisConfig | null = null;

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation((cmd: string, args?: Record<string, unknown>) => {
    if (cmd === "ler_paineis") return Promise.resolve(paineisMem);
    if (cmd === "gravar_paineis") {
      paineisMem = (args?.valor as PaineisConfig) ?? null;
      return Promise.resolve(undefined);
    }
    return Promise.resolve(null);
  }),
}));

vi.mock("../src/config/segredos", () => ({ cofreExiste: vi.fn(async () => true) }));

import { AbaVoz } from "../src/ui/aba-voz";
import { invoke } from "@tauri-apps/api/core";

/** Configs que chegaram ao gravar_paineis (prova de que a seleção foi gravada de verdade). */
function gravacoes(): PaineisConfig[] {
  return vi.mocked(invoke).mock.calls
    .filter(([cmd]) => cmd === "gravar_paineis")
    .map(([, args]) => (args as { valor: PaineisConfig }).valor);
}

const VOZES_XTTS = [
  "Suad Qasim",
  ...Array.from({ length: 57 }, (_, i) => `Voz Fictícia ${String(i + 1).padStart(2, "0")} (pt-BR)`),
];

let estado: { saude: Record<string, unknown> | null; vozes: string[] | null } = {
  saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: true, edge: true, piper: true },
  vozes: VOZES_XTTS,
};

const mockFetch = vi.fn(async (url: unknown) => {
  const u = String(url);
  const resposta = (obj: unknown) => ({ ok: true, json: async () => obj });
  if (u.endsWith("/saude")) {
    if (!estado.saude) throw new TypeError("Failed to fetch");
    return resposta(estado.saude);
  }
  if (u.endsWith("/vozes")) {
    if (!estado.vozes) throw new TypeError("Failed to fetch");
    return resposta({ vozes: estado.vozes, atual: estado.vozes[0] ?? "" });
  }
  if (u.includes("/v1/voices")) return resposta({ voices: [{ voice_id: "el-rachel", name: "Rachel" }] });
  throw new TypeError("Failed to fetch");
});

const ojFalso = {
  saude: async () => true,
  fala: async () => true,
  modelos: async () => ["modelo-falso"],
  perguntar: async () => "",
  sintetizar: async () => new ArrayBuffer(8),
  transcrever: async () => "",
  definirModelo: () => {},
} as unknown as OpenJarvis;

interface AbaTeste {
  raiz: HTMLElement;
  aba: AbaVoz;
  dizer: ReturnType<typeof vi.fn>;
}

function criarAba(): AbaTeste {
  const raiz = document.createElement("div");
  document.body.append(raiz);
  const dizer = vi.fn();
  const aba = new AbaVoz(raiz, { ...CONFIG_PADRAO, voz_url: "http://127.0.0.1:4710" }, {
    criarOj: () => ojFalso,
    velocidade: () => 1,
    dizer,
  });
  aba.montar();
  return { raiz, aba, dizer };
}

async function abrir(): Promise<AbaTeste> {
  const t = criarAba();
  await t.aba.atualizar();
  return t;
}

function cartao(raiz: HTMLElement, id: string): HTMLElement {
  const el = raiz.querySelector<HTMLElement>(`article.card[data-id="${id}"]`);
  expect(el, `card ${id}`).toBeTruthy();
  return el!;
}

function botao(el: HTMLElement, rotulo: string): HTMLButtonElement {
  const b = [...el.querySelectorAll<HTMLButtonElement>(".card-acoes button")].find((x) => x.textContent === rotulo);
  expect(b, `botão ${rotulo}`).toBeTruthy();
  return b!;
}

function modalAberto(): HTMLElement {
  const m = document.querySelector<HTMLElement>(".modal");
  expect(m, "modal aberto").toBeTruthy();
  return m!;
}

function botaoModal(rotulo: string): HTMLButtonElement {
  const m = modalAberto();
  const b = [...m.querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((x) => x.textContent === rotulo);
  expect(b, `botão do modal ${rotulo}`).toBeTruthy();
  return b!;
}

function camposModal(): { id: HTMLInputElement; nome: HTMLInputElement; tipo: HTMLSelectElement; url: HTMLInputElement; modelo: HTMLInputElement; cred: HTMLInputElement } {
  const m = modalAberto();
  const entradas = [...m.querySelectorAll<HTMLElement>(".modal-voz input, .modal-voz select")];
  return {
    id: entradas[0] as HTMLInputElement,
    nome: entradas[1] as HTMLInputElement,
    tipo: entradas[2] as HTMLSelectElement,
    url: entradas[3] as HTMLInputElement,
    modelo: entradas[4] as HTMLInputElement,
    cred: entradas[5] as HTMLInputElement,
  };
}

const proximoTick = () => new Promise((r) => setTimeout(r, 0));

describe("lista de vozes em cards (U5)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    paineisMem = null;
    vi.clearAllMocks();
    vi.stubGlobal("fetch", mockFetch);
    estado = {
      saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: true, edge: true, piper: true },
      vozes: VOZES_XTTS,
    };
  });

  it("lista_agrupada_por_motor_com_o_xtts_inteiro", async () => {
    const { raiz } = await abrir();
    for (const grupo of ["xtts", "kokoro", "edge", "piper", "elevenlabs", "gemini", "fish"]) {
      expect(raiz.querySelector(`#cfg-voz-grupo-${grupo}`), `grupo ${grupo}`).toBeTruthy();
    }
    const xtts = raiz.querySelector<HTMLElement>("#cfg-voz-grupo-xtts")!;
    expect(xtts.querySelectorAll("article.card").length).toBe(58);
    const kokoro = cartao(raiz, "voz:openjarvis:Kokoro:pf_dora");
    expect(kokoro.querySelector(".card-etiqueta")!.textContent).toBe("Kokoro · OpenJarvis");
  });

  it("busca_filtra_os_cards_do_grupo", async () => {
    const { raiz } = await abrir();
    const busca = raiz.querySelector<HTMLInputElement>("#cfg-voz-grupo-xtts input.cards-busca")!;
    expect(busca).toBeTruthy();
    busca.value = "fictícia 01";
    busca.dispatchEvent(new Event("input"));
    const visiveis = [...raiz.querySelectorAll<HTMLElement>("#cfg-voz-grupo-xtts article.card")].filter((c) => !c.hidden);
    expect(visiveis.length).toBe(1);
    expect(visiveis[0].textContent).toContain("Fictícia 01");
  });

  it("escolher_voz_do_xtts_grava_como_hoje", async () => {
    const { raiz, aba } = await abrir();
    botao(cartao(raiz, "voz:neste-pc:XTTS:Suad Qasim"), "Usar esta").click();
    const lido = aba.ler();
    expect(lido.voz_provedor).toBe("propria");
    expect(lido.voz_motor).toBe("xtts");
    expect(lido.voz_propria).toBe("Suad Qasim");
    expect(cartao(raiz, "voz:neste-pc:XTTS:Suad Qasim").textContent).toContain("Em uso");
  });

  it("escolher_voz_kokoro_do_openjarvis_grava_o_voz", async () => {
    const { raiz, aba } = await abrir();
    botao(cartao(raiz, "voz:openjarvis:Kokoro:pm_alex"), "Usar esta").click();
    const lido = aba.ler();
    expect(lido.voz_provedor).toBe("openjarvis");
    expect(lido.voz).toBe("pm_alex");
    expect(lido.voz_propria).toBe("");
  });

  it("escolher_voz_kokoro_local_grava_motor_e_voz_propria", async () => {
    const { raiz, aba } = await abrir();
    const local = cartao(raiz, "voz:neste-pc:Kokoro:pf_dora");
    expect(local.querySelector(".card-etiqueta")!.textContent).toBe("Kokoro · neste PC");
    botao(local, "Usar esta").click();
    const lido = aba.ler();
    expect(lido.voz_provedor).toBe("propria");
    expect(lido.voz_motor).toBe("kokoro");
    expect(lido.voz_propria).toBe("pf_dora");
  });

  it("escolher_voz_de_nuvem_grava_o_campo_do_provedor", async () => {
    const { raiz, aba } = await abrir();
    botao(cartao(raiz, "voz:nuvem:Gemini:Puck"), "Usar esta").click();
    expect(aba.ler().voz_provedor).toBe("gemini");
    expect(aba.ler().gemini_voz).toBe("Puck");
  });

  it("voz_atual_ja_vem_com_o_selo_em_uso", async () => {
    const raiz = document.createElement("div");
    document.body.append(raiz);
    const aba = new AbaVoz(raiz, { ...CONFIG_PADRAO, voz_url: "http://127.0.0.1:4710", voz_provedor: "openjarvis", voz: "pm_alex" }, {
      criarOj: () => ojFalso, velocidade: () => 1, dizer: vi.fn(),
    });
    aba.montar();
    await aba.atualizar();
    expect(cartao(raiz, "voz:openjarvis:Kokoro:pm_alex").textContent).toContain("Em uso");
    expect(cartao(raiz, "voz:openjarvis:Kokoro:pf_dora").textContent).not.toContain("Em uso");
  });
});

describe("modal de voz cadastrada", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    paineisMem = null;
    vi.clearAllMocks();
    vi.stubGlobal("fetch", mockFetch);
  });

  it("adicionar_pelo_modal_grava_e_aparece_na_lista", async () => {
    const { raiz } = await abrir();
    raiz.querySelector<HTMLButtonElement>("#cfg-voz-adicionar")!.click();
    const c = camposModal();
    c.id.value = "aria";
    c.nome.value = "Ária";
    c.tipo.value = "fish";
    c.url.value = "http://127.0.0.1:9000";
    botaoModal("Salvar").click();
    await proximoTick();
    expect(document.querySelector(".modal")).toBeNull();
    expect(paineisMem!.provedores).toHaveLength(1);
    expect(paineisMem!.provedores[0]).toMatchObject({ id: "aria", nome: "Ária", tipo: "fish" });
    expect(cartao(raiz, "voz:cadastrada:Fish:aria").textContent).toContain("Ária");
    expect(cartao(raiz, "voz:cadastrada:Fish:aria").querySelector(".card-etiqueta")!.textContent).toBe("Fish · cadastrada");
  });

  it("editar_pelo_modal_atualiza_a_voz", async () => {
    paineisMem = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "aria", nome: "Ária", tipo: "fish", url_base: "http://127.0.0.1:9000", modelo: "fish-v1" }],
    };
    const { raiz } = await abrir();
    botao(cartao(raiz, "voz:cadastrada:Fish:aria"), "Editar").click();
    const c = camposModal();
    expect(c.id.value).toBe("aria");
    expect(c.id.readOnly).toBe(true);
    c.nome.value = "Ária Nova";
    botaoModal("Salvar").click();
    await proximoTick();
    expect(paineisMem!.provedores[0].nome).toBe("Ária Nova");
    expect(cartao(raiz, "voz:cadastrada:Fish:aria").textContent).toContain("Ária Nova");
    expect(gravacoes().some((c) => c.provedores[0]?.nome === "Ária Nova")).toBe(true);
  });

  it("remover_pelo_card_e_pelo_modal", async () => {
    const base: PaineisConfig = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "aria", nome: "Ária", tipo: "fish", url_base: "", modelo: "" },
        { id: "dub", nome: "Dub", tipo: "suad", url_base: "", modelo: "" },
      ],
    };
    paineisMem = { ...base, provedores: [...base.provedores] };
    const { raiz } = await abrir();
    botao(cartao(raiz, "voz:cadastrada:Fish:aria"), "Remover").click();
    await proximoTick();
    expect(paineisMem!.provedores.map((p) => p.id)).toEqual(["dub"]);
    botao(cartao(raiz, "voz:cadastrada:XTTS:dub"), "Editar").click();
    botaoModal("Remover").click();
    await proximoTick();
    expect(paineisMem!.provedores).toHaveLength(0);
    expect(document.querySelector(".modal")).toBeNull();
  });

  it("modal_recusa_id_duplicado_e_fica_aberto", async () => {
    paineisMem = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "aria", nome: "Ária", tipo: "fish", url_base: "", modelo: "" }],
    };
    const { raiz } = await abrir();
    raiz.querySelector<HTMLButtonElement>("#cfg-voz-adicionar")!.click();
    const c = camposModal();
    c.id.value = "aria";
    c.nome.value = "Outra";
    botaoModal("Salvar").click();
    await proximoTick();
    expect(modalAberto().textContent).toContain("Já existe uma voz");
    expect(paineisMem!.provedores).toHaveLength(1);
  });

  it("modal_recusa_campos_obrigatorios_vazios", async () => {
    const { raiz } = await abrir();
    raiz.querySelector<HTMLButtonElement>("#cfg-voz-adicionar")!.click();
    botaoModal("Salvar").click();
    await proximoTick();
    expect(modalAberto().textContent).toContain("Preencha todos os campos obrigatórios");
  });

  it("usar_uma_voz_cadastrada_grava_o_paineis_ativo", async () => {
    paineisMem = {
      ...PAINEIS_PADRAO,
      provedores: [{ id: "aria", nome: "Ária", tipo: "fish", url_base: "", modelo: "" }],
    };
    const { raiz } = await abrir();
    botao(cartao(raiz, "voz:cadastrada:Fish:aria"), "Usar esta").click();
    await proximoTick();
    expect(paineisMem!.ativo).toBe("aria");
    expect(gravacoes().some((c) => c.ativo === "aria")).toBe(true);
  });
});

describe("motores ausentes e serviço fora (U8)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    paineisMem = null;
    vi.clearAllMocks();
    vi.stubGlobal("fetch", mockFetch);
    estado = {
      saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: true, edge: true, piper: true },
      vozes: VOZES_XTTS,
    };
  });

  it("motor_ausente_mostra_card_de_instalar_sem_botao_para_motor_sem_pacote", async () => {
    estado = {
      saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: false, edge: false, piper: false },
      vozes: VOZES_XTTS,
    };
    const { raiz } = await abrir();
    for (const grupo of ["kokoro", "edge", "piper"]) {
      const bloco = raiz.querySelector<HTMLElement>(`#cfg-voz-grupo-${grupo}`)!;
      const cards = [...bloco.querySelectorAll<HTMLElement>("article.card")].filter((c) => c.textContent!.includes("Não instalado"));
      expect(cards.length, `card de instalar em ${grupo}`).toBe(1);
      expect(cards[0].querySelector(".card-acoes")).toBeNull();
      expect(cards[0].textContent).toContain("Não instalado neste PC");
    }
    // Kokoro continua disponível pelo OpenJarvis enquanto o motor local está ausente.
    expect(raiz.querySelector('#cfg-voz-grupo-kokoro article.card[data-id="voz:openjarvis:Kokoro:pm_alex"]')).toBeTruthy();
  });

  it("xtts_nao_instalado_mostra_o_botao_do_instalador_existente", async () => {
    estado = {
      saude: { pronta: true, voz: "", device: "cpu", aquecida: true, xtts: false, kokoro: true, edge: true, piper: true },
      vozes: [],
    };
    const { raiz } = await abrir();
    const instalador = document.createElement("div");
    instalador.id = "cfg-instalador-vozes";
    instalador.innerHTML = `<button data-acao="instalar" data-pkg="xtts-v2">Instalar</button>`;
    const clique = vi.fn();
    instalador.querySelector("button")!.addEventListener("click", clique);
    document.body.append(instalador);
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-grupo-xtts")!;
    const card = [...bloco.querySelectorAll<HTMLElement>("article.card")].find((c) => c.textContent!.includes("Não instalado"))!;
    expect(card, "card do XTTS não instalado").toBeTruthy();
    botao(card, "Instalar").click();
    expect(clique).toHaveBeenCalledTimes(1);
  });

  it("serviço_fora_mostra_aviso_no_topo_e_nao_lista_vazia", async () => {
    estado = { saude: null, vozes: null };
    const { raiz } = await abrir();
    const aviso = raiz.querySelector<HTMLElement>("#cfg-voz-aviso")!;
    expect(aviso.hidden).toBe(false);
    expect(aviso.textContent).toContain("Os serviços do Vard estão desligados");
    // nada de "não instalado" enganoso: o serviço é que está fora
    expect(raiz.textContent).not.toContain("Não instalado");
    expect(raiz.textContent).toContain("Serviço de voz fora do ar");
    // e a lista não fica vazia: as vozes do OpenJarvis continuam lá
    expect(raiz.querySelector('#cfg-voz-grupo-kokoro article.card[data-id="voz:openjarvis:Kokoro:pm_alex"]')).toBeTruthy();
  });

  it("serviço_no_ar_nao_mostra_aviso", async () => {
    const { raiz } = await abrir();
    expect(raiz.querySelector<HTMLElement>("#cfg-voz-aviso")!.hidden).toBe(true);
    expect(raiz.textContent).not.toContain("Serviço de voz fora do ar");
  });
});
