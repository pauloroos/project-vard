# Registra (ou remove) o início do Vard no logon (pasta Startup) e os atalhos da área de trabalho.
param([switch]$Remover)
$ErrorActionPreference = "Stop"
$Repo    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # scripts/windows -> raiz do repositório
$Script  = Join-Path $PSScriptRoot "vard-modo.ps1"
$Startup = [Environment]::GetFolderPath("Startup")
$Desk    = [Environment]::GetFolderPath("Desktop")
$Atalhos = @{ (Join-Path $Startup "Vard.lnk") = "iniciar"; (Join-Path $Desk "Vard - Modo jogo.lnk") = "jogo"; (Join-Path $Desk "Vard - Voltar.lnk") = "voltar" }

if ($Remover) {
  foreach ($a in $Atalhos.Keys) { Remove-Item $a -Force -ErrorAction SilentlyContinue }
  Write-Host "Início no logon e atalhos removidos."; exit 0
}
$shell = New-Object -ComObject WScript.Shell
foreach ($a in $Atalhos.Keys) {
  $lnk = $shell.CreateShortcut($a)
  $lnk.TargetPath = "powershell.exe"
  $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`" " + $Atalhos[$a]
  $lnk.WorkingDirectory = $Repo
  $lnk.IconLocation = "shell32.dll,137"
  $lnk.Save()
}
Write-Host "Vard registrado no logon (pasta Startup) e atalhos criados na área de trabalho."
