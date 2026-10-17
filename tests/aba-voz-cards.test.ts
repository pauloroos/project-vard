/**
 * @vitest-environment jsdom
 */
/**
 * Testes da seção Voz (0.9.4): listas de seleção principal/reserva com botão Ouvir amostra,
 * blocos de serviço claros, cadastro em modal e reserva automática.
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

describe("listas de seleção principal e reserva (0.9.4)", () => {
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

  it("select_principal_contem_opcoes_de_todos_os_motores", async () => {
    const { raiz } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    expect(sel).toBeTruthy();
    const grupos = [...sel.querySelectorAll("optgroup")].map((g) => g.label);
    expect(grupos.some((g) => g.includes("XTTS"))).toBe(true);
    expect(grupos.some((g) => g.includes("Kokoro"))).toBe(true);
    expect(grupos.some((g) => g.includes("Edge"))).toBe(true);
    expect(grupos.some((g) => g.includes("Piper"))).toBe(true);
  });

  it("select_reserva_tem_opcao_nenhuma_e_as_mesmas_vozes", async () => {
    const { raiz } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!;
    expect(sel).toBeTruthy();
    const primeira = sel.options[0];
    expect(primeira.value).toBe("");
    expect(primeira.textContent).toContain("Nenhuma");
    const grupos = [...sel.querySelectorAll("optgroup")].map((g) => g.label);
    expect(grupos.some((g) => g.includes("Kokoro"))).toBe(true);
  });

  it("escolher_voz_no_select_principal_grava_na_config", async () => {
    const { raiz, aba } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    const opcao = [...sel.options].find((o) => o.value.startsWith("propria:xtts:Suad"));
    expect(opcao).toBeTruthy();
    sel.value = opcao!.value;
    sel.dispatchEvent(new Event("change"));
    const lido = aba.ler();
    expect(lido.voz_provedor).toBe("propria");
    expect(lido.voz_motor).toBe("xtts");
    expect(lido.voz_propria).toBe("Suad Qasim");
  });

  it("escolher_openjarvis_no_select_principal_grava_voz_e_provedor", async () => {
    const { raiz, aba } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    const opcao = [...sel.options].find((o) => o.value.startsWith("openjarvis:pm_alex"));
    expect(opcao).toBeTruthy();
    sel.value = opcao!.value;
    sel.dispatchEvent(new Event("change"));
    const lido = aba.ler();
    expect(lido.voz_provedor).toBe("openjarvis");
    expect(lido.voz).toBe("pm_alex");
  });

  it("escolher_reserva_grava_campos_de_reserva_na_config", async () => {
    const { raiz, aba } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!;
    const opcao = [...sel.options].find((o) => o.value.startsWith("openjarvis:pf_dora"));
    expect(opcao).toBeTruthy();
    sel.value = opcao!.value;
    sel.dispatchEvent(new Event("change"));
    const lido = aba.ler();
    expect(lido.voz_reserva_provedor).toBe("openjarvis");
    expect(lido.voz_reserva_id).toBe("pf_dora");
  });

  it("reserva_nenhuma_limpa_campos_de_reserva", async () => {
    const { raiz, aba } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!;
    sel.value = "";
    sel.dispatchEvent(new Event("change"));
    const lido = aba.ler();
    expect(lido.voz_reserva_provedor).toBe("nenhuma");
    expect(lido.voz_reserva_id).toBe("");
  });

  it("botao_amostra_principal_existe_e_chama_dizer", async () => {
    const { raiz, dizer } = await abrir();
    const btn = raiz.querySelector<HTMLButtonElement>("#cfg-voz-amostra-principal")!;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain("Ouvir amostra");
    // Com serviço no ar, o select tem valor padrão e a amostra tenta sintetizar
    btn.click();
    expect(dizer).toHaveBeenCalledWith("Sintetizando...");
  });

  it("botao_amostra_reserva_existe", async () => {
    const { raiz } = await abrir();
    const btn = raiz.querySelector<HTMLButtonElement>("#cfg-voz-amostra-reserva")!;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain("Ouvir amostra");
  });
});

describe("blocos de serviço (0.9.4)", () => {
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

  it("bloco_servico_local_mostra_endereco_e_estado", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-servicos")!;
    expect(bloco).toBeTruthy();
    expect(bloco.textContent).toContain("Serviço de voz deste PC");
    expect(bloco.textContent).toContain("Endereço do serviço de voz");
    expect(bloco.textContent).toContain("Serviço de voz no ar");
    const input = bloco.querySelector<HTMLInputElement>("#cfg-voz_url")!;
    expect(input).toBeTruthy();
    expect(input.value).toBe("http://127.0.0.1:4710");
  });

  it("bloco_elevenlabs_tem_chave_e_botao_carregar", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-servicos")!;
    expect(bloco.textContent).toContain("ElevenLabs");
    expect(bloco.querySelector("#cfg-elevenlabs_chave")).toBeTruthy();
    expect(bloco.querySelector("#cfg-voz-carregar-elevenlabs")).toBeTruthy();
  });

  it("bloco_gemini_tem_chave", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-servicos")!;
    expect(bloco.textContent).toContain("Gemini");
    expect(bloco.querySelector("#cfg-gemini_chave")).toBeTruthy();
  });

  it("servico_fora_mostra_aviso_no_topo", async () => {
    estado = { saude: null, vozes: null };
    const { raiz } = await abrir();
    const aviso = raiz.querySelector<HTMLElement>("#cfg-voz-aviso")!;
    expect(aviso.hidden).toBe(false);
    expect(aviso.textContent).toContain("Os serviços do Vard estão desligados");
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-servicos")!;
    expect(bloco.textContent).toContain("Serviço de voz fora do ar");
  });

  it("servico_desligado_mostra_aviso_e_estado_no_bloco", async () => {
    const { raiz, aba } = criarAba();
    // cfg sem voz_url → estado desligado
    (aba as unknown as { cfg: typeof CONFIG_PADRAO }).cfg.voz_url = "";
    await aba.atualizar();
    const aviso = raiz.querySelector<HTMLElement>("#cfg-voz-aviso")!;
    expect(aviso.hidden).toBe(false);
    expect(aviso.textContent).toContain("O serviço de voz está desligado");
  });
});

describe("vozes cadastradas (modal)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    paineisMem = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "fish-aria", nome: "Aria", tipo: "fish", url_base: "http://localhost:9999", modelo: "aria-v1" },
      ],
    };
    vi.clearAllMocks();
    vi.stubGlobal("fetch", mockFetch);
    estado = {
      saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: true, edge: true, piper: true },
      vozes: VOZES_XTTS,
    };
  });

  it("voz_cadastrada_aparece_na_lista_de_selecao", async () => {
    const { raiz } = await abrir();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    const opcao = [...sel.options].find((o) => o.value === "cadastrada:fish-aria");
    expect(opcao).toBeTruthy();
    expect(opcao!.textContent).toContain("Aria");
  });

  it("voz_cadastrada_aparece_no_bloco_de_cadastradas_com_botao_editar", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    expect(bloco).toBeTruthy();
    expect(bloco.textContent).toContain("Aria");
    expect(bloco.textContent).toContain("Editar");
  });

  it("botao_adicionar_voz_abre_modal", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const btnAdd = [...bloco.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Adicionar voz");
    expect(btnAdd).toBeTruthy();
    btnAdd!.click();
    const modal = document.querySelector<HTMLElement>(".modal");
    expect(modal).toBeTruthy();
  });
});

describe("detector e interrupção (Ouvido)", () => {
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

  it("campos_vad_e_interromper_existem_no_dom", async () => {
    const { raiz } = await abrir();
    const vad = raiz.querySelector<HTMLSelectElement>("#cfg-vad");
    expect(vad).toBeTruthy();
    const inter = raiz.querySelector<HTMLInputElement>("#cfg-interromper_ao_falar");
    expect(inter).toBeTruthy();
  });

  it("ler_retorna_vad_e_interromper_do_formulario", async () => {
    const { raiz, aba } = await abrir();
    const vad = raiz.querySelector<HTMLSelectElement>("#cfg-vad")!;
    vad.value = "silero";
    const inter = raiz.querySelector<HTMLInputElement>("#cfg-interromper_ao_falar")!;
    inter.checked = true;
    const lido = aba.ler();
    expect(lido.vad).toBe("silero");
    expect(lido.interromper_ao_falar).toBe(true);
  });
});

describe("modal de voz cadastrada (0.9.4 rodada 2)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    paineisMem = {
      ...PAINEIS_PADRAO,
      provedores: [
        { id: "fish-aria", nome: "Aria", tipo: "fish", url_base: "http://localhost:9999", modelo: "aria-v1" },
      ],
    };
    vi.clearAllMocks();
    vi.stubGlobal("fetch", mockFetch);
    estado = {
      saude: { pronta: true, voz: "Suad Qasim", device: "cpu", aquecida: true, xtts: true, kokoro: true, edge: true, piper: true },
      vozes: VOZES_XTTS,
    };
  });

  function modalAberto(): HTMLElement {
    const m = document.querySelector<HTMLElement>(".modal");
    expect(m, "modal aberto").toBeTruthy();
    return m!;
  }

  function camposModal() {
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

  function botaoModal(rotulo: string): HTMLButtonElement {
    const m = modalAberto();
    const b = [...m.querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((x) => x.textContent === rotulo);
    expect(b, `botão do modal ${rotulo}`).toBeTruthy();
    return b!;
  }

  it("editar_pelo_modal_atualiza_a_voz", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const btnEditar = [...bloco.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Editar");
    expect(btnEditar).toBeTruthy();
    btnEditar!.click();
    const campos = camposModal();
    expect(campos.id.value).toBe("fish-aria");
    campos.nome.value = "Aria Atualizada";
    botaoModal("Salvar").click();
    await new Promise((r) => setTimeout(r, 0));
    expect(paineisMem?.provedores.find((p) => p.id === "fish-aria")?.nome).toBe("Aria Atualizada");
  });

  it("remover_pelo_modal_remove_a_voz", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const btnEditar = [...bloco.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Editar");
    expect(btnEditar).toBeTruthy();
    btnEditar!.click();
    const btnRemover = [...modalAberto().querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((b) => b.textContent === "Remover");
    expect(btnRemover).toBeTruthy();
    btnRemover!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(paineisMem?.provedores.find((p) => p.id === "fish-aria")).toBeUndefined();
  });

  it("modal_recusa_id_duplicado_e_fica_aberto", async () => {
    paineisMem!.provedores.push({ id: "fish-dup", nome: "Dup", tipo: "fish", url_base: "", modelo: "" });
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const btnAdd = [...bloco.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Adicionar voz");
    btnAdd!.click();
    const campos = camposModal();
    campos.id.value = "fish-aria"; // duplicado
    campos.nome.value = "Nova";
    campos.tipo.value = "fish";
    botaoModal("Salvar").click();
    await new Promise((r) => setTimeout(r, 0));
    // Modal ainda aberto com aviso de erro
    expect(document.querySelector(".modal")).toBeTruthy();
    expect(modalAberto().textContent).toContain("Já existe");
  });

  it("modal_recusa_campos_obrigatorios_vazios", async () => {
    const { raiz } = await abrir();
    const bloco = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    const btnAdd = [...bloco.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Adicionar voz");
    btnAdd!.click();
    const campos = camposModal();
    campos.id.value = "";
    campos.nome.value = "";
    campos.tipo.value = "fish";
    botaoModal("Salvar").click();
    await new Promise((r) => setTimeout(r, 0));
    expect(document.querySelector(".modal")).toBeTruthy();
    expect(modalAberto().textContent).toContain("Preencha");
  });
});