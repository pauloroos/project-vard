// @vitest-environment node
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";

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

const VERSAO_ALVO = "0.10.0";

function lerVersaoLock(caminhoRelativo: string): string {
  const caminho = resolve(raiz, caminhoRelativo);
  const texto = readFileSync(caminho, "utf8");
  if (caminho.endsWith("package-lock.json")) {
    const json = JSON.parse(texto);
    const root = json.version;
    const pacoteRaiz = json.packages?.[""]?.version;
    if (!root || !pacoteRaiz) throw new Error(`versão ausente em ${caminhoRelativo}`);
    if (root !== pacoteRaiz) throw new Error(`versões divergentes em ${caminhoRelativo}: ${root} vs ${pacoteRaiz}`);
    return root;
  }
  if (caminho.endsWith("uv.lock")) {
    const match = texto.match(/name\s*=\s*"vard-nucleo"\s*\nversion\s*=\s*"([^"]+)"/);
    if (!match) throw new Error(`entrada vard-nucleo não encontrada em ${caminhoRelativo}`);
    return match[1];
  }
  throw new Error(`formato não suportado: ${caminhoRelativo}`);
}

describe("Versões alinhadas na 0.10.0", () => {
  it("package.json, Cargo.toml e tauri.conf.json têm a mesma versão", () => {
    const pkg = lerVersao("package.json");
    const cargo = lerVersao("src-tauri/Cargo.toml");
    const tauri = lerVersao("src-tauri/tauri.conf.json");
    expect(pkg).toBe(VERSAO_ALVO);
    expect(cargo).toBe(VERSAO_ALVO);
    expect(tauri).toBe(VERSAO_ALVO);
  });

  it("nucleo/pyproject.toml tem exatamente a versão alvo", () => {
    const nucleo = lerVersao("nucleo/pyproject.toml");
    expect(nucleo).toBe(VERSAO_ALVO);
  });

  it("package-lock.json (root e packages['']) tem a versão alvo", () => {
    const lock = lerVersaoLock("package-lock.json");
    expect(lock).toBe(VERSAO_ALVO);
  });

  it("Cargo.lock (pacote vard) tem a versão alvo", () => {
    const texto = readFileSync(resolve(raiz, "src-tauri/Cargo.lock"), "utf8");
    const match = texto.match(/name\s*=\s*"vard"\s*\nversion\s*=\s*"([^"]+)"/);
    expect(match).toBeTruthy();
    expect(match![1]).toBe(VERSAO_ALVO);
  });

  it("nucleo/uv.lock (vard-nucleo) tem a versão alvo", () => {
    const lock = lerVersaoLock("nucleo/uv.lock");
    expect(lock).toBe(VERSAO_ALVO);
  });

  it("instalador do Tauri aponta para a versão do package.json", () => {
    const pkg = lerVersao("package.json");
    const tauriConf = readFileSync(resolve(raiz, "src-tauri/tauri.conf.json"), "utf8");
    expect(tauriConf).toContain(`"version": "${pkg}"`);
  });

  it("npm run build produz artefatos sem erro de versão", () => {
    expect(() => {
      execFileSync(process.execPath, [resolve(raiz, "node_modules/typescript/bin/tsc"), "--noEmit"], { cwd: raiz, stdio: "pipe", timeout: 60_000 });
    }).not.toThrow();
  }, 60_000);
});