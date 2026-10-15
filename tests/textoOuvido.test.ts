import { describe, it, expect, vi } from "vitest";
import { processarTextoOuvido, type TextoOuvidoDeps } from "../src/fala/textoOuvido";

function criarDeps(overrides: Partial<TextoOuvidoDeps> = {}): TextoOuvidoDeps & {
  usuarioRespondeu: ReturnType<typeof vi.fn>;
  aoTextoTranscrito: ReturnType<typeof vi.fn>;
  executarAcoesChamada: ReturnType<typeof vi.fn>;
} {
  const usuarioRespondeu = vi.fn().mockReturnValue([]);
  const aoTextoTranscrito = vi.fn().mockResolvedValue(undefined);
  const executarAcoesChamada = vi.fn().mockResolvedValue(undefined);
  return {
    fluxoChamada: { estado: "inativo", usuarioRespondeu },
    conversa: { aoTextoTranscrito },
    executarAcoesChamada,
    conversaAbertaEstado: () => "desligado",
    ...overrides,
  } as unknown as TextoOuvidoDeps & {
    usuarioRespondeu: ReturnType<typeof vi.fn>;
    aoTextoTranscrito: ReturnType<typeof vi.fn>;
    executarAcoesChamada: ReturnType<typeof vi.fn>;
  };
}

describe("processarTextoOuvido (T14 + T13)", () => {
  it("rota para fluxo de chamada quando aguardando_resposta", async () => {
    const deps = criarDeps({
      fluxoChamada: {
        estado: "aguardando_resposta",
        usuarioRespondeu: vi.fn().mockReturnValue([{ tipo: "sintetizar", texto: "ok" }]),
      },
    });
    const roteado = await processarTextoOuvido(deps, "sim", false);
    expect(roteado).toBe(true);
    expect(deps.executarAcoesChamada).toHaveBeenCalledWith([{ tipo: "sintetizar", texto: "ok" }]);
    expect(deps.conversa.aoTextoTranscrito).not.toHaveBeenCalled();
  });

  it("rota para fluxo de chamada quando conversando", async () => {
    const deps = criarDeps({
      fluxoChamada: {
        estado: "conversando",
        usuarioRespondeu: vi.fn().mockReturnValue([{ tipo: "abrir_escuta" }]),
      },
    });
    const roteado = await processarTextoOuvido(deps, "continuar", false);
    expect(roteado).toBe(true);
    expect(deps.executarAcoesChamada).toHaveBeenCalled();
    expect(deps.conversa.aoTextoTranscrito).not.toHaveBeenCalled();
  });

  it("nao rota para fluxo de chamada quando inativo", async () => {
    const deps = criarDeps();
    const roteado = await processarTextoOuvido(deps, "teste", false);
    expect(roteado).toBe(false);
    expect(deps.conversa.aoTextoTranscrito).toHaveBeenCalledWith("teste", false);
  });

  it("pushToTalk dispensa nome mesmo com conversa aberta desligada", async () => {
    const deps = criarDeps({ conversaAbertaEstado: () => "desligado" });
    await processarTextoOuvido(deps, "abre youtube", true);
    expect(deps.conversa.aoTextoTranscrito).toHaveBeenCalledWith("abre youtube", true);
  });

  it("conversa aberta ligada dispensa nome sem pushToTalk (defeito A)", async () => {
    const deps = criarDeps({ conversaAbertaEstado: () => "ouvindo" });
    await processarTextoOuvido(deps, "abre youtube", false);
    // Regra unificada: conversa aberta ligada → dispensaNome=true
    expect(deps.conversa.aoTextoTranscrito).toHaveBeenCalledWith("abre youtube", true);
  });

  it("conversa aberta em processando tambem dispensa nome", async () => {
    const deps = criarDeps({ conversaAbertaEstado: () => "processando" });
    await processarTextoOuvido(deps, "qual a hora", false);
    expect(deps.conversa.aoTextoTranscrito).toHaveBeenCalledWith("qual a hora", true);
  });

  it("sem pushToTalk e sem conversa aberta exige nome (passa false)", async () => {
    const deps = criarDeps({ conversaAbertaEstado: () => "desligado" });
    await processarTextoOuvido(deps, "abre youtube", false);
    expect(deps.conversa.aoTextoTranscrito).toHaveBeenCalledWith("abre youtube", false);
  });

  it("fluxo de chamada tem prioridade sobre conversa aberta", async () => {
    const deps = criarDeps({
      fluxoChamada: {
        estado: "aguardando_resposta",
        usuarioRespondeu: vi.fn().mockReturnValue([{ tipo: "sintetizar", texto: "resposta" }]),
      },
      conversaAbertaEstado: () => "ouvindo",
    });
    const roteado = await processarTextoOuvido(deps, "sim", false);
    expect(roteado).toBe(true);
    expect(deps.conversa.aoTextoTranscrito).not.toHaveBeenCalled();
  });
});