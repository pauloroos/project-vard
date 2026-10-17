import { describe, it, expect } from "vitest";
import { extrairComando, classificar, ehInterrupcao, ehConfirmacao, aPartirDoGatilho } from "../src/fala/rotas";
import { FALAS } from "../src/fala/falas";

const V = ["vard", "varde", "vardi", "ward", "bard"];

describe("rotas", () => {
  it("gatilho no começo, com vírgula e maiúsculas", () => {
    expect(extrairComando("Vard, abre o YouTube", V)).toBe("abre o YouTube");
    expect(extrairComando("vard abre o youtube", V)).toBe("abre o youtube");
  });
  it("pontuação antes do nome não corrompe o comando", () => {
    expect(extrairComando(", vard abre o youtube", V)).toBe("abre o youtube");
    expect(extrairComando("... Vard, abre o YouTube", V)).toBe("abre o YouTube");
    expect(extrairComando("Vard", V)).toBe("");
  });
  it("variantes do reconhecimento disparam", () => {
    expect(extrairComando("Varde abre o youtube", V)).toBe("abre o youtube");
    expect(extrairComando("Ward, que horas são", V)).toBe("que horas são");
    expect(extrairComando("Vardi, abre o chrome", V)).toBe("abre o chrome");
    expect(extrairComando("Bard abre o chrome", V)).toBe("abre o chrome");
  });
  it("nome no meio ou ausente não dispara", () => {
    expect(extrairComando("abre o YouTube, Vard", V)).toBeNull();
    expect(extrairComando("abre o youtube", V)).toBeNull();
    expect(extrairComando("a varanda está suja", V)).toBeNull();
  });
  it("variantes vêm por parâmetro", () => {
    expect(extrairComando("Jarvis, oi", ["jarvis"])).toBe("oi");
    expect(extrairComando("Vard, oi", ["jarvis"])).toBeNull();
  });
  it("classificação de rota", () => {
    expect(classificar("o que você está vendo")).toBe("see");
    expect(classificar("olha a tela e me diz o que é isso")).toBe("see");
    expect(classificar("lê isso pra mim")).toBe("see");
    expect(classificar("modo jogo")).toBe("modo");
    expect(classificar("módo jogo")).toBe("modo");
    expect(classificar("abre o youtube")).toBe("ask");
  });
  it("pedido de ver a tela em qualquer forma natural vai para a visão", () => {
    expect(classificar("consegue ver minha tela?")).toBe("see");
    expect(classificar("vê minha tela")).toBe("see");
    expect(classificar("veja a minha tela e me diz o que tem")).toBe("see");
    expect(classificar("dá uma olhada na tela")).toBe("see");
    expect(classificar("você consegue ler o que está na tela")).toBe("see");
    expect(classificar("o que tá na minha tela")).toBe("see");
    expect(classificar("o que você tá vendo")).toBe("see");
  });
  it("tela sem pedido de ver não muda a rota", () => {
    expect(classificar("abre o telegram")).toBe("ask");
    expect(classificar("quanto custa uma tela nova")).toBe("ask");
    expect(classificar("me ajuda a ver o horário do voo")).toBe("ask");
  });
  it("interrupções", () => {
    expect(ehInterrupcao("para")).toBe(true);
    expect(ehInterrupcao("Espera!")).toBe(true);
    expect(ehInterrupcao("para de brincadeira e abre o chrome")).toBe(false);
  });
  it("confirmação só com sim ou confirmo", () => {
    for (const t of ["sim", "Sim!", "  sim.", "confirmo", "Confirmo!"]) expect(ehConfirmacao(t)).toBe(true);
    for (const t of ["simples não", "Simone", "pode ser", "pode", "sim, mas depois", "não", ""]) expect(ehConfirmacao(t)).toBe(false);
  });
  it("a partir do gatilho", () => {
    expect(aPartirDoGatilho("então Vard, abre o Chrome", V)).toBe("Vard, abre o Chrome");
    expect(aPartirDoGatilho("abre o Chrome, Vard", V)).toBeNull();
    expect(aPartirDoGatilho("Vard", V)).toBe("Vard");
    expect(aPartirDoGatilho("e aí ele falou que não vinha", V)).toBeNull();
    expect(aPartirDoGatilho("conversa qualquer vard que horas são", V)).toBe("vard que horas são");
  });
  it("FALAS tem as chaves fixas", () => {
    for (const k of ["saudacao", "pensando", "telaNaoCompartilhada", "erroModelo", "erroOuvido", "modoJogoConfirmar", "modoJogoAtivado", "semPonte", "openjarvisFora", "falaDesligada", "microfoneBloqueado"] as const)
      expect(typeof FALAS[k]).toBe("string");
    for (const k of ["modelo_fora", "modelo_demorou", "modelo_http", "modelo_vazio", "rede", "nao_json", "segredos", "modo_script", "modo_falhou", "origem_recusada"] as const)
      expect(typeof FALAS.erros[k]).toBe("string");
  });
});
