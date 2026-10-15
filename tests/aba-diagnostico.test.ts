import { describe, it, expect, beforeEach, vi } from "vitest";
import { AbaDiagnostico, type ResultadoDiagnostico } from "../src/ui/aba-diagnostico";

// Mock do invoke do Tauri
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

import { invoke } from "@tauri-apps/api/core";
const mockInvoke = vi.mocked(invoke);

describe("AbaDiagnostico", () => {
  let raiz: HTMLDivElement;
  let deps: { copiar: ReturnType<typeof vi.fn> };
  let aba: AbaDiagnostico;

  const resultadoFake: ResultadoDiagnostico = {
    checagens: [
      { grupo: "Runtime", nome: "Portas do Vard", estado: "ok", frase: "portas em loopback" },
      { grupo: "Hardware", nome: "GPU e RAM", estado: "aviso", frase: "GPU não detectada" },
    ],
    relatorio: "# Diagnóstico Vard (basico)\n✔ [Runtime] Portas do Vard: portas em loopback\n! [Hardware] GPU e RAM: GPU não detectada\n\n1 ok, 1 avisos, 0 falhas",
    duracao_ms: 150,
  };

  beforeEach(() => {
    raiz = document.createElement("div");
    deps = { copiar: vi.fn().mockResolvedValue(undefined) };
    aba = new AbaDiagnostico(raiz, deps);
    mockInvoke.mockReset();
  });

  it("montar cria botoes e fieldset", () => {
    aba.montar();
    expect(raiz.querySelector("#diag-basico")).toBeTruthy();
    expect(raiz.querySelector("#diag-preflight")).toBeTruthy();
    expect(raiz.querySelector("#diag-cancelar")).toBeTruthy();
    expect(raiz.querySelector("#diag-copiar")).toBeTruthy();
    expect(raiz.querySelector("fieldset")).toBeTruthy();
  });

  it("botao basico dispara invoke com tipo basico", async () => {
    mockInvoke.mockResolvedValue(resultadoFake);
    aba.montar();
    const btn = raiz.querySelector("#diag-basico") as HTMLButtonElement;
    btn.click();
    // Aguarda resolução assíncrona
    await new Promise((r) => setTimeout(r, 50));
    expect(mockInvoke).toHaveBeenCalledWith("rodar_diagnostico", { tipo: "basico" });
  });

  it("exibe resultado apos execucao bem-sucedida", async () => {
    mockInvoke.mockResolvedValue(resultadoFake);
    aba.montar();
    const btn = raiz.querySelector("#diag-basico") as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));
    const divResultado = raiz.querySelector("#diag-resultado") as HTMLDivElement;
    expect(divResultado.hidden).toBe(false);
    const pre = raiz.querySelector("#diag-relatorio") as HTMLPreElement;
    expect(pre.textContent).toContain("Diagnóstico Vard");
    const resumo = raiz.querySelector("#diag-resumo") as HTMLDivElement;
    expect(resumo.textContent).toContain("1 ok");
    expect(resumo.textContent).toContain("1 avisos");
  });

  it("copiar relatorio chama deps.copiar", async () => {
    mockInvoke.mockResolvedValue(resultadoFake);
    aba.montar();
    const btnBasico = raiz.querySelector("#diag-basico") as HTMLButtonElement;
    btnBasico.click();
    await new Promise((r) => setTimeout(r, 50));
    const btnCopiar = raiz.querySelector("#diag-copiar") as HTMLButtonElement;
    expect(btnCopiar.disabled).toBe(false);
    btnCopiar.click();
    await new Promise((r) => setTimeout(r, 10));
    expect(deps.copiar).toHaveBeenCalledWith(resultadoFake.relatorio);
  });

  it("cancelar invoca cancelar_diagnostico", async () => {
    mockInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "cancelar_diagnostico") return undefined;
      // Simula execução longa que será cancelada
      await new Promise((r) => setTimeout(r, 5000));
      return resultadoFake;
    });
    aba.montar();
    const btnBasico = raiz.querySelector("#diag-basico") as HTMLButtonElement;
    btnBasico.click();
    await new Promise((r) => setTimeout(r, 10));
    const btnCancelar = raiz.querySelector("#diag-cancelar") as HTMLButtonElement;
    expect(btnCancelar.disabled).toBe(false);
    btnCancelar.click();
    await new Promise((r) => setTimeout(r, 10));
    expect(mockInvoke).toHaveBeenCalledWith("cancelar_diagnostico");
  });

  it("erro na execucao exibe mensagem", async () => {
    mockInvoke.mockRejectedValue(new Error("python não encontrado"));
    aba.montar();
    const btn = raiz.querySelector("#diag-basico") as HTMLButtonElement;
    btn.click();
    await new Promise((r) => setTimeout(r, 50));
    const texto = raiz.querySelector("#diag-texto") as HTMLSpanElement;
    expect(texto.textContent).toContain("Erro");
    expect(texto.textContent).toContain("python não encontrado");
  });
});