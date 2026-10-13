import { describe, it, expect, vi, beforeEach } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a) }));

import { lerConfigAoVivo, lerTopoCompacto, aplicarAoVivo, carregarConfig, CONFIG_PADRAO, mudancasQueExigemReinicio, atualizarConfig, limitarLado, urlLocal, avisosDeUrl, gatilhos } from "../src/config/config";

describe("carregarConfig", () => {
  beforeEach(() => invoke.mockReset());

  it("sem config salva devolve o padrao", async () => {
    invoke.mockResolvedValue(null);
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });

  it("tamanho desconhecido volta ao padrão; compacto e lado salvos valem", async () => {
    invoke.mockResolvedValue({ tamanho: "enorme", tamanho_px: 500, compacto: true });
    const c = await carregarConfig();
    expect(c.tamanho).toBe("medio");
    expect(c.tamanho_px).toBe(500);
    expect(c.compacto).toBe(true);
  });

  it("conversa_ms: negativo, texto e NaN voltam ao padrão; zero desliga", async () => {
    invoke.mockResolvedValue({ conversa_ms: -5 });
    expect((await carregarConfig()).conversa_ms).toBe(20000);
    invoke.mockResolvedValue({ conversa_ms: "x" });
    expect((await carregarConfig()).conversa_ms).toBe(20000);
    invoke.mockResolvedValue({ conversa_ms: 0 });
    expect((await carregarConfig()).conversa_ms).toBe(0);
    invoke.mockResolvedValue({ conversa_ms: 1500.4 });
    expect((await carregarConfig()).conversa_ms).toBe(1500);
  });

  it("mescla o padrao com o salvo", async () => {
    invoke.mockResolvedValue({ nome: "jarvis", velocidade: 1.2, voz_url: "" });
    const c = await carregarConfig();
    expect(c.voz_url).toBe(""); // vazio salvo é escolha (voz própria desligada), não volta ao padrão
    expect(c.nome).toBe("jarvis");
    expect(c.velocidade).toBe(1.2);
    expect(c.idioma).toBe(CONFIG_PADRAO.idioma);
  });

  it("preserva atalhos parciais", async () => {
    invoke.mockResolvedValue({ atalhos: { falar: "Ctrl+Shift+F" } });
    const c = await carregarConfig();
    expect(c.atalhos.falar).toBe("Ctrl+Shift+F");
    expect(c.atalhos.parar).toBe(CONFIG_PADRAO.atalhos.parar);
    expect(c.atalhos.mostrar).toBe(CONFIG_PADRAO.atalhos.mostrar);
  });

  it("atalhos novos têm padrão e o salvo antigo (só três) continua valendo", async () => {
    invoke.mockResolvedValue({ atalhos: { falar: "Ctrl+Shift+F", parar: "Ctrl+Alt+Period", mostrar: "Ctrl+Alt+V" } });
    const c = await carregarConfig();
    expect(c.atalhos.falar).toBe("Ctrl+Shift+F");
    expect(c.atalhos.config).toBe("Ctrl+Alt+P");
    expect(c.atalhos.escuta).toBe("Ctrl+Alt+L");
  });

  it("migra o painel Ctrl+Alt+Comma (antigo padrão, roubava o ç) e preserva escolha do usuário", async () => {
    invoke.mockResolvedValue({ atalhos: { config: "Ctrl+Alt+Comma", escuta: "Ctrl+Alt+Comma" } });
    const c = await carregarConfig();
    expect(c.atalhos.config).toBe("Ctrl+Alt+P");
    expect(c.atalhos.escuta).toBe("Ctrl+Alt+Comma");
    invoke.mockResolvedValue({ atalhos: { config: "Ctrl+Shift+K" } });
    expect((await carregarConfig()).atalhos.config).toBe("Ctrl+Shift+K");
  });
});

