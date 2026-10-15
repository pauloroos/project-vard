import { describe, it, expect } from "vitest";
import { compararVersoes, interpretarRelease, URL_RELEASE } from "../src/atualizacao/release";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const release = {
  tag_name: "v0.4.0", name: "Vard 0.4.0", body: "Notas\n- item", published_at: "2026-11-01T10:00:00Z",
  html_url: "https://github.com/pauloroos/project-vard/releases/tag/v0.4.0",
  assets: [
    { name: "Vard_0.4.0_x64_en-US.msi", browser_download_url: "https://github.com/x/Vard_0.4.0_x64_en-US.msi", size: 10 },
    { name: "Vard_0.4.0_x64-setup.exe", browser_download_url: "https://github.com/x/Vard_0.4.0_x64-setup.exe", size: 4321, digest: "sha256:ABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABAB" },
  ],
};

describe("compararVersoes", () => {
  it("numerico", () => {
    expect(compararVersoes("0.3.0", "0.2.2")).toBe(1);
    expect(compararVersoes("0.2.2", "0.10.0")).toBe(-1);
    expect(compararVersoes("v1.0.0", "1.0.0")).toBe(0);
    expect(compararVersoes("1.0.0-beta", "1.0.0")).toBe(-1);
    expect(compararVersoes("1.0", "1.0.0")).toBe(0);
  });
});

describe("interpretarRelease", () => {
  it("le_a_release_e_acha_o_setup", () => {
    const r = interpretarRelease(release, "0.3.0")!;
    expect(r.versao).toBe("0.4.0");
    expect(r.maisNova).toBe(true);
    expect(r.setup).toEqual({ nome: "Vard_0.4.0_x64-setup.exe", url: "https://github.com/x/Vard_0.4.0_x64-setup.exe", bytes: 4321, sha256: "abababababababababababababababababababababababababababababababab" });
    expect(r.notas).toBe("Notas\n- item");
  });
  it("digest_ausente_ou_invalido_vira_null", () => {
    const a = { ...release.assets[1] } as Record<string, unknown>;
    delete a.digest;
    expect(interpretarRelease({ ...release, assets: [a] }, "0.3.0")!.setup!.sha256).toBeNull();
    expect(interpretarRelease({ ...release, assets: [{ ...a, digest: "md5:abc" }] }, "0.3.0")!.setup!.sha256).toBeNull();
  });
  it("mesma_versao_nao_e_mais_nova", () => { expect(interpretarRelease(release, "0.4.0")!.maisNova).toBe(false); });
  it("sem_setup_vira_null", () => { expect(interpretarRelease({ ...release, assets: [release.assets[0]] }, "0.3.0")!.setup).toBeNull(); });
  it("malformado_vira_null", () => {
    expect(interpretarRelease(null, "0.3.0")).toBeNull();
    expect(interpretarRelease({ tag_name: 5 }, "0.3.0")).toBeNull();
    expect(interpretarRelease("texto", "0.3.0")).toBeNull();
  });
  it("url_oficial", () => { expect(URL_RELEASE).toBe("https://api.github.com/repos/pauloroos/project-vard/releases/latest"); });
});

// --- Testes da T2: runtime Python 3.13 embutido ---

const RAIZ = resolve(import.meta.dirname, "..");
const BUILD_NUCLEO = join(RAIZ, "build", "nucleo");
const MEDIDAS = join(RAIZ, "build", "nucleo-medidas.json");
const PYTHON_EMBUTIDO = join(BUILD_NUCLEO, "python", "python.exe");

describe("release T2 — runtime Python 3.13 embutido", () => {
  it("runtime.toml existe com versao 3.13.x, url oficial e sha256 valido", () => {
    const toml = readFileSync(join(RAIZ, "nucleo", "runtime.toml"), "utf8");
    expect(toml).toMatch(/versao\s*=\s*"3\.13\.\d+"/);
    expect(toml).toMatch(/url\s*=\s*"https:\/\/github\.com\/astral-sh\/python-build-standalone\//);
    expect(toml).toMatch(/sha256\s*=\s*"[0-9a-f]{64}"/);
  });

  it("montar-nucleo.ps1 existe e referencia vard (nao vard_nucleo)", () => {
    const script = readFileSync(join(RAIZ, "scripts", "windows", "montar-nucleo.ps1"), "utf8");
    expect(script).toContain("-m vard --versao");
    expect(script).toContain("vard.server");
    expect(script).not.toContain("vard_nucleo");
  });

  it("tauri.nucleo.conf.json aponta build/nucleo como recurso", () => {
    const conf = JSON.parse(
      readFileSync(join(RAIZ, "src-tauri", "tauri.nucleo.conf.json"), "utf8"),
    );
    expect(conf.bundle?.resources).toBeDefined();
    const recursos = conf.bundle.resources;
    const chave = Object.keys(recursos).find((k) => k.includes("build/nucleo"));
    expect(chave).toBeDefined();
    expect(recursos[chave!]).toBe("nucleo/");
  });

  it("package.json tem script nucleo que chama montar-nucleo.ps1", () => {
    const pkg = JSON.parse(readFileSync(join(RAIZ, "package.json"), "utf8"));
    expect(pkg.scripts?.nucleo).toContain("montar-nucleo.ps1");
  });

  it("bundle montado existe com python.exe e medidas validas", () => {
    if (!existsSync(PYTHON_EMBUTIDO)) {
      throw new Error(`runtime nao montado: ${PYTHON_EMBUTIDO} ausente (rode npm run nucleo)`);
    }
    expect(existsSync(MEDIDAS)).toBe(true);
    const dados = JSON.parse(readFileSync(MEDIDAS, "utf8"));
    expect(dados.python).toMatch(/^3\.13\./);
    expect(dados.bytes_total).toBeGreaterThan(0);
    expect(dados.arquivos).toBeGreaterThan(0);
    expect(dados.maior_caminho_len).toBeLessThanOrEqual(160);
  });
});