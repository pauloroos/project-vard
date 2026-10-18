import { afterEach, describe, expect, it, vi } from "vitest";
import { MonitorRecursos, PRAZO_RECURSOS_MS, INTERVALO_RECURSOS_MS } from "../src/ui/monitor-recursos";

const RESPOSTA = {
  componentes: [
    { nome: "Widget", memoria_mb: 300, cpu_percent: 1.5, pids: [10], detalhes: "" },
    { nome: "Núcleo", memoria_mb: 120, cpu_percent: 0.5, pids: [20], detalhes: "" },
  ],
  externos: [],
  total_memoria_mb: 420,
  total_cpu_percent: 2,
};

function montar() {
  const raiz = document.createElement("div");
  document.body.append(raiz);
  const monitor = new MonitorRecursos(raiz, { urlNucleo: () => "http://127.0.0.1:4700" });
  return { raiz, monitor };
}

describe("MonitorRecursos", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); document.body.innerHTML = ""; });

  it("prazo da leitura cobre o /recursos e fica abaixo do intervalo", () => {
    expect(PRAZO_RECURSOS_MS).toBeGreaterThanOrEqual(4000);
    expect(PRAZO_RECURSOS_MS).toBeLessThan(INTERVALO_RECURSOS_MS * 2);
  });

  it("uma leitura por vez: montar e ativar juntos não disparam duas consultas", async () => {
    let soltar!: (r: Response) => void;
    const f = vi.fn(() => new Promise<Response>((r) => { soltar = r; }));
    vi.stubGlobal("fetch", f);
    const { raiz, monitor } = montar();
    monitor.montar();
    monitor.ativar();
    expect(f).toHaveBeenCalledTimes(1);
    soltar(new Response(JSON.stringify(RESPOSTA)));
    await vi.waitFor(() => expect(raiz.textContent).toContain("Núcleo"));
    monitor.desativar();
  });

  it("uma resposta lenta (6 s) ainda chega à tela", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_u: string, init?: RequestInit) => new Promise<Response>((resolver, rejeitar) => {
      const t = setTimeout(() => resolver(new Response(JSON.stringify(RESPOSTA))), 6000);
      init?.signal?.addEventListener("abort", () => { clearTimeout(t); rejeitar(new DOMException("abortado", "AbortError")); });
    })));
    const { raiz, monitor } = montar();
    monitor.montar();
    await vi.advanceTimersByTimeAsync(6100);
    expect(raiz.textContent).toContain("420.0 MB");
  });

  it("falha depois de uma leitura boa mantém a tabela e avisa", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify(RESPOSTA)));
    vi.stubGlobal("fetch", f);
    const { raiz, monitor } = montar();
    monitor.montar();
    await vi.waitFor(() => expect(raiz.textContent).toContain("Núcleo"));
    f.mockImplementation(async () => { throw new Error("sem rede"); });
    monitor.ativar();
    await vi.waitFor(() => expect(raiz.querySelector(".aviso")?.textContent).toContain("Não consegui atualizar"));
    expect(raiz.textContent).toContain("Núcleo");
    monitor.desativar();
  });
});
