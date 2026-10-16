import { describe, it, expect, vi } from "vitest";
import { DetectorSelecionavel, ControleCapturaVoz, pareceEco, type CarregarSilero } from "../src/audio/vad-selecionavel";

function montar(tipo: "energia" | "silero" = "energia", falhar = false) {
  let quadro: (p: number) => void = () => {};
  const destruir = vi.fn(async () => {});
  const carregar: CarregarSilero = vi.fn(async (_mic, cb) => {
    if (falhar) throw new Error("modelo indisponível");
    quadro = cb; return { destruir };
  });
  const mic = { contexto: { sampleRate: 48000 }, stream: {} } as unknown as Parameters<DetectorSelecionavel["iniciar"]>[0];
  const d = new DetectorSelecionavel(tipo, { limiar: .02, inicioMs: 150, fimMs: 100, tetoMs: 12000 }, carregar);
  return { d, mic, carregar, destruir, quadro: (p: number) => quadro(p) };
}
describe("detector selecionável", () => {
  it("energia mantém início e fim atuais sem carregar modelo", async () => {
    const t = montar(); await t.d.iniciar(t.mic);
    expect(t.d.alimentar(.03, 0)).toBeNull(); expect(t.d.alimentar(.03, 150)).toBe("inicio");
    expect(t.d.alimentar(0, 200)).toBeNull(); expect(t.d.alimentar(0, 300)).toBe("fim");
    expect(t.carregar).not.toHaveBeenCalled();
  });
  it("Silero decide início e fim mesmo com energia alta", async () => {
    const t = montar("silero"); await t.d.iniciar(t.mic);
    expect(t.d.alimentar(1, 0)).toBeNull();
    t.quadro(.95); t.d.alimentar(.1, 10); t.quadro(.95);
    expect(t.d.alimentar(.1, 160)).toBe("inicio");
    t.quadro(0); t.d.alimentar(1, 200); t.quadro(0);
    expect(t.d.alimentar(1, 300)).toBe("fim");
  });
  it("falha ao carregar avisa sem expor erro e volta à energia", async () => {
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = montar("silero", true); await t.d.iniciar(t.mic);
    t.d.alimentar(.1, 0); expect(t.d.alimentar(.1, 150)).toBe("inicio");
    expect(aviso).toHaveBeenCalledWith("Silero indisponível; usando detector de energia."); aviso.mockRestore();
  });
  it("fechar durante carga destrói modelo tardio", async () => {
    const t = montar("silero"); const p = t.d.iniciar(t.mic); t.d.fechar(); await p;
    expect(t.destruir).toHaveBeenCalledOnce();
  });
});
const livre = { falando: false, ocupado: false, mudo: false, reuniao: false, jogo: false, ptt: false, eco: false };
describe("interrupção por voz", () => {
  function montarControle(ligada = true) {
    const parar = vi.fn(), capturar = vi.fn(), encerrar = vi.fn();
    const controle = new ControleCapturaVoz(ligada, { interromper: parar, capturar, encerrar });
    return { controle, parar, capturar, encerrar };
  }
  it("início confirmado para boca/cancela pedido e captura nova fala", () => {
    const t = montarControle(); t.controle.processar("inicio", { ...livre, falando: true, ocupado: true });
    expect(t.parar).toHaveBeenCalledOnce(); expect(t.capturar).toHaveBeenCalledOnce();
    expect(t.parar.mock.invocationCallOrder[0]).toBeLessThan(t.capturar.mock.invocationCallOrder[0]);
    t.controle.processar("fim", livre); expect(t.encerrar).toHaveBeenCalledOnce();
  });
  it("opção desligada mantém bloqueio durante resposta", () => {
    const t = montarControle(false); t.controle.processar("inicio", { ...livre, falando: true }); expect(t.parar).not.toHaveBeenCalled(); expect(t.capturar).not.toHaveBeenCalled();
  });
  it.each(["eco", "mudo", "reuniao", "jogo", "ptt"] as const)("%s não interrompe nem captura", (chave) => {
    const t = montarControle(); t.controle.processar("inicio", { ...livre, falando: true, [chave]: true });
    expect(t.parar).not.toHaveBeenCalled(); expect(t.capturar).not.toHaveBeenCalled();
  });
  it("energia da própria saída e cópia atrasada são eco", () => {
    const saida = Float32Array.from({ length: 128 }, (_, i) => Math.sin(i * .31) * .2);
    expect(pareceEco(saida.map(x => x * .3), [saida])).toBe(true);
    expect(pareceEco(saida.map(x => x * 2), [saida])).toBe(true);
    const usuario = Float32Array.from({ length: 128 }, (_, i) => Math.sin(i * .87) * .5);
    expect(pareceEco(usuario, [saida])).toBe(false);
  });
});
it("voz baixa independente da saída também pode interromper com fones", () => {
  const saida = Float32Array.from({ length: 128 }, (_, i) => Math.sin(i * .31) * .2);
  const usuario = Float32Array.from({ length: 128 }, (_, i) => Math.sin(i * .87) * .04);
  expect(pareceEco(usuario, [saida])).toBe(false);
});
