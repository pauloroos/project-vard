import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const powershell = ["pwsh", "powershell"].find(
  (comando) => spawnSync(comando, ["-NoProfile", "-Command", "exit 0"]).status === 0,
);

describe("medidor de RAM", () => {
  it.skipIf(!powershell)("executa o autoteste completo em PowerShell", () => {
    const resultado = spawnSync(powershell!, [
      "-NoProfile", "-File", "scripts/windows/medir-ram.ps1", "-AutoTeste",
    ], { encoding: "utf8" });

    expect(resultado.stderr).toBe("");
    expect(resultado.status).toBe(0);
    expect(resultado.stdout).toContain("Todos os testes passaram");
  }, 60_000);

  it.skipIf(!powershell)("atualiza a árvore e rejeita PID trocado depois do snapshot", () => {
    const pasta = mkdtempSync(join(tmpdir(), "vard-ram-"));
    try {
      const roteiro = join(pasta, "teste.ps1");
      const saida = join(pasta, "saida.json");
      writeFileSync(roteiro, `param($medidor, $saida)
$global:chamadas = 0
$global:inicio = [datetime]::Parse('2026-01-01T00:00:00Z').ToUniversalTime()
function Get-CimInstance {
  param($ClassName)
  $global:chamadas++
  if ($env:VARD_CASO) {
    $raizData = if ($env:VARD_CASO -in @('raiz_sem_data', 'raizes_sobrepostas')) { $null } else { $inicio }
    $paiData = if ($env:VARD_CASO -eq 'pai_sem_data') { $null } elseif ($env:VARD_CASO -eq 'pai_data_invalida') { 'invalida' } else { $inicio.AddSeconds(10) }
    $filhoData = if ($env:VARD_CASO -eq 'filho_antigo') { $inicio.AddSeconds(5) } else { $inicio.AddSeconds(20) }
    [pscustomobject]@{ ProcessId=100; ParentProcessId=1; Name='vard.exe'; CommandLine='vard.exe'; CreationDate=$raizData }
    [pscustomobject]@{ ProcessId=200; ParentProcessId=100; Name='python.exe'; CommandLine='worker'; CreationDate=$paiData }
    [pscustomobject]@{ ProcessId=300; ParentProcessId=200; Name='python.exe'; CommandLine='worker'; CreationDate=$filhoData }
    return
  }
  $inicioRaiz = if ($env:VARD_TESTE_RAIZ -and $global:chamadas -ge 2) { $inicio.AddMinutes(1) } else { $inicio }
  [pscustomobject]@{ ProcessId=100; ParentProcessId=1; Name='vard.exe'; CommandLine='vard.exe'; CreationDate=$inicioRaiz }
  if ($env:VARD_TESTE_FILHO) {
    $inicioFilho = if ($global:chamadas -ge 2) { $inicio.AddMinutes(1) } else { $inicio }
    [pscustomobject]@{ ProcessId=200; ParentProcessId=100; Name='python.exe'; CommandLine='worker'; CreationDate=$inicioFilho }
    return
  }
  if ($global:chamadas -ge 2) {
    [pscustomobject]@{ ProcessId=200; ParentProcessId=100; Name='python.exe'; CommandLine='worker'; CreationDate=$inicio }
    [pscustomobject]@{ ProcessId=300; ParentProcessId=100; Name='python.exe'; CommandLine='worker'; CreationDate=$inicio }
  }
}
function Get-Process {
  param($Id, $ErrorAction)
  if ($env:VARD_CASO) {
    $data = if ($Id -eq 100) { $inicio } elseif ($Id -eq 200) { $inicio.AddSeconds(10) } else { if ($env:VARD_CASO -eq 'filho_antigo') { $inicio.AddSeconds(5) } else { $inicio.AddSeconds(20) } }
    if ($env:VARD_CASO -eq 'pai_reutilizado_rapido' -and $Id -eq 200) { $data = $data.AddTicks(10) }
    if (($env:VARD_CASO -eq 'pai_sem_start' -and $Id -eq 200) -or ($env:VARD_CASO -eq 'raiz_sem_start' -and $Id -eq 100)) { $data = $null }
    [pscustomobject]@{ StartTime=$data; WorkingSet64=1048576; PrivateMemorySize64=1048576 }
    return
  }
  $data = if ($Id -eq 300 -or ($env:VARD_TESTE_FILHO -and $Id -eq 200 -and $global:chamadas -ge 2) -or ($env:VARD_TESTE_CORRIDA -and $Id -eq 100 -and $global:chamadas -ge 2)) { $inicio.AddMinutes(1) } else { $inicio }
  [pscustomobject]@{ StartTime=$data; WorkingSet64=1048576; PrivateMemorySize64=1048576 }
}
$raizes = if ($env:VARD_CASO -eq 'raizes_sobrepostas') { @(200, 100) } else { @(100) }
if ($env:VARD_SEM_JSON) {
  & $medidor -PidsRaiz $raizes -Estado repouso -Amostras 2 -IntervaloSeg 0
} else {
  & $medidor -PidsRaiz $raizes -Estado repouso -Amostras 2 -IntervaloSeg 0 -SaidaJson $saida
}
`);
      const resultado = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], { encoding: "utf8" });
      expect(resultado.stderr).toBe("");
      expect(resultado.status).toBe(0);
      const dados = JSON.parse(readFileSync(saida, "utf8").replace(/^\uFEFF/, ""));
      expect(dados.amostras[0].total.processos).toBe(1);
      expect(dados.amostras[1].total.processos).toBe(2);
      expect(dados.amostras[1].arvores[0].processos.find((p: { pid: number }) => p.pid === 300).encerrado).toBe(true);
      const raizTrocada = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
        encoding: "utf8", env: { ...process.env, VARD_TESTE_RAIZ: "1" },
      });
      expect(raizTrocada.stderr).toBe("");
      expect(raizTrocada.status).toBe(0);
      const dadosRaiz = JSON.parse(readFileSync(saida, "utf8").replace(/^\uFEFF/, ""));
      expect(dadosRaiz.amostras[1].total.processos).toBe(0);
      const filhoTrocado = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
        encoding: "utf8", env: { ...process.env, VARD_TESTE_FILHO: "1" },
      });
      expect(filhoTrocado.stderr).toBe("");
      expect(filhoTrocado.status).toBe(0);
      const dadosFilho = JSON.parse(readFileSync(saida, "utf8").replace(/^\uFEFF/, ""));
      expect(dadosFilho.amostras[0].total.processos).toBe(2);
      expect(dadosFilho.amostras[1].total.processos).toBe(1);
      const corrida = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
        encoding: "utf8", env: { ...process.env, VARD_TESTE_CORRIDA: "1" },
      });
      expect(corrida.stderr).toBe("");
      expect(corrida.status).toBe(0);
      const dadosCorrida = JSON.parse(readFileSync(saida, "utf8").replace(/^\uFEFF/, ""));
      expect(dadosCorrida.amostras[1].total.processos).toBe(0);
      for (const [caso, total] of [
        ["pai_sem_data", 1], ["pai_data_invalida", 1], ["pai_sem_start", 1], ["pai_reutilizado_rapido", 1],
        ["filho_antigo", 2], ["raiz_sem_data", 0], ["raiz_sem_start", 0], ["raizes_sobrepostas", 0],
      ] as const) {
        const execucao = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
          encoding: "utf8", env: { ...process.env, VARD_CASO: caso },
        });
        expect(execucao.stderr, caso).toBe("");
        expect(execucao.status, caso).toBe(0);
        const dadosCaso = JSON.parse(readFileSync(saida, "utf8").replace(/^\uFEFF/, ""));
        expect(dadosCaso.amostras[0].total.processos, caso).toBe(total);
        if (caso.startsWith("pai_")) {
          const processos = dadosCaso.amostras[0].arvores[0].processos;
          expect(processos.find((p: { pid: number }) => p.pid === 200).nao_verificavel, caso).toBe(true);
          expect(processos.find((p: { pid: number }) => p.pid === 300).nao_verificavel, caso).toBe(true);
        }
        if (caso.startsWith("raiz")) {
          expect(dadosCaso.amostras[0].raizes_nao_verificaveis, caso).toContain(100);
        }
        if (caso === "filho_antigo") {
          expect(dadosCaso.amostras[0].arvores[0].processos.map((p: { pid: number }) => p.pid)).not.toContain(300);
        }
      }
      const consoleIncompleto = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
        encoding: "utf8", env: { ...process.env, VARD_CASO: "raiz_sem_data", VARD_SEM_JSON: "1" },
      });
      expect(consoleIncompleto.stderr).toBe("");
      expect(consoleIncompleto.status).toBe(0);
      expect(consoleIncompleto.stdout).toMatch(/aviso.*incomplet/i);
      expect(consoleIncompleto.stdout).toMatch(/raiz/i);
      const consoleCompleto = spawnSync(powershell!, ["-NoProfile", "-File", roteiro, resolve("scripts/windows/medir-ram.ps1"), saida], {
        encoding: "utf8", env: { ...process.env, VARD_CASO: "normal", VARD_SEM_JSON: "1" },
      });
      expect(consoleCompleto.stderr).toBe("");
      expect(consoleCompleto.status).toBe(0);
      expect(consoleCompleto.stdout).not.toMatch(/aviso.*incomplet/i);
    } finally {
      rmSync(pasta, { recursive: true, force: true });
    }
  }, 60_000);
});
