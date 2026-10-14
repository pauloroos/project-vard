# Troca da instalação do Vard para este repositório, com retorno em um passo.
# Uso: trocar-instalacao.ps1 -Candidato | -Promover | -Reverter | -Status [-Raiz <pasta>] [-Antigo <vard-modo.ps1 antigo>]
#   -Candidato: backup + gera a config do OpenJarvis para esta raiz + recarrega OpenJarvis e ponte por ela, SEM trocar a
#               instalação ativa (usa um instalacao.json temporário). Rode o preflight depois. Nada de jogo/parar.
#   -Promover:  só depois do preflight verde: grava instalacao.json (atômico) e aponta logon e atalhos para este script.
#   -Reverter:  restaura config do OpenJarvis, variáveis, atalhos e instalacao.json do backup e recarrega pelo script antigo.
# Não mexe em tarefas, atas nem schemas de dados. Código e venvs antigos ficam intactos.
param([switch]$Candidato, [switch]$Promover, [switch]$Reverter, [switch]$Status, [string]$Raiz = "", [string]$Antigo = "")
$ErrorActionPreference = "Stop"
$Raiz = if ($Raiz) { $Raiz } else { Split-Path (Split-Path $PSScriptRoot -Parent) -Parent }
$Pasta = Join-Path $env:LOCALAPPDATA "rdl-vard"
$Fusao = Join-Path $Pasta "fusao"
$Promocao = Join-Path $Fusao "promocao.json"
$InstAtiva = Join-Path $Pasta "instalacao.json"
$InstCand = Join-Path $Fusao "instalacao-candidata.json"
$Startup = [Environment]::GetFolderPath("Startup"); $Desk = [Environment]::GetFolderPath("Desktop")
$Atalhos = @((Join-Path $Startup "Vard.lnk"), (Join-Path $Desk "Vard - Modo jogo.lnk"), (Join-Path $Desk "Vard - Voltar.lnk"))
$Variaveis = "VLLM_API_KEY", "LMSTUDIO_API_KEY", "PYTHONUTF8", "OPENJARVIS_CHAT_EXTRA", "OPENJARVIS_GOOGLE_CLIENT_ID", "OPENJARVIS_GOOGLE_CLIENT_SECRET", "OPENJARVIS_HOME"
function Gravar-Atomico($caminho, $texto) {
  New-Item -ItemType Directory -Force (Split-Path $caminho -Parent) | Out-Null
  $tmp = "$caminho.tmp"; [IO.File]::WriteAllText($tmp, $texto, (New-Object Text.UTF8Encoding $false)); Move-Item -Force $tmp $caminho
}
function Ler-Json($caminho) { if (Test-Path $caminho) { Get-Content $caminho -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null } }
function Script-Antigo() {
  if ($Antigo) { return $Antigo }
  $lnk = $Atalhos[0]
  if (Test-Path $lnk) {
    $a = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).Arguments
    if ($a -match '-File "([^"]+)"') { return $Matches[1] }
  }
  throw "Não achei o vard-modo.ps1 em uso (atalho de logon); passe -Antigo."
}
function Pasta-OpenJarvis() { [Environment]::GetEnvironmentVariable("OPENJARVIS_HOME", "User") }
function Fazer-Backup() {
  $dir = Join-Path $Fusao ("backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
  New-Item -ItemType Directory -Force $dir | Out-Null
  $oj = Pasta-OpenJarvis
  foreach ($f in @((Join-Path $oj "config.toml"), (Join-Path $Pasta "mcp.json"), (Join-Path $Pasta "segredos.toml"), $InstAtiva, (Join-Path $Pasta "estado.json"))) {
    if (Test-Path $f) { Copy-Item $f (Join-Path $dir (Split-Path $f -Leaf)) -Force }
  }
  foreach ($l in $Atalhos) { if (Test-Path $l) { Copy-Item $l (Join-Path $dir (Split-Path $l -Leaf)) -Force } }
  $vars = @{}; foreach ($n in $Variaveis) { $vars[$n] = [Environment]::GetEnvironmentVariable($n, "User") }
  Gravar-Atomico (Join-Path $dir "variaveis.json") ($vars | ConvertTo-Json)
  return $dir
}
function Restaurar-Backup($dir) {
  $oj = Pasta-OpenJarvis
  if (Test-Path (Join-Path $dir "config.toml")) { Copy-Item (Join-Path $dir "config.toml") (Join-Path $oj "config.toml") -Force }
  if (Test-Path (Join-Path $dir "segredos.toml")) { Copy-Item (Join-Path $dir "segredos.toml") (Join-Path $Pasta "segredos.toml") -Force }
  if (Test-Path (Join-Path $dir "mcp.json")) { Copy-Item (Join-Path $dir "mcp.json") (Join-Path $Pasta "mcp.json") -Force }
  if (Test-Path (Join-Path $dir "instalacao.json")) { Copy-Item (Join-Path $dir "instalacao.json") $InstAtiva -Force } else { Remove-Item $InstAtiva -Force -ErrorAction SilentlyContinue }
  foreach ($l in $Atalhos) { $b = Join-Path $dir (Split-Path $l -Leaf); if (Test-Path $b) { Copy-Item $b $l -Force } else { Remove-Item $l -Force -ErrorAction SilentlyContinue } }
  $vars = Ler-Json (Join-Path $dir "variaveis.json")
  foreach ($n in $Variaveis) { [Environment]::SetEnvironmentVariable($n, $vars.$n, "User") }
}
function Instalacao-Candidata() {
  $base = Ler-Json $InstAtiva
  $o = [ordered]@{ raiz_codigo = $Raiz; openjarvis_src = ""; openjarvis_home = (Pasta-OpenJarvis); modelo = ""; contexto = 0; servicos = @{} }
  if ($base) { foreach ($p in $base.PSObject.Properties) { $o[$p.Name] = $p.Value }; $o["raiz_codigo"] = $Raiz }
  return $o
}
function Exigir-Ambiente() {
  if (-not (Test-Path (Join-Path $Raiz "nucleo\.venv\Scripts\python.exe"))) { throw "Falta o ambiente do núcleo: rode 'uv sync --project nucleo' em $Raiz." }
  if (-not (Pasta-OpenJarvis)) { throw "OPENJARVIS_HOME não definida." }
}

if ($Status) {
  [ordered]@{ raiz = $Raiz; promovida = (Test-Path $Promocao); instalacao = (Test-Path $InstAtiva); candidata = (Test-Path $InstCand) } | ConvertTo-Json -Compress
  exit 0
}
if ($Candidato) {
  Exigir-Ambiente
  $antigo = Script-Antigo
  $dir = Fazer-Backup
  Gravar-Atomico $Promocao (([ordered]@{ antigo = $antigo; raiz_nova = $Raiz; backup = $dir; promovida = $false; desde = (Get-Date).ToString("s") }) | ConvertTo-Json)
  Gravar-Atomico $InstCand ((Instalacao-Candidata) | ConvertTo-Json -Depth 5)
  $env:VARD_CONFIG = Join-Path $Pasta "config"; $env:VARD_DADOS = $Pasta; $env:VARD_INSTALACAO = $InstCand
  & (Join-Path $PSScriptRoot "aplicar-config.ps1")
  if ($LASTEXITCODE -ne 0) { Write-Error "aplicar-config falhou; rode -Reverter"; exit 1 }
  & (Join-Path $PSScriptRoot "vard-modo.ps1") recarregar -Instalacao $InstCand
  Write-Host "Candidato no ar. Backup em $dir. Rode o preflight; se verde, -Promover; senão, -Reverter."
  exit 0
}
if ($Promover) {
  $p = Ler-Json $Promocao
  if (-not $p -or -not (Test-Path $InstCand)) { throw "Rode -Candidato antes (e o preflight)." }
  Copy-Item $InstCand "$InstAtiva.tmp" -Force; Move-Item -Force "$InstAtiva.tmp" $InstAtiva
  & (Join-Path $PSScriptRoot "tarefa-logon.ps1")
  $p.promovida = $true; Gravar-Atomico $Promocao ($p | ConvertTo-Json)
  Write-Host "Promovida: instalacao.json gravado e logon/atalhos apontam para $Raiz. Retorno: trocar-instalacao.ps1 -Reverter."
  exit 0
}
if ($Reverter) {
  $p = Ler-Json $Promocao
  if (-not $p) { throw "Nada a reverter (sem promocao.json)." }
  Restaurar-Backup $p.backup
  Remove-Item $InstCand -Force -ErrorAction SilentlyContinue
  & $p.antigo recarregar
  $p.promovida = $false; $p | Add-Member -NotePropertyName revertida -NotePropertyValue (Get-Date).ToString("s") -Force
  Gravar-Atomico $Promocao ($p | ConvertTo-Json)
  Write-Host "Revertido: config, variáveis, atalhos e instalacao.json do backup; OpenJarvis e ponte recarregados pelo script antigo."
  exit 0
}
throw "Use -Candidato, -Promover, -Reverter ou -Status."
