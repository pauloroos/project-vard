import { it, expect } from "vitest";
import { readFileSync } from "node:fs";
it("CSP permite WebAssembly local sem liberar scripts externos", () => {
  const cfg = JSON.parse(readFileSync("src-tauri/tauri.conf.json", "utf8"));
  const csp: string = cfg.app.security.csp;
  expect(csp).toContain("'wasm-unsafe-eval'");
  expect(csp).not.toContain("'unsafe-eval'");
});
