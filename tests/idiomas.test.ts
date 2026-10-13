import { describe, it, expect } from "vitest";
import { IDIOMAS, campoIdioma, opcoesIdioma } from "../src/config/idiomas";

const semAcento = (n: string) => n.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

describe("opcoesIdioma", () => {
  it("comeca_no_automatico_e_lista_os_principais_na_ordem_do_painel", () => {
    const o = opcoesIdioma("pt");
    expect(o[0]).toEqual(["", "Detectar automaticamente"]);
    expect(o.slice(1, 9).map(([codigo]) => codigo)).toEqual(["pt", "en", "es", "fr", "de", "it", "ja", "zh"]);
  });
  it("valor_conhecido_continua_na_lista", () => {
    expect(opcoesIdioma("ja")).toContainEqual(["ja", "日本語"]);
    expect(opcoesIdioma("pt").some(([, nome]) => nome.startsWith("Outro:"))).toBe(false);
  });
  it("vazio_mostra_so_o_automatico", () => {
    const o = opcoesIdioma("");
    expect(o.filter(([codigo]) => codigo === "")).toEqual([["", "Detectar automaticamente"]]);
  });
  it("valor_fora_da_lista_vira_outro_com_o_mesmo_valor", () => {
    const o = opcoesIdioma("gd");
    expect(o[o.length - 1]).toEqual(["gd", "Outro: gd"]);
    expect(o).toHaveLength(IDIOMAS.length + 2);
  });
});

describe("IDIOMAS", () => {
  it("tem_os_99_idiomas_do_whisper_com_codigos_unicos", () => {
    const codigos = IDIOMAS.map(([codigo]) => codigo);
    expect(codigos).toHaveLength(99);
    expect(new Set(codigos).size).toBe(99);
  });
  it("os_demais_vem_ordenados_por_nome", () => {
    const nomes = IDIOMAS.slice(8).map(([, nome]) => semAcento(nome));
    expect(nomes).toEqual([...nomes].sort());
  });
});

describe("campoIdioma", () => {
  it("traz_a_lista_com_a_opcao_atual_marcada_e_a_ajuda", () => {
    const h = campoIdioma("pt");
    expect(h).toContain('id="cfg-idioma"');
    expect(h).toContain('<option value="pt" selected>Português</option>');
    expect(h).toContain("sem região: Português vale para Brasil e Portugal");
  });
  it("vazio_marca_o_automatico", () => {
    expect(campoIdioma("")).toContain('<option value="" selected>Detectar automaticamente</option>');
  });
  it("valor_antigo_fora_da_lista_aparece_como_outro_marcado", () => {
    expect(campoIdioma("gd")).toContain('<option value="gd" selected>Outro: gd</option>');
  });
});
