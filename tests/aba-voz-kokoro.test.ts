/**
 * Seção Voz (0.9.7): o Kokoro é motor do serviço de voz do Vard, sem OpenJarvis. Card sem "Via OpenJarvis",
 * vozes vindas do serviço, instalação pelo instalador de vozes e compatibilidade com a config antiga
 * (provedor openjarvis + voz Kokoro). Serviço e instalador falsos; nada é baixado nem tocado.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CONFIG_PADRAO, type Config } from "../src/config/config";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { OpenJarvis } from "../src/conectores/openjarvis/cliente";
import { AbaVoz } from "../src/ui/aba-voz";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => PAINEIS_PADRAO) }));

let saude: Record<string, unknown>;
let vozes: Record<string, unknown>;
const buscar = vi.fn(async (url: string) => {
  const corpo = String(url).endsWith("/saude") ? saude : vozes;
  return { ok: true, json: async () => corpo };
});

beforeEach(() => {
  document.body.replaceChildren();
  saude = { pronta: true, xtts: true, kokoro: true, edge: true, piper: false };
  vozes = {
    vozes: ["Voz Fictícia", "pm_alex", "pm_santa", "pt-BR-FranciscaNeural"],
    atual: "Voz Fictícia",
    por_motor: { xtts: ["Voz Fictícia"], kokoro: ["pm_alex", "pm_santa"], edge: ["pt-BR-FranciscaNeural"] },
  };
  buscar.mockClear();
  vi.stubGlobal("fetch", buscar);
});

async function abrir(extra: Partial<Config> = {}) {
  const raiz = document.createElement("div");
  document.body.append(raiz);
  const dizer = vi.fn();
  const cfg = { ...CONFIG_PADRAO, voz_url: "http://127.0.0.1:4710", voz_provedor: "propria" as const, voz_motor: "xtts", voz_propria: "Voz Fictícia", ...extra };
  const aba = new AbaVoz(raiz, cfg, { criarOj: () => ({} as OpenJarvis), velocidade: () => 1, dizer });
  aba.montar();
  await aba.atualizar();
  return { raiz, aba, dizer };
}

const card = (raiz: HTMLElement) => raiz.querySelector<HTMLButtonElement>('[data-motor="kokoro"]')!;
const valores = (raiz: HTMLElement, id: "principal" | "reserva") =>
  [...raiz.querySelector<HTMLSelectElement>(`#cfg-voz-${id}`)!.options].map((o) => o.value);
const modal = () => document.querySelector<HTMLElement>(".modal");
function botao(rotulo: string): HTMLButtonElement {
  const b = [...(modal()?.querySelectorAll<HTMLButtonElement>(".modal-acoes button") ?? [])].find((x) => x.textContent === rotulo);
  expect(b, `botão ${rotulo} no modal`).toBeTruthy();
  return b!;
}
const PACOTE = { nome: "Kokoro fictício", licenca_nome: "Apache-2.0", licenca_url: "https://example.com/licenca", bytes_download: 1024 };

describe("Kokoro pelo serviço de voz do Vard", () => {
  it("o card não fala mais em OpenJarvis", async () => {
    saude = { ...saude, kokoro: false };
    const { raiz } = await abrir();
    expect(card(raiz).textContent).not.toContain("OpenJarvis");
    expect(card(raiz).textContent).toContain("Instalar");
  });

  it("com o Kokoro no serviço o card fica disponível", async () => {
    const { raiz } = await abrir();
    expect(card(raiz).textContent).toContain("Disponível · serviço de voz");
  });

  it("as vozes do Kokoro vêm do serviço de voz, com o nome legível", async () => {
    const { raiz, aba } = await abrir();
    card(raiz).click();
    expect(valores(raiz, "principal")).toEqual(["propria:kokoro:pm_alex", "propria:kokoro:pm_santa"]);
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    expect(sel.selectedOptions[0].textContent).toContain("Alex (pt-BR, masculina)");
    expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "kokoro", voz_propria: "pm_alex" });
  });

  it("nenhuma opção da lista passa pelo OpenJarvis", async () => {
    const { raiz } = await abrir({ voz_motor: "kokoro", voz_propria: "pm_alex" });
    for (const id of ["principal", "reserva"] as const) {
      expect(valores(raiz, id).some((v) => v.startsWith("openjarvis:"))).toBe(false);
    }
  });

  it("serviço antigo sem por_motor: usa as vozes Kokoro conhecidas que ele lista", async () => {
    vozes = { vozes: ["Voz Fictícia", "pf_dora"], atual: "Voz Fictícia" };
    const { raiz } = await abrir({ voz_motor: "kokoro", voz_propria: "pf_dora" });
    expect(valores(raiz, "principal")).toEqual(["propria:kokoro:pf_dora"]);
  });

  it("escolher Kokoro sem ele instalado pergunta, instala o pacote kokoro e já escolhe a voz", async () => {
    saude = { ...saude, kokoro: false };
    vozes = { vozes: ["Voz Fictícia"], atual: "Voz Fictícia", por_motor: { xtts: ["Voz Fictícia"] } };
    const { raiz, aba, dizer } = await abrir();
    let concluir!: (ok: boolean) => void;
    const instalar = vi.fn(() => new Promise<boolean>((ok) => { concluir = ok; }));
    aba.definirInstalador(instalar, () => PACOTE);
    card(raiz).click();
    await vi.waitFor(() => expect(modal()?.textContent).toContain("Instalar Kokoro?"));
    expect(modal()?.textContent).toContain("Apache-2.0");
    botao("Instalar e usar").click();
    await vi.waitFor(() => expect(instalar).toHaveBeenCalledWith("kokoro", { licencaAceita: true }));
    expect(card(raiz).textContent).toContain("Instalando");
    saude = { ...saude, kokoro: true };
    vozes = { vozes: ["Voz Fictícia", "pf_dora"], atual: "Voz Fictícia", por_motor: { xtts: ["Voz Fictícia"], kokoro: ["pf_dora"] } };
    concluir(true);
    await vi.waitFor(() => expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "kokoro", voz_propria: "pf_dora" }));
    expect(card(raiz).getAttribute("aria-pressed")).toBe("true");
    expect(dizer).toHaveBeenCalledWith(expect.stringContaining("Kokoro instalado"));
  });

  it("pacote kokoro instalado com o serviço ainda sem ele não oferece instalar de novo", async () => {
    saude = { ...saude, kokoro: false };
    const { raiz, aba } = await abrir();
    const instalar = vi.fn();
    aba.definirInstalador(instalar);
    aba.definirPacoteInstalado("kokoro", true);
    expect(card(raiz).textContent).toContain("Instalado");
    expect(card(raiz).textContent).not.toContain("Instalar");
    card(raiz).click();
    expect(instalar).not.toHaveBeenCalled();
  });
});

describe("config antiga: Kokoro pelo OpenJarvis", () => {
  const ANTIGA = { voz_provedor: "openjarvis" as const, voz_motor: "", voz_propria: "", voz: "pm_alex" };

  it("com o Kokoro instalado no serviço passa a usar o Kokoro do serviço, mesma voz", async () => {
    const { raiz, aba } = await abrir(ANTIGA);
    expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "kokoro", voz_propria: "pm_alex" });
    expect(card(raiz).getAttribute("aria-pressed")).toBe("true");
    expect(raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!.value).toBe("propria:kokoro:pm_alex");
  });

  it("a reserva antiga pelo OpenJarvis também passa para o Kokoro do serviço", async () => {
    const { aba } = await abrir({ voz_reserva_provedor: "openjarvis", voz_reserva_motor: "", voz_reserva_id: "pm_santa" });
    expect(aba.ler()).toMatchObject({ voz_reserva_provedor: "propria", voz_reserva_motor: "kokoro", voz_reserva_id: "pm_santa" });
  });

  it("sem o Kokoro no serviço mantém a config, marca o Kokoro e oferece instalar", async () => {
    saude = { ...saude, kokoro: false };
    vozes = { vozes: ["Voz Fictícia"], atual: "Voz Fictícia", por_motor: { xtts: ["Voz Fictícia"] } };
    const { raiz, aba } = await abrir(ANTIGA);
    expect(aba.ler()).toMatchObject({ voz_provedor: "openjarvis", voz: "pm_alex" });
    expect(card(raiz).getAttribute("aria-pressed")).toBe("true");
    expect(card(raiz).textContent).toContain("Instalar");
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    expect(sel.selectedOptions[0].textContent).toContain("Alex");
    const instalar = vi.fn(async () => {
      saude = { ...saude, kokoro: true };
      vozes = { vozes: ["Voz Fictícia", "pm_alex"], atual: "Voz Fictícia", por_motor: { xtts: ["Voz Fictícia"], kokoro: ["pf_dora", "pm_alex"] } };
      return true;
    });
    aba.definirInstalador(instalar, () => PACOTE);
    card(raiz).click();
    await vi.waitFor(() => expect(modal()).toBeTruthy());
    botao("Instalar e usar").click();
    await vi.waitFor(() => expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "kokoro", voz_propria: "pm_alex" }));
  });
});
