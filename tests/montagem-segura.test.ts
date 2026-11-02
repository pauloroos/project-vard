// @vitest-environment node
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

const powershell = process.env.VARD_TEST_POWERSHELL || (process.platform === "win32" ? "powershell" : "pwsh");
const disponivel = spawnSync(powershell, ["-NoProfile", "-Command", "exit 0"]).status === 0;

describe.skipIf(!disponivel)("montagem segura do núcleo", () => {
  it.each(["build", "cache", "nucleo"])("recusa link em %s sem tocar no destino externo", (local) => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-link-"));
    try {
      const scripts = join(raiz, "scripts", "windows");
      const nucleo = join(raiz, "nucleo");
      const externo = join(raiz, "externo");
      for (const pasta of [scripts, nucleo, externo]) mkdirSync(pasta, { recursive: true });
      copyFileSync(resolve("scripts/windows/montar-nucleo.ps1"), join(scripts, "montar-nucleo.ps1"));
      writeFileSync(join(nucleo, "runtime.toml"), `versao = "3.13.0"\nurl = "https://github.com/exemplo/runtime.tar.gz"\nsha256 = "${"0".repeat(64)}"\n`);
      if (local !== "build") mkdirSync(join(raiz, "build"));
      symlinkSync(externo, local === "build" ? join(raiz, "build") : join(raiz, "build", local), "junction");
      const sentinela = join(externo, "sentinela.txt");
      writeFileSync(sentinela, "preservado");
      const resultado = spawnSync(powershell, ["-NoProfile", "-File", join(scripts, "montar-nucleo.ps1"), "-SoVerificar"], { encoding: "utf8", timeout: 15000 });
      expect(resultado.status).not.toBe(0);
      expect(resultado.stderr + resultado.stdout).toMatch(/link|reparse/i);
      expect(readFileSync(sentinela, "utf8")).toBe("preservado");
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });

  it.each(["nucleo-medidas.json", "requisitos.txt"])("recusa %s preexistente antes da montagem", (nome) => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-medidas-"));
    try {
      const scripts = join(raiz, "scripts", "windows");
      const nucleo = join(raiz, "nucleo");
      const build = join(raiz, "build");
      for (const pasta of [scripts, nucleo, build, join(build, "cache")]) mkdirSync(pasta, { recursive: true });
      copyFileSync(resolve("scripts/windows/montar-nucleo.ps1"), join(scripts, "montar-nucleo.ps1"));
      writeFileSync(join(nucleo, "runtime.toml"), `versao = "3.13.0"\nurl = "https://github.com/exemplo/runtime.tar.gz"\nsha256 = "${"0".repeat(64)}"\n`);
      writeFileSync(join(build, "cache", "runtime.tar.gz"), "arquivo inválido sem download");
      const sentinela = join(build, nome);
      writeFileSync(sentinela, "preservado");
      const resultado = spawnSync(powershell, ["-NoProfile", "-File", join(scripts, "montar-nucleo.ps1")], { encoding: "utf8", timeout: 15000 });
      expect(resultado.status).not.toBe(0);
      expect(resultado.stderr + resultado.stdout).toMatch(/(medidas|requisitos).*existe/i);
      expect(readFileSync(sentinela, "utf8")).toBe("preservado");
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });
  it.each(["arquivo-pessoal.txt", "segredos.toml"])("preserva %s e falha antes de montar", (nome) => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-montagem-"));
    try {
      const scripts = join(raiz, "scripts", "windows");
      const nucleo = join(raiz, "nucleo");
      const destino = join(raiz, "build", "nucleo");
      const cache = join(raiz, "build", "cache");
      for (const pasta of [scripts, nucleo, destino, cache]) mkdirSync(pasta, { recursive: true });
      copyFileSync(resolve("scripts/windows/montar-nucleo.ps1"), join(scripts, "montar-nucleo.ps1"));
      const conteudo = Buffer.from("arquivo de teste");
      const hash = createHash("sha256").update(conteudo).digest("hex");
      writeFileSync(join(cache, "runtime.tar.gz"), conteudo);
      writeFileSync(join(nucleo, "runtime.toml"), `versao = "3.13.0"\nurl = "https://github.com/exemplo/runtime.tar.gz"\nsha256 = "${hash}"\n`);
      const sentinela = join(destino, nome);
      writeFileSync(sentinela, "conteúdo preservado");
      const resultado = spawnSync(powershell, ["-NoProfile", "-File", join(scripts, "montar-nucleo.ps1")], { encoding: "utf8", timeout: 15000 });
      expect(resultado.status).not.toBe(0);
      expect(existsSync(sentinela)).toBe(true);
      expect(readFileSync(sentinela, "utf8")).toBe("conteúdo preservado");
      expect(resultado.stderr + resultado.stdout).toMatch(/destino.*(existe|existente)/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });

  it.each([[], ["-SoVerificar"]])("preserva arquivo existente no cache com hash incorreto (%s)", (...args: string[]) => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-cache-"));
    try {
      const scripts = join(raiz, "scripts", "windows");
      const nucleo = join(raiz, "nucleo");
      const cache = join(raiz, "build", "cache");
      for (const pasta of [scripts, nucleo, cache]) mkdirSync(pasta, { recursive: true });
      copyFileSync(resolve("scripts/windows/montar-nucleo.ps1"), join(scripts, "montar-nucleo.ps1"));
      writeFileSync(join(nucleo, "runtime.toml"), `versao = "3.13.0"\nurl = "https://github.com/exemplo/runtime.tar.gz"\nsha256 = "${"0".repeat(64)}"\n`);
      const arquivo = join(cache, "runtime.tar.gz");
      writeFileSync(arquivo, "conteúdo preservado");
      const resultado = spawnSync(powershell, ["-NoProfile", "-File", join(scripts, "montar-nucleo.ps1"), ...args], { encoding: "utf8", timeout: 15000 });
      expect(resultado.status).not.toBe(0);
      expect(existsSync(arquivo)).toBe(true);
      expect(readFileSync(arquivo, "utf8")).toBe("conteúdo preservado");
      expect(resultado.stderr + resultado.stdout).toMatch(/sha256/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });
});

// --- Pit stop: sem sobrescrita em corrida + pyc sem caminho de build ---
// Testes sintéticos: nenhum faz download real.

const lerMontagem = () => readFileSync(resolve("scripts/windows/montar-nucleo.ps1"), "utf8");

describe.skipIf(!disponivel)("montagem sem sobrescrita em corrida", () => {
  it("não baixa direto no caminho final: usa temporário próprio e publicação exclusiva", () => {
    const texto = lerMontagem();
    expect(texto).not.toMatch(/Invoke-WebRequest[^;\n{]*-OutFile\s+\$arquivo\b/);
    expect(texto).toMatch(/\$tempArquivo/);
    expect(texto).toMatch(/\[System\.IO\.File\]::Move\(\$tempArquivo,\s*\$arquivo\)/);
  });

  it("não reabre o arquivo reservado: uv escreve no temporário e publica sem sobrescrever", () => {
    const texto = lerMontagem();
    expect(texto).not.toMatch(/uv export[^;\n{]*-o\s+\$requisitos\b/);
    expect(texto).toMatch(/\$tempRequisitos/);
    expect(texto).toMatch(/\[System\.IO\.File\]::Move\(\$tempRequisitos,\s*\$requisitos\)/);
    expect(texto).toMatch(/CreateNew/);
  });

  it("criação exclusiva e Move sem sobrescrever preservam dados em corrida sintética", () => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-corrida-"));
    try {
      const roteiro = join(raiz, "corrida.ps1");
      const final = join(raiz, "final.bin");
      const perdedor = join(raiz, "perdedor.bin");
      writeFileSync(final, "vencedor");
      writeFileSync(perdedor, "perdedor");
      writeFileSync(
        roteiro,
        [
          "$ErrorActionPreference = 'Stop'",
          `$final = '${final.replace(/'/g, "''")}'`,
          `$perdedor = '${perdedor.replace(/'/g, "''")}'`,
          "try {",
          "  $r = [System.IO.File]::Open($final, [System.IO.FileMode]::CreateNew)",
          "  $r.Dispose()",
          "  Write-Host 'FALHA: CreateNew sobrescreveu'",
          "  exit 1",
          "} catch [System.IO.IOException] { Write-Host 'CreateNew recusou (ok)' }",
          "try {",
          "  [System.IO.File]::Move($perdedor, $final)",
          "  Write-Host 'FALHA: Move sobrescreveu'",
          "  exit 1",
          "} catch [System.IO.IOException] { Write-Host 'Move recusou (ok)' }",
        ].join("\n"),
      );
      const resultado = spawnSync(powershell, ["-NoProfile", "-File", roteiro], { encoding: "utf8", timeout: 15000 });
      expect(resultado.status).toBe(0);
      expect(resultado.stdout).toMatch(/CreateNew recusou/);
      expect(resultado.stdout).toMatch(/Move recusou/);
      expect(readFileSync(final, "utf8")).toBe("vencedor");
      expect(readFileSync(perdedor, "utf8")).toBe("perdedor");
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });
});

describe.skipIf(!disponivel)("montagem sem caminho da máquina (direct_url.json)", () => {
  const montarRaizFicticia = (raiz: string) => {
    const scripts = join(raiz, "scripts", "windows");
    const nucleo = join(raiz, "nucleo");
    const distInfo = join(raiz, "build", "nucleo", "python", "Lib", "site-packages", "vard-0.1.dist-info");
    for (const pasta of [scripts, nucleo, distInfo]) mkdirSync(pasta, { recursive: true });
    copyFileSync(resolve("scripts/windows/montar-nucleo.ps1"), join(scripts, "montar-nucleo.ps1"));
    writeFileSync(join(nucleo, "runtime.toml"), `versao = "3.13.0"\nurl = "https://github.com/exemplo/runtime.tar.gz"\nsha256 = "${"0".repeat(64)}"\n`);
    return { scripts, distInfo };
  };
  const verificar = (scripts: string) =>
    spawnSync(powershell, ["-NoProfile", "-File", join(scripts, "montar-nucleo.ps1"), "-SoVerificar"], { encoding: "utf8", timeout: 30000 });

  it("remove direct_url.json e metadata editável após instalar o vard, antes da varredura", () => {
    const texto = lerMontagem();
    // remoção cobre o arquivo PEP 610 e equivalentes de instalação editável
    expect(texto).toMatch(/direct_url\.json/);
    expect(texto).toMatch(/__editable__\*\.pth/);
    expect(texto).toMatch(/\*\.egg-link/);
    // ordem: instala o vard -> remove metadata -> varre o destino
    const idxInstalar = texto.indexOf("instalar o vard");
    const idxRemover = texto.indexOf("remover metadata com caminho da maquina");
    const idxVarredura = texto.indexOf("Validar-Caminhos-No-Destino $destinoSeguro");
    expect(idxInstalar).toBeGreaterThanOrEqual(0);
    expect(idxRemover).toBeGreaterThan(idxInstalar);
    expect(idxVarredura).toBeGreaterThan(idxRemover);
    // a varredura reprova file:/// e letra de unidade
    expect(texto).toMatch(/file:\/\/\//);
    expect(texto).toMatch(/\[A-Za-z\]:\[\\\\\/\]/);
  });

  it("varredura falha com direct_url.json sintético contendo file:/// (sem download)", () => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-directurl-"));
    try {
      const { scripts, distInfo } = montarRaizFicticia(raiz);
      writeFileSync(join(distInfo, "direct_url.json"), '{"url": "file:///C:/maquina/vard", "archive_info": null}');
      const resultado = verificar(scripts);
      expect(resultado.status).not.toBe(0);
      expect(resultado.stderr + resultado.stdout).toMatch(/direct_url|file:\/\/\/|caminho (da |absoluto)/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });

  it("varredura falha com letra de unidade em metadata sintética (sem download)", () => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-unidade-"));
    try {
      const { scripts, distInfo } = montarRaizFicticia(raiz);
      writeFileSync(join(distInfo, "RECORD"), "vard/__init__.py,sha256=abc,10\nC:\\maquina\\vard\\nucleo\\mod.py,sha256=def,20\n");
      const resultado = verificar(scripts);
      expect(resultado.status).not.toBe(0);
      expect(resultado.stderr + resultado.stdout).toMatch(/letra de unidade|caminho (da |absoluto)/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });

  it("varredura falha com caminho absoluto da máquina em metadata sintética (sem download)", () => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-abspath-"));
    try {
      const { scripts, distInfo } = montarRaizFicticia(raiz);
      const destino = join(raiz, "build", "nucleo");
      writeFileSync(join(distInfo, "RECORD"), `vard/__init__.py,sha256=abc,10\n${join(destino, "python", "x.py")},sha256=def,20\n`);
      const resultado = verificar(scripts);
      expect(resultado.status).not.toBe(0);
      expect(resultado.stderr + resultado.stdout).toMatch(/caminho absoluto|caminho (da |de maquina)/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });

  it("varredura passa com metadata sintética limpa (sem download)", () => {
    const raiz = mkdtempSync(join(tmpdir(), "vard-limpo-"));
    try {
      const { scripts, distInfo } = montarRaizFicticia(raiz);
      writeFileSync(join(distInfo, "RECORD"), "vard/__init__.py,sha256=abc,10\nvard/server.py,sha256=def,20\n");
      const resultado = verificar(scripts);
      expect(resultado.status).toBe(0);
      expect(resultado.stdout).toMatch(/verificacao concluida/i);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });
});

describe("pyc reproduzível sem caminho de build", () => {
  it("compileall usa caminho genérico (-s/-p) em vez do absoluto do build", () => {
    expect(lerMontagem()).toMatch(/compileall.*-s\s+\$pythonDir.*-p\s+\/nucleo/);
  });

  it("pyc sintético via marshal não guarda caminho de build", () => {
    const python = spawnSync("python3", ["--version"], { encoding: "utf8" });
    if (python.status !== 0) return;
    const raiz = mkdtempSync(join(tmpdir(), "vard-pyc-"));
    try {
      const pacote = join(raiz, "ficticio");
      mkdirSync(pacote, { recursive: true });
      writeFileSync(join(pacote, "mod.py"), "VALOR = 42\n");
      const compilar = spawnSync("python3", ["-I", "-m", "compileall", "-q", "-j", "0", "-s", raiz, "-p", "/nucleo", pacote], { encoding: "utf8", timeout: 30000 });
      expect(compilar.status).toBe(0);
      const despejo = spawnSync(
        "python3",
        ["-I", "-c", "import marshal,glob;f=open(glob.glob('__pycache__/*.pyc')[0],'rb');f.read(16);print(marshal.load(f).co_filename)"],
        { encoding: "utf8", timeout: 30000, cwd: pacote },
      );
      expect(despejo.status).toBe(0);
      const nome = despejo.stdout.trim();
      // compileall -p /nucleo grava o prefixo com o separador da plataforma:
      // barra normal no Linux, invertida no Windows. Aceita as duas formas.
      expect(nome.replace(/\\/g, "/").startsWith("/nucleo/")).toBe(true);
      expect(nome).not.toContain(raiz);
      expect(nome).not.toMatch(/^[A-Za-z]:/);
    } finally {
      rmSync(raiz, { recursive: true, force: true });
    }
  });
});
