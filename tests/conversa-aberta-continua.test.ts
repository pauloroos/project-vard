import { describe, it, expect } from "vitest";
import {
  criarMaquinaConversaAberta,
  processamentoConcluido,
  type MaquinaConversaAberta,
} from "../src/conversa/aberta";

describe("conversa aberta contínua (0.9.6)", () => {
  let maquina: MaquinaConversaAberta;

  function nova() {
    maquina = criarMaquinaConversaAberta();
    return maquina;
  }

  it("após resposta retorna para ouvindo automaticamente", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("qual é a previsão do tempo hoje");
    expect(m.estado).toBe("processando");
    expect(processamentoConcluido(m)).toBe("ouvindo");
    expect(m.estado).toBe("ouvindo");
  });

  it("segue ouvindo sem exigir nome após primeira resposta", () => {
    const m = nova();
    m.ligar();
    // Primeira fala válida
    m.falaDetectada("primeira pergunta completa aqui");
    expect(m.estado).toBe("processando");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    // Segunda fala válida sem nome: deve ser aceita
    const aceita = m.falaDetectada("segunda pergunta sem nome");
    expect(aceita).toBe(true);
    expect(m.estado).toBe("processando");
  });

  it("silêncio configurável encerra a conversa aberta", () => {
    const m = criarMaquinaConversaAberta({ silencioMs: 5000 });
    m.ligar();
    m.falaDetectada("pergunta válida para testar");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    expect(m.silencioExpirou()).toBe("desligado");
  });

  it("frase de encerramento desliga mesmo durante diálogo contínuo", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("pergunta inicial válida aqui");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    const aceita = m.falaDetectada("pode parar de me ouvir");
    expect(aceita).toBe(false);
    expect(m.estado).toBe("desligado");
  });

  it("modo jogo desliga conversa aberta durante diálogo contínuo", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("pergunta válida qualquer coisa");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    expect(m.contextoMudou("jogo")).toBe("desligado");
  });

  it("não ouvir desliga conversa aberta", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("pergunta válida qualquer coisa");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    expect(m.desligar()).toBe("desligado");
  });

  it("timer de silêncio reinicia após cada resposta", () => {
    const m = criarMaquinaConversaAberta({ silencioMs: 10000 });
    m.ligar();
    // Primeira troca
    m.falaDetectada("primeira pergunta válida aqui");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    // Segunda troca: timer deve ser rearmado (estado volta a ouvindo)
    m.falaDetectada("segunda pergunta válida aqui");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
  });

  it("fala curta não interrompe diálogo contínuo", () => {
    const m = nova();
    m.ligar();
    m.falaDetectada("pergunta válida inicial aqui");
    processamentoConcluido(m);
    expect(m.estado).toBe("ouvindo");
    // Fala curta: ignorada mas mantém ouvindo
    const aceita = m.falaDetectada("oi");
    expect(aceita).toBe(false);
    expect(m.estado).toBe("ouvindo");
    // Fala válida seguinte ainda funciona
    const valida = m.falaDetectada("pergunta válida seguinte aqui");
    expect(valida).toBe(true);
    expect(m.estado).toBe("processando");
  });
});