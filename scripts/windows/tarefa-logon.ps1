# Registra (ou remove) o início do Vard no logon (pasta Startup) e os atalhos da área de trabalho.
# Com supervisor ativo e vard.exe presente, os atalhos apontam direto para o exe (ciclo nativo).
# Sem supervisor, mantém o comportamento legado (PowerShell + vard-modo.ps1).
param([switch]$Remover)
$ErrorActionPreference = "Stop"
$Repo    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # scripts/windows -> raiz do repositório
$Script  = Join-Path $PSScriptRoot "vard-modo.ps1"
# VARD_PASTA_STARTUP / VARD_PASTA_DESKTOP desviam as pastas (testes usam pastas temporárias, nunca as reais).
$Startup = if ($env:VARD_PASTA_STARTUP) { $env:VARD_PASTA_STARTUP } else { [Environment]::GetFolderPath("Startup") }
$Desk    = if ($env:VARD_PASTA_DESKTOP) { $env:VARD_PASTA_DESKTOP } else { [Environment]::GetFolderPath("Desktop") }
$Atalhos = @{ (Join-Path $Startup "Vard.lnk") = "iniciar"; (Join-Path $Desk "Vard - Modo jogo.lnk") = "jogo"; (Join-Path $Desk "Vard - Voltar.lnk") = "voltar" }

if ($Remover) {
  foreach ($a in $Atalhos.Keys) { Remove-Item $a -Force -ErrorAction SilentlyContinue }
  Write-Host "Início no logon e atalhos removidos."; exit 0
}

# Detecta modo supervisor: instalacao.json com supervisor:true e vard.exe existente.
$Dados = if ($env:VARD_DADOS) { $env:VARD_DADOS } else { Join-Path $env:LOCALAPPDATA "rdl-vard" }
$InstArquivo = Join-Path $Dados "instalacao.json"
$Supervisor = $false
$HudExe = $null
if (Test-Path $InstArquivo) {
  try {
    $instCfg = Get-Content $InstArquivo -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($instCfg.supervisor -eq $true) {
      $candidato = if ($env:VARD_HUD_EXE) { $env:VARD_HUD_EXE } else { Join-Path $Repo "src-tauri\target\release\vard.exe" }
      if (-not (Test-Path $candidato)) { $candidato = Join-Path $Repo "vard.exe" }
      if (Test-Path $candidato) { $Supervisor = $true; $HudExe = $candidato }
    }
  } catch { }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($a in $Atalhos.Keys) {
  $lnk = $shell.CreateShortcut($a)
  if ($Supervisor) {
    # Modo supervisor: atalho aponta direto para vard.exe (single-instance garante unicidade).
    $lnk.TargetPath = $HudExe
    $lnk.Arguments = ""
    $lnk.WorkingDirectory = Split-Path $HudExe -Parent
    $lnk.IconLocation = "$HudExe,0"
  } else {
    # Modo legado: PowerShell + vard-modo.ps1 (comportamento atual preservado).
    $lnk.TargetPath = "powershell.exe"
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`" " + $Atalhos[$a]
    $lnk.WorkingDirectory = $Repo
    $lnk.IconLocation = "shell32.dll,137"
  }
  $lnk.Save()
}
if ($Supervisor) {
  Write-Host "Vard registrado no logon (supervisor: atalhos apontam para vard.exe)."
} else {
  Write-Host "Vard registrado no logon (pasta Startup) e atalhos criados na área de trabalho."
}