describe("carregarConfig com arquivo ruim", () => {
  beforeEach(() => { invoke.mockReset(); vi.spyOn(console, "warn").mockImplementation(() => {}); });

  it("invoke rejeitando (JSON inválido) cai para o padrão", async () => {
    invoke.mockRejectedValue("expected value at line 1 column 1");
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });
  it("lixo no lugar do objeto cai para o padrão", async () => {
    invoke.mockResolvedValue("lixo");
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
    invoke.mockResolvedValue([1, 2]);
    expect(await carregarConfig()).toEqual(CONFIG_PADRAO);
  });
  it("tipos errados são descartados chave a chave", async () => {
    invoke.mockResolvedValue({ variantes: "vard", velocidade: "rápido", nome: "jarvis", atalhos: { falar: 3 } });
    const c = await carregarConfig();
    expect(c.variantes).toEqual(CONFIG_PADRAO.variantes);
    expect(c.velocidade).toBe(CONFIG_PADRAO.velocidade);
    expect(c.nome).toBe("jarvis");
    expect(c.atalhos).toEqual(CONFIG_PADRAO.atalhos);
  });
});

describe("gatilhos", () => {
  it("com o nome padrão mantém as variantes", () => {
    expect(gatilhos(CONFIG_PADRAO)).toEqual(CONFIG_PADRAO.variantes);
  });
  it("com outro nome usa o nome e só as variantes próprias", () => {
    expect(gatilhos({ nome: "Jarvis", variantes: [...CONFIG_PADRAO.variantes, "jarvi"] })).toEqual(["jarvis", "jarvi"]);
  });
});

describe("urlLocal", () => {
  it("aceita 127.0.0.1 e localhost", () => {
    expect(urlLocal("http://127.0.0.1:8000")).toBe(true);
    expect(urlLocal("http://localhost:5173/")).toBe(true);
  });
  it("recusa outros hosts, esquemas e lixo", () => {
    expect(urlLocal("http://10.0.0.5:8000")).toBe(false);
    expect(urlLocal("http://127.0.0.1.evil.com")).toBe(false);
    expect(urlLocal("ftp://127.0.0.1")).toBe(false);
    expect(urlLocal("isto nao e url")).toBe(false);
    expect(urlLocal("")).toBe(false);
  });
  it("avisosDeUrl lista só os campos fora da máquina", () => {
    expect(avisosDeUrl(CONFIG_PADRAO)).toEqual([]);
    const a = avisosDeUrl({ ...CONFIG_PADRAO, ponte_url: "http://10.0.0.5:4700" });
    expect(a).toHaveLength(1);
    expect(a[0]).toContain("Ponte");
    expect(avisosDeUrl({ ...CONFIG_PADRAO, ponte_url: "" })).toEqual([]); // vazio = ponte desligada
  });
  it("serviço de voz: fora da máquina avisa, vazio desliga sem aviso", () => {
    expect(CONFIG_PADRAO.voz_url).toBe("http://127.0.0.1:4710");
    const a = avisosDeUrl({ ...CONFIG_PADRAO, voz_url: "http://192.168.0.9:4710" });
    expect(a).toHaveLength(1);
    expect(a[0]).toContain("Serviço de voz");
    expect(avisosDeUrl({ ...CONFIG_PADRAO, voz_url: "" })).toEqual([]);
  });
});

describe("salvar no painel", () => {
  const copia = () => ({ ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } });

  it("aplica_ao_vivo_so_o_seguro", () => {
    const vivo = copia();
    const novo = { ...copia(), tamanho: "grande" as const, usuario: "Ana", openjarvis_url: "http://127.0.0.1:9000", voz: "pf_dora" };
    expect(aplicarAoVivo(vivo, novo)).toEqual(["tamanho", "usuario"]);
    expect(vivo.tamanho).toBe("grande");
    expect(vivo.usuario).toBe("Ana");
    expect(vivo.openjarvis_url).toBe(CONFIG_PADRAO.openjarvis_url);
    expect(vivo.voz).toBe(CONFIG_PADRAO.voz);
  });

  it("lista_o_que_exige_reinicio", () => {
    const novo = { ...copia(), openjarvis_url: "http://127.0.0.1:9000", ponte_url: "", compacto: true, atalhos: { ...CONFIG_PADRAO.atalhos, escuta: "Ctrl+Alt+N" } };
    expect(mudancasQueExigemReinicio(CONFIG_PADRAO, novo)).toEqual(["endereços", "atalhos"]);
    expect(mudancasQueExigemReinicio(CONFIG_PADRAO, copia())).toEqual([]);
  });
});

