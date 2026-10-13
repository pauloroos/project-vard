import { describe, it, expect } from "vitest";
import { compararVersoes, interpretarRelease, URL_RELEASE } from "../src/atualizacao/release";

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
