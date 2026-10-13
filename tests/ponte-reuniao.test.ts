import { describe, it, expect, vi, afterEach } from "vitest";
import { Ponte, FRASE_REUNIAO_AUSENTE } from "../src/conectores/ponte/cliente";

const BASE = "http://127.0.0.1:4700";

function responder(corpo: unknown, status = 200): Response {
  return new Response(typeof corpo === "string" ? corpo : JSON.stringify(corpo), { status });
}

describe("Ponte.status (reunião)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("le_o_campo_reuniao", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ openjarvis: true, lmstudio: true, modo: "ligado", reuniao: "ativa" })));
    expect((await new Ponte(BASE).status())?.reuniao).toBe("ativa");
  });

  it("reuniao_invalida_ou_ausente_fica_fora_do_tipo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ openjarvis: true, lmstudio: true, modo: "ligado", reuniao: "qualquer" })));
    expect((await new Ponte(BASE).status())?.reuniao).toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(async () => responder({ openjarvis: true, lmstudio: true, modo: "ligado" })));
    expect((await new Ponte(BASE).status())?.reuniao).toBeUndefined();
  });
});

describe("Ponte.reuniaoStatus", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("devolve_o_estado", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ativa: true, pasta: "2026-10-13_1500", inicio: "2026-10-13T15:00:00", duracao_s: 65, falas: 3 })));
    expect(await new Ponte(BASE).reuniaoStatus()).toEqual({ ativa: true, pasta: "2026-10-13_1500", inicio: "2026-10-13T15:00:00", duracao_s: 65, falas: 3 });
  });

  it("preenche_o_resto_com_padrao_e_ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ativa: false })));
    expect(await new Ponte(BASE).reuniaoStatus()).toEqual({ ativa: false });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    expect(await new Ponte(BASE).reuniaoStatus()).toBeNull();
    expect(await new Ponte("").reuniaoStatus()).toBeNull(); // ponte_url vazio nem tenta a rede
  });
});

describe("Ponte.iniciarReuniao / encerrarReuniao", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("200_devolve_ok_com_a_frase_da_ponte_ou_o_padrao", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => { urls.push(url); return responder({ ok: true, frase: "Reunião lá vai." }); }));
    expect(await new Ponte(BASE).iniciarReuniao()).toEqual({ ok: true, frase: "Reunião lá vai." });
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ok: true })));
    expect(await new Ponte(BASE).encerrarReuniao()).toEqual({ ok: true, frase: "Reunião encerrada." });
    expect(urls).toEqual([`${BASE}/reuniao/iniciar`]);
  });

  it("409_de_ja_ativa_usa_a_frase_ou_o_padrao", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ok: false, erro: "ja_ativa" }, 409)));
    expect(await new Ponte(BASE).iniciarReuniao()).toEqual({ ok: false, frase: "Já há uma reunião em andamento." });
    vi.stubGlobal("fetch", vi.fn(async () => responder({ frase: "Não há nada a encerrar." }, 409)));
    expect(await new Ponte(BASE).encerrarReuniao()).toEqual({ ok: false, frase: "Não há nada a encerrar." });
  });

  it("503_vira_a_frase_de_reuniao_ausente_e_ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ erro: "reuniao_ausente" }, 503)));
    expect(await new Ponte(BASE).iniciarReuniao()).toEqual({ ok: false, frase: FRASE_REUNIAO_AUSENTE });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("sem rede"); }));
    expect(await new Ponte(BASE).encerrarReuniao()).toBeNull();
    expect(await new Ponte("").iniciarReuniao()).toBeNull();
  });
});

describe("Ponte.listaReuniao", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normaliza_os_campos_e_pergunta_pelo_n", async () => {
    let url = "";
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      url = u;
      return responder([{ pasta: "2026-10-13_1500", inicio: "2026-10-13T15:00:00", fim: "2026-10-13T16:05:00", duracao_s: 3900, ata: true, relatorio: false, diarizada: true }]);
    }));
    expect(await new Ponte(BASE).listaReuniao(1)).toEqual([
      { pasta: "2026-10-13_1500", inicio: "2026-10-13T15:00:00", fim: "2026-10-13T16:05:00", duracao_s: 3900, ata: true, relatorio: false },
    ]);
    expect(url).toBe(`${BASE}/reuniao/lista?n=1`);
  });

  it("aceita_ata_como_caminho_e_item_invalido_vira_padrao", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder([{}, { ata: "docs/ata.md", relatorio: "", duracao_s: "x" }])));
    expect(await new Ponte(BASE).listaReuniao()).toEqual([
      { pasta: "", inicio: "", fim: "", duracao_s: 0, ata: false, relatorio: false },
      { pasta: "", inicio: "", fim: "", duracao_s: 0, ata: true, relatorio: false },
    ]);
  });

  it("ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder("no", 500)));
    expect(await new Ponte(BASE).listaReuniao(2)).toBeNull();
    expect(await new Ponte("").listaReuniao()).toBeNull();
  });
});

describe("Ponte.gerarAta", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("manda_tipo_e_qual_e_devolve_a_frase", async () => {
    const corpos: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      corpos.push(`${url} ${String(init?.body)}`);
      return responder({ ok: true, n: 4, frase: "Ata pronta na pasta." });
    }));
    expect(await new Ponte(BASE).gerarAta("ata")).toEqual({ ok: true, frase: "Ata pronta na pasta." });
    expect(corpos).toEqual([`${BASE}/reuniao/ata {"tipo":"ata","qual":"ultima"}`]);
  });

  it("404_e_409_usam_a_frase_da_ponte", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ok: false, frase: "Não achei nenhuma reunião." }, 404)));
    expect(await new Ponte(BASE).gerarAta("ata")).toEqual({ ok: false, frase: "Não achei nenhuma reunião." });
    vi.stubGlobal("fetch", vi.fn(async () => responder({ ok: false, frase: "A reunião ainda está em andamento." }, 409)));
    expect(await new Ponte(BASE).gerarAta("relatorio", "ultima")).toEqual({ ok: false, frase: "A reunião ainda está em andamento." });
  });

  it("503_vira_reuniao_ausente_e_ponte_fora_devolve_null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => responder({ erro: "reuniao_ausente" }, 503)));
    expect(await new Ponte(BASE).gerarAta("ata")).toEqual({ ok: false, frase: FRASE_REUNIAO_AUSENTE });
    expect(await new Ponte("").gerarAta("ata")).toBeNull();
  });
});
