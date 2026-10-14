import { describe, it, expect } from "vitest";
import {
  criarMaquinaConversaAberta,
  processamentoConcluido,
  type MaquinaConversaAberta,
} from "../src/conversa/aberta";

describe("conversa aberta (T13)", () => {
  let maquina: MaquinaConversaAberta;

  function nova() {
    maquina = criarMaquinaConversaAberta();
    return maquina;
  }

  it("maquina inicia desligada", () => {
    expect(nova().estado).toBe("desligado");
  });

  it("ligar transiciona para ouvindo", () => {
    const m = nova();
    expect(m.ligar()).toBe("ouvindo");
    expect(m.estado).toBe("ouvindo");
  });

  it("fala detectada mantém ouvindo e reseta timer (vai para processando)", () => {
    const m = nova();
    m.ligar();
    const aceita = m.falaDetectada("qual é a previsão do tempo hoje");
    expect(aceita).toBe(true);
    expect(m.estado).toBe("processando");
  });

  it("silencio prolongado encerra quando em ouvindo", () => {
    const m = nova();
    m.ligar();
    expect(m.silencioExpirou()).toBe("desligado");
    expect(m.estado).toBe("desligado");
  });

  it("silencio expirado não afeta estado se já desligado ou processando", () => {
    const m = nova();
    // Desligado → sem efeito
    expect(m.silencioExpirou()).toBe("desligado");

    // Processando → sem efeito
    m.ligar();
    m.falaDetectada("teste válido agora mesmo");
    expect(m.estado).toBe("processando");
    expect(m.silencioExpirou()).toBe("processando");
  });

  it("reuniao desliga automaticamente", () => {
    const m = nova();
    m.ligar();
    expect(m.contextoMudou("reuniao")).toBe("desligado");
    expect(m.estado).toBe("desligado");
  });

  it("jogo desliga automaticamente", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("uma frase válida qualquer");
    expect(m.estado).toBe("processando");
    expect(m.contextoMudou("jogo")).toBe("desligado");
  });

  it("fala curta ignorada mas mantém ouvindo", () => {
    const m = nova();
    m.ligar();
    const aceita = m.falaDetectada("oi");
    expect(aceita).toBe(false);
    expect(m.estado).toBe("ouvindo");
  });

  it("frase de encerramento desliga", () => {
    const m = nova();
    m.ligar();
    const aceita = m.falaDetectada("pode parar de me ouvir");
    expect(aceita).toBe(false);
    expect(m.estado).toBe("desligado");
  });

  it("processamento concluído retorna para ouvindo", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("me conta uma história legal");
    expect(m.estado).toBe("processando");
    expect(processamentoConcluido(m)).toBe("ouvindo");
    expect(m.estado).toBe("ouvindo");
  });

  it("ehFraseEncerramento reconhece variantes", () => {
    const m = nova();
    expect(m.ehFraseEncerramento("pode parar de me ouvir")).toBe(true);
    expect(m.ehFraseEncerramento("Para de me ouvir!")).toBe(true);
    expect(m.ehFraseEncerramento("não ouvir mais")).toBe(true);
    expect(m.ehFraseEncerramento("parar de ouvir agora")).toBe(true);
    expect(m.ehFraseEncerramento("pode parar")).toBe(true);
    expect(m.ehFraseEncerramento("qual a previsão")).toBe(false);
  });

  it("fala detectada só funciona em estado ouvindo", () => {
    const m = nova();
    // Desligado → não aceita
    expect(m.falaDetectada("teste válido aqui agora")).toBe(false);
    expect(m.estado).toBe("desligado");

    // Processando → não aceita
    m.ligar();
    m.falaDetectada("primeira frase válida aqui");
    expect(m.estado).toBe("processando");
    expect(m.falaDetectada("segunda frase válida aqui")).toBe(false);
    expect(m.estado).toBe("processando");
  });

  it("config personalizada minPalavras altera limiar", () => {
    const m = criarMaquinaConversaAberta({ minPalavras: 1 });
    m.ligar();
    expect(m.falaDetectada("oi")).toBe(true);
    expect(m.estado).toBe("processando");
  });

  it("desligar explicitamente funciona de qualquer estado", () => {
    const m = nova();
    m.ligar();
    expect(m.desligar()).toBe("desligado");

    m.ligar();
    m.falaDetectada("frase válida para testar");
    expect(m.desligar()).toBe("desligado");
  });
});