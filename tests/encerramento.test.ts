import { describe, it, expect } from "vitest";
import { ehEncerramento } from "../src/fala/encerramento";

describe("ehEncerramento", () => {
  it("aceita_as_variantes", () => {
    for (const t of ["pode parar de me ouvir", "Pare de me ouvir!", "para de me ouvir agora", "Deixa de me ouvir",
      "não precisa mais me ouvir", "vou entrar em reunião", "Entrando em reunião.", "estou em reunião", "tô em reunião",
      "modo silencioso", "pode descansar"]) expect(ehEncerramento(t), t).toBe(true);
  });
  it("nao_confunde_pergunta_sobre_reuniao", () => {
    for (const t of ["marca reunião amanhã às 10", "quando é a reunião", "que horas são", "me ouve", "para"]) expect(ehEncerramento(t), t).toBe(false);
  });
  it("vazio_e_false", () => { expect(ehEncerramento("")).toBe(false); });
});
