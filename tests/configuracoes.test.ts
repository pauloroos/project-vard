import { describe, it, expect, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

import { Configuracoes, type DepsConfiguracoes } from "../src/ui/configuracoes";
import { CONFIG_PADRAO } from "../src/config/config";

// DOM mínimo: o suficiente para o método (os testes rodam em node, sem navegador).
class No {
  checked = false;
  caixas = new Map<string, No>();
  querySelector(sel: string) {
    if (!this.caixas.has(sel)) this.caixas.set(sel, new No());
    return this.caixas.get(sel)!;
  }
}
const caixa = (raiz: No, id: string) => raiz.querySelector(`#cfg-${id}`);

function montar() {
  const raiz = new No();
  const cfg = { ...CONFIG_PADRAO, atalhos: { ...CONFIG_PADRAO.atalhos } };
  const painel = new Configuracoes(cfg, raiz as unknown as HTMLElement, {} as DepsConfiguracoes);
  return { painel, raiz, cfg };
}

describe("Configuracoes.mudouNaoOuvirFalar", () => {
  it("atualiza as duas caixas do formulário", () => {
    const t = montar();
    t.painel.mudouNaoOuvirFalar({ nao_ouvir: true, nao_falar: true });
    expect(caixa(t.raiz, "nao_ouvir").checked).toBe(true);
    expect(caixa(t.raiz, "nao_falar").checked).toBe(true);
    t.painel.mudouNaoOuvirFalar({ nao_ouvir: false, nao_falar: false });
    expect(caixa(t.raiz, "nao_ouvir").checked).toBe(false);
    expect(caixa(t.raiz, "nao_falar").checked).toBe(false);
  });

  it("atualiza a config guardada: um Salvar depois não devolve os valores antigos", () => {
    const t = montar();
    caixa(t.raiz, "nao_ouvir").checked = true; // valor velho no formulário, lido do disco ao abrir
    caixa(t.raiz, "nao_falar").checked = false;
    t.painel.mudouNaoOuvirFalar({ nao_ouvir: false, nao_falar: true });
    expect(t.cfg.nao_ouvir).toBe(false);
    expect(t.cfg.nao_falar).toBe(true);
  });
});
