# Grava um segredo em %LOCALAPPDATA%\rdl-vard\segredos.toml sem exibir o valor (o resto do arquivo fica).
# Uso: scripts\windows\gravar-segredo.ps1 -Secao coolify.exemplo -Chave token
#      scripts\windows\gravar-segredo.ps1 -Secao liv -Chave ssh_chave -Visivel     (valor que não é segredo, ex.: caminho)
param([Parameter(Mandatory)][string]$Secao, [Parameter(Mandatory)][string]$Chave, [switch]$Visivel)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts/windows -> raiz do repositório
if ($Secao -notmatch '^[a-z_]+(\.[a-z0-9_-]+)?$' -or $Chave -notmatch '^[a-z_]+$') { throw "Seção ou chave com caractere inválido." }
if ($Visivel) { $valor = Read-Host "Valor de $Secao.$Chave" }
else {
  $seguro = Read-Host "Valor de $Secao.$Chave (não aparece na tela)" -AsSecureString
  $valor = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
}
if (-not $valor) { throw "Valor vazio; nada gravado." }
$env:VARD_SEGREDO_VALOR = $valor     # o valor nunca vai na linha de comando
try {
  uv run --project (Join-Path $repo "nucleo") python -c "import os; from vard import segredos as s; s.gravar('$Secao', '$Chave', os.environ['VARD_SEGREDO_VALOR'])"
  if ($LASTEXITCODE -ne 0) { throw "Falhou ao gravar (código $LASTEXITCODE)" }
} finally { Remove-Item Env:VARD_SEGREDO_VALOR -ErrorAction SilentlyContinue }
Write-Host "Gravado $Secao.$Chave em segredos.toml (valor não exibido)."
