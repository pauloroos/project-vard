import { describe, it, expect } from "vitest";
import { cortarEmFrases } from "../src/fala/frases";

describe("cortarEmFrases", () => {
  it("duas frases com ponto", () => {
    expect(cortarEmFrases("Oi, Ana. O YouTube já está aberto.")).toEqual(["Oi, Ana.", "O YouTube já está aberto."]);
  });
  it("uma palavra com exclamação vira uma frase", () => {
    expect(cortarEmFrases("Pronto!")).toEqual(["Pronto!"]);
  });
  it("sem pontuação final ainda vira uma frase", () => {
    expect(cortarEmFrases("abri o youtube pra você")).toEqual(["abri o youtube pra você"]);
    expect(cortarEmFrases("Abri o YouTube. Quer que eu toque algo")).toEqual(["Abri o YouTube.", "Quer que eu toque algo"]);
  });
  it("abreviações não cortam", () => {
    expect(cortarEmFrases("O Dr. Carlos chegou agora. A Sra. Ana também veio.")).toEqual(["O Dr. Carlos chegou agora.", "A Sra. Ana também veio."]);
    expect(cortarEmFrases("Falei com o Sr. Silva e o Prof. Lima hoje.")).toEqual(["Falei com o Sr. Silva e o Prof. Lima hoje."]);
    expect(cortarEmFrases("Frutas, verduras etc. ficam na geladeira, p. ex. a alface.")).toEqual(["Frutas, verduras etc. ficam na geladeira, p. ex. a alface."]);
  });
  it("números com ponto não cortam", () => {
    expect(cortarEmFrases("A reunião é às 15.30 na sala dois.")).toEqual(["A reunião é às 15.30 na sala dois."]);
    expect(cortarEmFrases("Custa R$ 1.200,00 à vista. Parcelado sai mais caro.")).toEqual(["Custa R$ 1.200,00 à vista.", "Parcelado sai mais caro."]);
  });
  it("corta em ! ? reticências e quebra de linha", () => {
    expect(cortarEmFrases("Que dia bonito hoje! Vamos sair agora? Talvez mais tarde… Quem sabe amanhã cedo.")).toEqual([
      "Que dia bonito hoje!", "Vamos sair agora?", "Talvez mais tarde…", "Quem sabe amanhã cedo.",
    ]);
    expect(cortarEmFrases("Primeira linha sem ponto\nSegunda linha sem ponto")).toEqual(["Primeira linha sem ponto", "Segunda linha sem ponto"]);
    expect(cortarEmFrases("Deixa eu pensar... Acho que sim, pode ser.")).toEqual(["Deixa eu pensar...", "Acho que sim, pode ser."]);
  });
  it("pedaço curto (< 12 caracteres) junta no anterior", () => {
    expect(cortarEmFrases("O YouTube já está aberto. Pronto!")).toEqual(["O YouTube já está aberto. Pronto!"]);
    expect(cortarEmFrases("Abri o navegador para você. Ok. Algo mais por aqui?")).toEqual(["Abri o navegador para você. Ok.", "Algo mais por aqui?"]);
  });
  it("vazio e só espaços não geram frase", () => {
    expect(cortarEmFrases("")).toEqual([]);
    expect(cortarEmFrases("  \n ")).toEqual([]);
  });
  it("aspas e parênteses depois do ponto ficam na frase", () => {
    expect(cortarEmFrases("Ele disse \"já volto.\" Depois saiu correndo.")).toEqual(["Ele disse \"já volto.\"", "Depois saiu correndo."]);
  });
  it("pedaço longo demais é partido em até 400 caracteres", () => {
    const longo = Array.from({ length: 120 }, (_, i) => `palavra${i}`).join(" ");
    const partes = cortarEmFrases(longo);
    expect(partes.length).toBeGreaterThan(1);
    for (const p of partes) expect(p.length).toBeLessThanOrEqual(400);
    expect(partes.join(" ")).toBe(longo);
  });
});
