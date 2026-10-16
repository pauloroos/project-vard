import { it, expect, vi } from "vitest";
import { Conversa, type DepsConversa } from "../src/fala/conversa";
import { CONFIG_PADRAO } from "../src/config/config";
function montar() {
  const d: DepsConversa = {
    config: { ...CONFIG_PADRAO, conversa_ms: 0 },
    oj: { perguntar: vi.fn(async () => "resposta"), sintetizar: vi.fn(async () => new ArrayBuffer(8)) },
    boca: { falando: false, tocar: vi.fn(async () => {}), parar: vi.fn() }, falas: vi.fn(async () => new ArrayBuffer(8)),
    cerebro: "proprio", sessaoVoz: () => "sessao-ficticia",
    ponte: { ver: vi.fn(), modo: vi.fn(), pedir: vi.fn(), cancelar: vi.fn(async () => ({ estado: "cancelado" })), consultarPedido: vi.fn(async () => null) },
    aoResposta: vi.fn(),
  };
  return { d, c: new Conversa(d) };
}
it("interrupção durante admissão cancela pedido próprio tardio", async () => {
  const { d, c } = montar();
  let admitir!: (v: { pedido_id: string; sessao_id: string; estado: string }) => void;
  d.ponte!.pedir = () => new Promise(r => { admitir = r; });
  const p = c.aoTextoTranscrito("vard, explique", true);
  await vi.waitFor(() => expect(admitir).toBeDefined()); c.interromper();
  admitir({ pedido_id: "pedido-ficticio", sessao_id: "sessao-ficticia", estado: "na_fila" }); await p;
  expect(d.ponte!.cancelar).toHaveBeenCalledWith("pedido-ficticio");
});
it("interrupção durante reconciliação cancela pedido sem aguardar consulta", async () => {
  const { d, c } = montar();
  d.ponte!.pedir = async () => ({ pedido_id: "pedido-ficticio", sessao_id: "sessao-ficticia", estado: "executando" });
  let resolver!: (v: null) => void;
  d.ponte!.consultarPedido = vi.fn(() => new Promise<null>(r => { resolver = r; }));
  const p = c.aoTextoTranscrito("vard, explique", true);
  await vi.waitFor(() => expect(resolver).toBeDefined()); c.interromper();
  expect(d.ponte!.cancelar).toHaveBeenCalledWith("pedido-ficticio"); resolver(null); await p;
});
it("interrupção para boca e ignora resposta OpenJarvis pendente", async () => {
  const { d, c } = montar(); d.cerebro = "openjarvis";
  let responder!: (v: string) => void;
  d.oj.perguntar = () => new Promise(r => { responder = r; });
  const p = c.aoTextoTranscrito("vard, explique", true);
  await vi.waitFor(() => expect(responder).toBeDefined()); c.interromper(); responder("resposta tardia"); await p;
  expect(d.boca.parar).toHaveBeenCalledOnce(); expect(d.aoResposta).not.toHaveBeenCalled(); expect(d.boca.tocar).not.toHaveBeenCalled();
});
it("fala por cima durante reprodução cancela pedido próprio e corta boca", async () => {
  const { d, c } = montar();
  d.ponte!.pedir = async () => ({ pedido_id: "pedido-ficticio", sessao_id: "sessao-ficticia", estado: "executando" });
  let terminar!: () => void;
  d.boca.tocar = () => new Promise<void>(r => { terminar = r; d.boca.falando = true; });
  d.boca.parar = vi.fn(() => { d.boca.falando = false; terminar?.(); });
  const p = c.aoTextoTranscrito("vard, explique", true);
  await vi.waitFor(() => expect(d.ponte!.consultarPedido).toHaveBeenCalled());
  for (const [seq, evento_tipo, dados] of [[1, "texto", { texto: "resposta própria" }], [2, "fim", {}]] as const) {
    window.dispatchEvent(new MessageEvent("vard-evento-pedido", { data: JSON.stringify({ tipo: "pedido", pedido_id: "pedido-ficticio", sessao_id: "sessao-ficticia", seq, evento_tipo, dados }) }));
  }
  await vi.waitFor(() => expect(d.boca.falando).toBe(true));
  c.interromper(); await p;
  expect(d.boca.parar).toHaveBeenCalled(); expect(d.boca.falando).toBe(false);
  expect(d.ponte!.cancelar).toHaveBeenCalledWith("pedido-ficticio");
});
