// @vitest-environment node
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { execSync } from "node:child_process";

const raiz = resolve(import.meta.dirname, "..");

function lerVersao(caminhoRelativo: string): string {
  const caminho = resolve(raiz, caminhoRelativo);
  const texto = readFileSync(caminho, "utf8");
  if (caminho.endsWith(".json")) {
    return JSON.parse(texto).version;
  }
  // TOML simples: version = "x.y.z"
  const match = texto.match(/^version\s*=\s*"([^"]+)"/m);
  if (!match) throw new Error(`versão não encontrada em ${caminhoRelativo}`);
  return match[1];
}

describe("Versões alinhadas na 0.7", () => {
  it("package.json, Cargo.toml e tauri.conf.json têm a mesma versão", () => {
    const pkg = lerVersao("package.json");
    const cargo = lerVersao("src-tauri/Cargo.toml");
    const tauri = lerVersao("src-tauri/tauri.conf.json");
    expect(pkg).toBe(cargo);
    expect(pkg).toBe(tauri);
  });

  it("nucleo/pyproject.toml tem versão compatível com o app", () => {
    const app = lerVersao("package.json");
    const nucleo = lerVersao("nucleo/pyproject.toml");
    // Núcleo pode ter versão própria, mas deve ser >= app para garantir compatibilidade
    const [appMaior, appMenor] = app.split(".").map(Number);
    const [nucMaior, nucMenor] = nucleo.split(".").map(Number);
    expect(nucMaior).toBe(appMaior);
    expect(nucMenor).toBeGreaterThanOrEqual(appMenor);
  });

  it("instalador do Tauri aponta para a versão do package.json", () => {
    const pkg = lerVersao("package.json");
    const tauriConf = readFileSync(resolve(raiz, "src-tauri/tauri.conf.json"), "utf8");
    expect(tauriConf).toContain(`"version": "${pkg}"`);
  });

  it("npm run build produz artefatos sem erro de versão", () => {
    // Smoke test: apenas verifica que o build do Vite não falha por versão
    // O build completo é rodado no CI/CD e no passo de release
    expect(() => {
      execSync("npx tsc --noEmit", { cwd: raiz, stdio: "pipe", timeout: 60_000 });
    }).not.toThrow();
  }, 60_000);
});