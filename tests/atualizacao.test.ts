import { describe, it, expect, beforeAll, afterAll } from "vitest";
// @ts-expect-error módulo .mjs sem tipos
import { criarServidor } from "./harness/servidor-falso.mjs";
import { interpretarRelease } from "../src/atualizacao/release";

describe("atualização contra o harness", () => {
  let srv: ReturnType<typeof criarServidor>; let base = "";
  beforeAll(async () => {
    srv = criarServidor({ release: true });
    await new Promise<void>((r) => srv.listen(0, "127.0.0.1", () => r()));
    base = `http://127.0.0.1:${(srv.address() as { port: number }).port}`;
  });
  afterAll(() => srv.close());
  it("lista_a_release_falsa_com_setup", async () => {
    const r = await fetch(`${base}/repos/pauloroos/project-vard/releases/latest`);
    const rel = interpretarRelease(await r.json(), "0.3.0")!;
    expect(rel.versao).toBe("9.9.9");
    expect(rel.maisNova).toBe(true);
    expect(rel.setup!.nome).toBe("Vard_9.9.9_x64-setup.exe");
    const d = await fetch(rel.setup!.url.replace(/^http:\/\/127\.0\.0\.1:\d+/, base));
    expect((await d.arrayBuffer()).byteLength).toBe(rel.setup!.bytes);
  });
  it("sem_release_e_404", async () => {
    const s2 = criarServidor(); await new Promise<void>((r) => s2.listen(0, "127.0.0.1", () => r()));
    const b2 = `http://127.0.0.1:${(s2.address() as { port: number }).port}`;
    expect((await fetch(`${b2}/repos/pauloroos/project-vard/releases/latest`)).status).toBe(404);
    s2.close();
  });
});
