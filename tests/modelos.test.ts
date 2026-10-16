import { describe, it, expect, vi, afterEach } from "vitest";
import { OpenJarvis, escolherModelo } from "../src/conectores/openjarvis/cliente";
import { Ponte } from "../src/conectores/ponte/cliente";
import { formatarSegundos } from "../src/ui/aba-modelos";

const resposta = (corpo: unknown) => new Response(JSON.stringify(corpo), { status: 200, headers: { "Content-Type": "application/json" } });

describe("modelos", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("escolhe_o_preferido", () => {
    expect(escolherModelo(["a", "b"], "b")).toEqual({ id: "b", caiu: false });
  });
  it("vazio_usa_o_primeiro", () => {
    expect(escolherModelo(["a", "b"], "")).toEqual({ id: "a", caiu: false });
    expect(escolherModelo([], "a")).toBeNull();
  });
  it("modelo_sumiu_cai_para_o_primeiro", () => {
    expect(escolherModelo(["a", "b"], "c")).toEqual({ id: "a", caiu: true });
  });
  it("perguntar_manda_o_modelo_escolhido_e_troca_ao_vivo", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const corpos: { model: string }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/v1/models")) return resposta({ data: [{ id: "local" }, { id: "nuvem" }] });
      corpos.push(JSON.parse(String(init?.body)));
      return resposta({ choices: [{ message: { content: "ok" } }] });
    }));
    const oj = new OpenJarvis("http://127.0.0.1:8000", "nuvem");
    await oj.perguntar([{ role: "user", content: "oi" }]);
    oj.definirModelo("sumiu");
    await oj.perguntar([{ role: "user", content: "oi" }]);
    expect(corpos.map((c) => c.model)).toEqual(["nuvem", "local"]);
  });
  it("status_da_ponte_le_a_reserva", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ openjarvis: true, lmstudio: true, modo: "ligado", reserva: "combo/t1-work" })));
    expect((await new Ponte("http://127.0.0.1:4700").status())?.reserva).toBe("combo/t1-work");
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ openjarvis: true, lmstudio: true, modo: "ligado" })));
    expect((await new Ponte("http://127.0.0.1:4700").status())?.reserva).toBeUndefined();
  });
  it("status_da_ponte_filtra_modelos_lmstudio", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ openjarvis: true, lmstudio: true, modo: "ligado", modelos_lmstudio: ["a", 1, "b"], tarefas_abertas: 3 })));
    const st = await new Ponte("http://127.0.0.1:4700").status();
    expect(st?.modelos_lmstudio).toEqual(["a", "b"]);
    expect(st?.tarefas_abertas).toBe(3);
    vi.stubGlobal("fetch", vi.fn(async () => resposta({ openjarvis: true, lmstudio: true, modo: "ligado" })));
    const sem = await new Ponte("http://127.0.0.1:4700").status();
    expect(sem?.modelos_lmstudio).toBeUndefined();
    expect(sem?.tarefas_abertas).toBeUndefined();
  });
  it("ponte_sem_endereco_nao_faz_rede", async () => {
    const f = vi.fn(async () => resposta({ ok: true }));
    vi.stubGlobal("fetch", f);
    expect(await new Ponte("").status()).toBeNull();
    expect(await new Ponte("").modo("jogo")).toBe(false);
    expect(f).not.toHaveBeenCalled();
  });

  it("formatar_segundos", () => {
    expect(formatarSegundos(1830)).toBe("1,8 s");
    expect(formatarSegundos(500)).toBe("0,5 s");
    expect(formatarSegundos(12345)).toBe("12,3 s");
  });
});
