import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DepsConversa } from "../src/fala/conversa";
import { Conversa } from "../src/fala/conversa";
import { CONFIG_PADRAO } from "../src/config/config";
import { ROTULO_ESTADO } from "../src/ui/hud";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue(null) }));

const WAV = new ArrayBuffer(8);

describe("FR-007 — etapas visíveis e erros tipados", () => {
  let oj: DepsConversa["oj"];
  let boca: DepsConversa["boca"];
  let estados: Array<{ e: string; detalhe: string }>;
  let deps: DepsConversa;

  beforeEach(() => {
    oj = {
      perguntar: vi.fn().mockResolvedValue("Resposta."),
      sintetizar: vi.fn().mockResolvedValue(WAV),
    } as unknown as DepsConversa["oj"];
    boca = {
      falando: false,
      tocar: vi.fn().mockResolvedValue(undefined),
      parar: vi.fn(),
    } as unknown as DepsConversa["boca"];
    estados = [];
    deps = {
      oj,
      boca,
      config: CONFIG_PADRAO,
      falas: async () => WAV,
      aoEstado: (e: string, detalhe?: string) => estados.push({ e, detalhe: detalhe ?? "" }),
    };
  });

  it("emite 'pensando' antes da resposta do cérebro", async () => {
    const c = new Conversa(deps);
    await c.aoTextoTranscrito("Vard, que horas são", false);
    const idxPensando = estados.findIndex((s) => s.e === "pensando");
    const idxFalando = estados.findIndex((s) => s.e === "falando");
    expect(idxPensando).toBeGreaterThanOrEqual(0);
    expect(idxFalando).toBeGreaterThan(idxPensando);
  });

  it("emite 'falando' antes da reprodução", async () => {
    const c = new Conversa(deps);
    await c.aoTextoTranscrito("Vard, oi", false);
    const idxFalando = estados.findIndex((s) => s.e === "falando");
    expect(idxFalando).toBeGreaterThanOrEqual(0);
    expect(boca.tocar).toHaveBeenCalled();
  });

  it("erro do cérebro emite 'erro' com tipo 'resposta'", async () => {
    oj.perguntar.mockRejectedValue(new Error("HTTP 500"));
    const c = new Conversa(deps);
    await c.aoTextoTranscrito("Vard, oi", false);
    const erro = estados.find((s) => s.e === "erro");
    expect(erro).toBeDefined();
    expect(erro!.detalhe).toMatch(/^resposta:/);
  });

  it("erro de síntese emite 'erro' com tipo 'sintese'", async () => {
    oj.sintetizar.mockRejectedValue(new Error("voz indisponível"));
    const c = new Conversa(deps);
    await c.aoTextoTranscrito("Vard, oi", false);
    const erro = estados.find((s) => s.e === "erro" && s.detalhe.startsWith("sintese:"));
    expect(erro).toBeDefined();
    expect(erro!.detalhe).toContain("voz indisponível");
  });

  it("HUD mapeia o estado 'transcrevendo' com rótulo correto", () => {
    // O estado "transcrevendo" é emitido em main.ts antes de chamar transcreverFala.
    // A emissão real ocorre no fluxo de encerrar() em main.ts, não em conversa.ts.
    // Este teste valida que ROTULO_ESTADO cobre a chave "transcrevendo" em tempo de execução.
    expect(ROTULO_ESTADO.transcrevendo).toBe("transcrevendo");
  });

  it("tipo Estado aceita 'transcrevendo' e Record<Estado, string> exige a chave", () => {
    // O erro de transcrição é capturado em main.ts na função encerrar().
    // A emissão real: mostrarEstado("erro", `transcricao: ${mensagem}`) em main.ts.
    // Validação estática: se "transcrevendo" fosse removido de Estado ou de ROTULO_ESTADO,
    // o TypeScript rejeitaria este arquivo. Aqui confirmamos em tempo de execução.
    const rotulos: Record<string, string> = ROTULO_ESTADO;
    expect(rotulos).toHaveProperty("transcrevendo");
    expect(typeof rotulos.transcrevendo).toBe("string");
  });
});