describe("payloads entre janelas", () => {
  const ok = { tamanho: "grande", tamanho_px: 480, compacto: false, sempre_no_topo: true, click_through: false, usuario: "Ana", modelo: "", conversa_ms: 20000 };
  it("lado fora de 160..800 é limitado, não recusado", () => {
    expect(lerConfigAoVivo({ ...ok, tamanho_px: 1000 })).toEqual({ ...ok, tamanho_px: 800 });
    expect(lerConfigAoVivo({ ...ok, tamanho_px: 100 })).toEqual({ ...ok, tamanho_px: 160 });
    expect(limitarLado(333.4)).toBe(333);
  });
  it("aceita_payload_valido", () => { expect(lerConfigAoVivo({ ...ok, extra: 1 })).toEqual(ok); });
  it("recusa_tipos_e_faixas_ruins", () => {
    for (const ruim of [null, "x", 3, { ...ok, tamanho: "enorme" }, 
      { ...ok, tamanho_px: "320" }, { ...ok, tamanho_px: NaN }, { ...ok, compacto: "sim" }, { ...ok, sempre_no_topo: 1 },
      { ...ok, click_through: null }, { ...ok, usuario: 5 }, { ...ok, modelo: 7 }, { ...ok, conversa_ms: "20" }, { ...ok, conversa_ms: -1 }, { ...ok, conversa_ms: NaN }]) expect(lerConfigAoVivo(ruim)).toBeNull();
  });
  it("conversa_ms_numerico_e_aceito", () => { expect(lerConfigAoVivo({ ...ok, conversa_ms: 0 })).toEqual({ ...ok, conversa_ms: 0 }); });
  it("topo_e_compacto", () => {
    expect(lerTopoCompacto({ sempre_no_topo: true, compacto: false })).toEqual({ sempre_no_topo: true, compacto: false });
    expect(lerTopoCompacto({ sempre_no_topo: "1", compacto: false })).toBeNull();
    expect(lerTopoCompacto(undefined)).toBeNull();
  });
});

describe("atualizarConfig", () => {
  beforeEach(() => invoke.mockReset());
  it("grava só a chave mudada e mantém o que o painel salvou no disco", async () => {
    const disco = { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos, escuta: "Ctrl+Shift+K" }, ponte_url: "http://127.0.0.1:9999", sala_monitor: "DISPLAY2" };
    let gravado: unknown = null;
    invoke.mockImplementation(async (cmd: string, args?: { config: unknown }) => {
      if (cmd === "ler_config") return JSON.parse(JSON.stringify(disco));
      if (cmd === "gravar_config") { gravado = args?.config; return; }
    });
    await atualizarConfig({ compacto: true });
    expect(gravado).toEqual({ ...disco, compacto: true });
    await atualizarConfig({ sempre_no_topo: false });
    expect((gravado as typeof disco).atalhos.escuta).toBe("Ctrl+Shift+K");
  });
});

describe("reinício e atalhos normalizados", () => {
  it("o mesmo atalho escrito de outro jeito não pede reinício; um diferente pede", () => {
    const a = { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos, mostrar: "ctrl + alt + v" } };
    expect(mudancasQueExigemReinicio(a, CONFIG_PADRAO)).toEqual([]);
    expect(mudancasQueExigemReinicio(CONFIG_PADRAO, { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos, mostrar: "Ctrl+Alt+J" } })).toEqual(["atalhos"]);
  });
});
