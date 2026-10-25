import { beforeEach, describe, expect, it, vi } from "vitest";
import { CONFIG_PADRAO, type Config } from "../src/config/config";
import { PAINEIS_PADRAO } from "../src/config/paineis";
import type { OpenJarvis } from "../src/conectores/openjarvis/cliente";
import { AbaVoz } from "../src/ui/aba-voz";
import { invoke } from "@tauri-apps/api/core";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => PAINEIS_PADRAO) }));

const buscar = vi.fn();
beforeEach(() => {
  document.body.replaceChildren();
  vi.stubGlobal("fetch", buscar);
  buscar.mockImplementation(async (url: string) => ({ ok: true, json: async () => url.endsWith("/saude")
    ? { xtts: true, kokoro: true, edge: true, piper: true, voz: "Voz Fictícia" }
    : { vozes: ["Voz Fictícia", "pm_alex", "pt-BR-FranciscaNeural", "pt_BR-feminina-medium"] } }));
});

async function abrir(extra: Partial<Config> = {}) {
  const raiz = document.createElement("div");
  document.body.append(raiz);
  const cfg = { ...CONFIG_PADRAO, voz_provedor: "propria" as const, voz_motor: "xtts", voz_propria: "Voz Fictícia", ...extra };
  const aba = new AbaVoz(raiz, cfg, { criarOj: () => ({} as OpenJarvis), velocidade: () => 1, dizer: vi.fn() });
  aba.montar();
  await aba.atualizar();
  return { raiz, aba, cfg };
}

