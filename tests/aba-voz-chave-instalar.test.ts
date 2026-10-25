/**
 * Seção Voz (0.9.7): voz de nuvem sem chave abre o modal de chave na hora; motor ausente pergunta
 * se quer instalar, instala pelo instalador existente e já deixa a voz escolhida. Chaves fictícias.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CONFIG_PADRAO, type Config } from "../src/config/config";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { OpenJarvis } from "../src/conectores/openjarvis/cliente";
import { AbaVoz } from "../src/ui/aba-voz";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => PAINEIS_PADRAO) }));

let saude: Record<string, unknown> = { xtts: true, kokoro: true, edge: true, piper: true };
let vozesServico: string[] = ["Voz Fictícia", "pt-BR-FranciscaNeural"];
const buscar = vi.fn(async (url: string) => {
  const u = String(url);
  const corpo = u.endsWith("/saude") ? saude
    : u.includes("/voices") ? { voices: [{ voice_id: "el-ficticia", name: "Voz Nuvem Fictícia" }] }
    : { vozes: vozesServico };
  return { ok: true, json: async () => corpo };
});

beforeEach(() => {
  document.body.replaceChildren();
  saude = { xtts: true, kokoro: true, edge: true, piper: true };
  vozesServico = ["Voz Fictícia", "pt-BR-FranciscaNeural"];
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

const modal = () => document.querySelector<HTMLElement>(".modal");
function botao(rotulo: string): HTMLButtonElement {
  const b = [...(modal()?.querySelectorAll<HTMLButtonElement>(".modal-acoes button") ?? [])].find((x) => x.textContent === rotulo);
  expect(b, `botão ${rotulo} no modal`).toBeTruthy();
  return b!;
}
const campoChave = () => modal()!.querySelector<HTMLInputElement>('input[type="password"]')!;
const esperar = () => new Promise((r) => setTimeout(r, 0));

describe("voz que precisa de chave abre o modal de cadastro", () => {
  it("a aba não tem mais campos de chave soltos no fim", async () => {
    const { raiz } = await abrir();
    expect(raiz.querySelector("#cfg-elevenlabs_chave")).toBeNull();
    expect(raiz.querySelector("#cfg-gemini_chave")).toBeNull();
    expect(raiz.querySelector('input[type="password"]')).toBeNull();
  });

  it("card Gemini sem chave abre o modal e, ao salvar, já escolhe o Gemini", async () => {
    const { raiz, aba } = await abrir();
    raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!.click();
    expect(modal()?.textContent).toContain("Gemini");
    campoChave().value = "chave-ficticia";
    botao("Salvar").click();
    await vi.waitFor(() => expect(aba.ler().voz_provedor).toBe("gemini"));
    expect(aba.ler()).toMatchObject({ gemini_chave: "chave-ficticia", gemini_voz: "Kore" });
    expect(modal()).toBeNull();
  });

  it("cancelar o modal sem chave mantém a voz anterior", async () => {
    const { raiz, aba } = await abrir();
    raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!.click();
    botao("Cancelar").click();
    await esperar();
    expect(modal()).toBeNull();
    expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "xtts", voz_propria: "Voz Fictícia", gemini_chave: "" });
  });

  it("salvar com a chave vazia avisa e mantém o modal aberto", async () => {
    const { raiz } = await abrir();
    raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!.click();
    botao("Salvar").click();
    await esperar();
    expect(modal()?.textContent).toContain("Informe a chave");
  });

  it("com chave já cadastrada não abre o modal", async () => {
    const { raiz, aba } = await abrir({ gemini_chave: "chave-ficticia" });
    raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!.click();
    expect(modal()).toBeNull();
    expect(aba.ler().voz_provedor).toBe("gemini");
  });

  it("ElevenLabs: salvar a chave carrega as vozes da conta e escolhe uma", async () => {
    const { raiz, aba } = await abrir();
    raiz.querySelector<HTMLButtonElement>('[data-motor="elevenlabs"]')!.click();
    expect(modal()?.textContent).toContain("ElevenLabs");
    campoChave().value = "chave-ficticia";
    botao("Salvar").click();
    await vi.waitFor(() => expect(aba.ler().voz_provedor).toBe("elevenlabs"));
    expect(aba.ler()).toMatchObject({ elevenlabs_chave: "chave-ficticia", elevenlabs_voz: "el-ficticia" });
  });

  it("voz principal de nuvem sem chave no select abre o modal; cancelar volta à anterior", async () => {
    const { raiz, aba } = await abrir({ voz_provedor: "gemini", gemini_voz: "Kore", gemini_chave: "" });
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    sel.value = "gemini:Puck";
    sel.dispatchEvent(new Event("change"));
    expect(modal()).toBeTruthy();
    botao("Cancelar").click();
    await esperar();
    expect(sel.value).toBe("gemini:Kore");
    expect(aba.ler().gemini_voz).toBe("Kore");
  });

  it("voz principal de nuvem sem chave no select: salvar a chave aplica a escolha", async () => {
    const { raiz, aba } = await abrir({ voz_provedor: "gemini", gemini_voz: "Kore", gemini_chave: "" });
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!;
    sel.value = "gemini:Puck";
    sel.dispatchEvent(new Event("change"));
    campoChave().value = "chave-ficticia";
    botao("Salvar").click();
    await vi.waitFor(() => expect(aba.ler().gemini_voz).toBe("Puck"));
    expect(aba.ler().gemini_chave).toBe("chave-ficticia");
    expect(sel.value).toBe("gemini:Puck");
  });

  it("voz de reserva de nuvem sem chave também abre o modal; cancelar volta à anterior", async () => {
    const { raiz, aba } = await abrir({ voz_provedor: "gemini", gemini_voz: "Kore", gemini_chave: "" });
    const antes = aba.ler();
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!;
    sel.value = "gemini:Puck";
    sel.dispatchEvent(new Event("change"));
    expect(modal()).toBeTruthy();
    botao("Cancelar").click();
    await esperar();
    expect(sel.value).toBe("");
    expect(aba.ler()).toMatchObject({ voz_reserva_provedor: antes.voz_reserva_provedor, voz_reserva_id: antes.voz_reserva_id });
  });

  it("voz de reserva de nuvem: salvar a chave grava a reserva", async () => {
    const { raiz, aba } = await abrir({ voz_provedor: "gemini", gemini_voz: "Kore", gemini_chave: "" });
    const sel = raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!;
    sel.value = "gemini:Puck";
    sel.dispatchEvent(new Event("change"));
    campoChave().value = "chave-ficticia";
    botao("Salvar").click();
    await vi.waitFor(() => expect(aba.ler().voz_reserva_provedor).toBe("gemini"));
    expect(aba.ler()).toMatchObject({ voz_reserva_id: "Puck", gemini_chave: "chave-ficticia" });
  });

  it("trocar a chave pelo bloco de serviços usa o mesmo modal e não muda a voz", async () => {
    const { raiz, aba } = await abrir({ gemini_chave: "chave-antiga-ficticia" });
    const trocar = raiz.querySelector<HTMLButtonElement>("#cfg-voz-chave-gemini")!;
    expect(trocar.textContent).toContain("Trocar chave");
    trocar.click();
    campoChave().value = "chave-nova-ficticia";
    botao("Salvar").click();
    await esperar();
    expect(aba.ler()).toMatchObject({ gemini_chave: "chave-nova-ficticia", voz_provedor: "propria", voz_motor: "xtts" });
  });
});

describe("voz não instalada pergunta e instala pelo instalador existente", () => {
  const PACOTE = { nome: "XTTS-v2 fictício", licenca_nome: "Licença Fictícia", licenca_url: "https://example.com/licenca", bytes_download: 2048 };

  it("recusar a instalação mantém a voz anterior e não chama o instalador", async () => {
    saude = { xtts: false, edge: true };
    const { raiz, aba } = await abrir({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    const instalar = vi.fn(async () => true);
    aba.definirInstalador(instalar, () => PACOTE);
    raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!.click();
    await vi.waitFor(() => expect(modal()).toBeTruthy());
    expect(modal()?.textContent).toContain("Instalar");
    expect(modal()?.textContent).toContain("Licença Fictícia");
    botao("Agora não").click();
    await esperar();
    expect(instalar).not.toHaveBeenCalled();
    expect(aba.ler()).toMatchObject({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
  });

  it("confirmar instala com a licença aceita e, ao terminar, já escolhe o XTTS", async () => {
    saude = { xtts: false, edge: true };
    const { raiz, aba } = await abrir({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    let concluir!: (ok: boolean) => void;
    const instalar = vi.fn(() => new Promise<boolean>((ok) => { concluir = ok; }));
    aba.definirInstalador(instalar, () => PACOTE);
    raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!.click();
    await vi.waitFor(() => expect(modal()).toBeTruthy());
    botao("Instalar e usar").click();
    await vi.waitFor(() => expect(instalar).toHaveBeenCalledWith("xtts-v2", { licencaAceita: true }));
    expect(raiz.querySelector('[data-motor="xtts"]')?.textContent).toContain("Instalando");
    expect(aba.ler().voz_motor).toBe("edge");
    saude = { xtts: true, edge: true };
    concluir(true);
    await vi.waitFor(() => expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "xtts", voz_propria: "Voz Fictícia" }));
    expect(raiz.querySelector('[data-motor="xtts"]')?.getAttribute("aria-pressed")).toBe("true");
  });

  it("instalado mas o serviço ainda sem o motor: escolhe o XTTS e avisa", async () => {
    saude = { xtts: false, edge: true };
    const { raiz, aba, dizer } = await abrir({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    aba.definirInstalador(async () => true, () => PACOTE);
    raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!.click();
    await vi.waitFor(() => expect(modal()).toBeTruthy());
    botao("Instalar e usar").click();
    await vi.waitFor(() => expect(aba.ler()).toMatchObject({ voz_provedor: "propria", voz_motor: "xtts" }));
    expect(dizer).toHaveBeenCalledWith(expect.stringContaining("XTTS instalado"));
    expect(raiz.querySelector('[data-motor="xtts"]')?.getAttribute("aria-pressed")).toBe("true");
  });

  it("instalação que não conclui (licença recusada, falha ou cancelada) mantém a voz anterior", async () => {
    saude = { xtts: false, edge: true };
    const { raiz, aba } = await abrir({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    const instalar = vi.fn(async () => false);
    aba.definirInstalador(instalar);
    raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!.click();
    await vi.waitFor(() => expect(modal()).toBeTruthy());
    botao("Instalar e usar").click();
    await vi.waitFor(() => expect(instalar).toHaveBeenCalledWith("xtts-v2", { licencaAceita: false }));
    await esperar();
    expect(aba.ler()).toMatchObject({ voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    expect(raiz.querySelector('[data-motor="xtts"]')?.textContent).toContain("Instalar");
  });
});