describe("Quem fala", () => {
  it("pacote XTTS instalado com serviço fora não oferece instalar novamente", async () => {
    buscar.mockRejectedValue(new Error("serviço desligado"));
    const { raiz, aba } = await abrir({ voz_motor: "edge" });
    const instalar = vi.fn();
    aba.definirInstalador(instalar);
    aba.definirPacoteXttsInstalado(true);
    const card = raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!;
    expect(card.textContent).toContain("Instalado");
    expect(card.textContent).not.toContain("Instalar");
    card.click();
    expect(instalar).not.toHaveBeenCalled();
    expect(aba.ler().voz_motor).toBe("edge");
  });

  it("atualizar disponibilidade não apaga uma chave cadastrada durante a consulta", async () => {
    const { raiz, aba } = await abrir();
    let responder!: (r: Response) => void;
    buscar.mockImplementationOnce(() => new Promise<Response>((ok) => { responder = ok; }));
    const atualizando = aba.atualizar();
    raiz.querySelector<HTMLButtonElement>("#cfg-voz-chave-gemini")!.click();
    document.querySelector<HTMLInputElement>('.modal input[type="password"]')!.value = "credencial-ficticia";
    [...document.querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((b) => b.textContent === "Salvar")!.click();
    await new Promise((r) => setTimeout(r, 0));
    responder(new Response(JSON.stringify({ xtts: true, edge: true })));
    await atualizando;
    expect(aba.ler().gemini_chave).toBe("credencial-ficticia");
  });

  it("filtra também as vozes cadastradas e mantém o botão de cadastro", async () => {
    vi.mocked(invoke).mockResolvedValueOnce({ ...PAINEIS_PADRAO, provedores: [
      { id: "fish-ficticia", tipo: "fish", nome: "Voz Fish Fictícia", url_base: "", modelo: "" },
    ] });
    const { raiz } = await abrir();
    const cadastradas = raiz.querySelector<HTMLElement>("#cfg-voz-cadastradas")!;
    expect(cadastradas.textContent).not.toContain("Voz Fish Fictícia");
    expect(cadastradas.textContent).toContain("Adicionar voz");
    raiz.querySelector<HTMLButtonElement>('[data-motor="fish"]')!.click();
    expect(cadastradas.textContent).toContain("Voz Fish Fictícia");
  });

  it("começa a seção com os motores e destaca somente o ativo", async () => {
    const { raiz } = await abrir();
    expect(raiz.firstElementChild?.textContent).toContain("Quem fala");
    const ativo = raiz.querySelectorAll('[data-motor][aria-pressed="true"]');
    expect(ativo).toHaveLength(1);
    expect((ativo[0] as HTMLElement).dataset.motor).toBe("xtts");
    expect(ativo[0].textContent).toContain("Fala agora");
    for (const motor of ["xtts", "kokoro", "edge", "piper", "elevenlabs", "gemini", "fish"]) {
      expect(raiz.querySelector(`[data-motor="${motor}"]`)).toBeTruthy();
    }
  });

  it("troca o motor nos mesmos campos e filtra principal e reserva", async () => {
    const { raiz, aba, cfg } = await abrir();
    raiz.querySelector<HTMLButtonElement>('[data-motor="edge"]')!.click();
    const lida = aba.ler();
    expect(lida).toMatchObject({ voz_provedor: "propria", voz_motor: "edge", voz_propria: "pt-BR-FranciscaNeural" });
    expect(cfg.voz_motor).toBe("xtts"); // A configuração original só muda quando o painel salva.
    expect(raiz.querySelector('[data-motor="edge"]')?.getAttribute("aria-pressed")).toBe("true");
    for (const id of ["principal", "reserva"]) {
      const select = raiz.querySelector<HTMLSelectElement>(`#cfg-voz-${id}`)!;
      expect([...select.options].filter((o) => o.value).every((o) => o.value.startsWith("propria:edge:"))).toBe(true);
    }
  });

  it("exclui IDs de outros motores da lista XTTS devolvida pelo serviço", async () => {
    const { raiz } = await abrir();
    const valores = [...raiz.querySelector<HTMLSelectElement>("#cfg-voz-principal")!.options].map((o) => o.value);
    expect(valores).toEqual(["propria:xtts:Voz Fictícia"]);
  });

  it("mantém a reserva salva de outro motor até haver uma escolha explícita", async () => {
    const { raiz, aba } = await abrir({ voz_reserva_provedor: "gemini", voz_reserva_id: "Kore" });
    expect(aba.ler().voz_reserva_id).toBe("Kore");
    expect(raiz.querySelector<HTMLSelectElement>("#cfg-voz-reserva")!.selectedOptions[0].textContent).toContain("outro motor");
  });

  it("motor opcional ausente mostra Instalar e usa o instalador existente", async () => {
    buscar.mockImplementation(async () => ({ ok: true, json: async () => ({ xtts: false, edge: true, vozes: [] }) }));
    const { raiz, aba } = await abrir({ voz_motor: "edge" });
    const instalar = vi.fn();
    aba.definirInstalador(instalar);
    const card = raiz.querySelector<HTMLButtonElement>('[data-motor="xtts"]')!;
    expect(card.textContent).toContain("Instalar");
    card.click();
    expect(instalar).not.toHaveBeenCalled(); // primeiro pergunta
    await vi.waitFor(() => expect(document.querySelector(".modal")).toBeTruthy());
    [...document.querySelectorAll<HTMLButtonElement>(".modal-acoes button")].find((b) => b.textContent === "Instalar e usar")!.click();
    await vi.waitFor(() => expect(instalar).toHaveBeenCalledWith("xtts-v2", expect.anything()));
    expect(aba.ler().voz_motor).toBe("edge");
  });

  it("nuvem sem chave abre o modal de chave sem trocar o ativo", async () => {
    const { raiz, aba } = await abrir();
    const card = raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!;
    expect(card.textContent).toContain("Falta a chave");
    card.click();
    expect(aba.ler().voz_motor).toBe("xtts");
    expect(document.activeElement).toBe(document.querySelector('.modal input[type="password"]'));
  });

  it("troca para Gemini com chave e preserva a chave entre motores", async () => {
    const { raiz, aba } = await abrir({ gemini_chave: "credencial-ficticia" });
    raiz.querySelector<HTMLButtonElement>('[data-motor="gemini"]')!.click();
    expect(aba.ler()).toMatchObject({ voz_provedor: "gemini", gemini_voz: "Kore", gemini_chave: "credencial-ficticia" });
    raiz.querySelector<HTMLButtonElement>('[data-motor="edge"]')!.click();
    expect(aba.ler().gemini_chave).toBe("credencial-ficticia");
  });
});
