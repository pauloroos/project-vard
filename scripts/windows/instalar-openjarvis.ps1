# Instala o OpenJarvis nativo no Windows, com Python 3.13 via uv.
# Idempotente: roda de novo para atualizar.
# Pastas: -Src/-Home na linha de comando ou, na falta, instalacao.json da máquina.
param(
  [switch]$Atualizar,
  [string]$Src = "",
  [Alias("Home")][string]$HomeDir = ""   # $HOME é somente leitura no PowerShell: -Home entra pelo alias
)
$ErrorActionPreference = "Stop"
$OjCommit = "ccf02ec7bdda2e2b344eeb8dd986d742ff458acc"  # commit do OpenJarvis testado com o Vard
function Exigir($passo) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $passo (código $LASTEXITCODE)" } }
# Patches ficam ao lado dos scripts, sempre relativos a este arquivo.
$DirPatches = "$PSScriptRoot/../openjarvis/patches"
$Patch = Join-Path $DirPatches "openjarvis-telegram-allowed-chat-ids.patch"
$PatchMarca = Join-Path $DirPatches "openjarvis-telegram-marca.patch"
$PatchExtra = Join-Path $DirPatches "openjarvis-chat-extra.patch"   # OPENJARVIS_CHAT_EXTRA: reasoning_effort none no corpo do chat
$PatchBrowser = Join-Path $DirPatches "openjarvis-open-browser.patch"   # open_browser no Windows: cmd /c start cortava a URL no primeiro & (OAuth do Google abria sem redirect_uri)

# Patch local: o OpenJarvis ignora allowed_chat_ids do Telegram (o bot atenderia qualquer chat).
# Se o upstream já trouxer a correção, pula. Se o patch não aplicar na versão nova (-Atualizar),
# volta o clone para o commit fixado, reaplica lá e para com erro: nunca fica sem pin e sem patch.
function AplicarPatch($src, $patch, $fixado, $atualizando, $rel = "src/openjarvis/system/_channel_kwargs.py", $marca = 'kw["allowed_chat_ids"]', $nome = "allowed_chat_ids") {
  $arquivo = Join-Path $src $rel
  if ((Get-Content $arquivo -Raw -Encoding UTF8).Contains($marca)) {
    Write-Host "$nome já vem no OpenJarvis (upstream absorveu): patch pulado."
    return "pulado"
  }
  $ErrorActionPreference = "Continue"   # git escreve o motivo no stderr; o código de saída decide
  git -C $src apply --check $patch
  $cabe = ($LASTEXITCODE -eq 0)
  $ErrorActionPreference = "Stop"
  if ($cabe) {
    git -C $src apply $patch
    Exigir "patch $nome"
    return "aplicado"
  }
  if (-not $atualizando) { throw "O patch $nome não aplica no commit fixado $fixado (clone mexido à mão?)." }
  git -C $src checkout -f --detach $fixado
  Exigir "voltar ao commit fixado"
  git -C $src apply $patch
  Exigir "reaplicar o patch no commit fixado"
  throw "O patch $nome não aplica na versão nova do OpenJarvis. O clone VOLTOU para $fixado com o patch; nada foi atualizado. Ajuste scripts/openjarvis/patches antes de tentar -Atualizar de novo."
}
# Pastas do OpenJarvis: -Src/-Home vence; sem eles, o instalacao.json da máquina
# (VARD_INSTALACAO, depois VARD_DADOS, por fim %LOCALAPPDATA%\rdl-vard\instalacao.json).
function LerInstalacao() {
  $arq = $env:VARD_INSTALACAO
  if (-not $arq) {
    $base = $env:VARD_DADOS
    if (-not $base) { $base = Join-Path $env:LOCALAPPDATA "rdl-vard" }
    $arq = Join-Path $base "instalacao.json"
  }
  if (-not (Test-Path $arq)) { return $null }
  try { return Get-Content $arq -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}
$inst = LerInstalacao
if (-not $Src) { $Src = ("{0}" -f $inst.openjarvis_src).Trim() }
if (-not $HomeDir) { $HomeDir = ("{0}" -f $inst.openjarvis_home).Trim() }
if (-not $Src -or -not $HomeDir) {
  throw "Falta a pasta do OpenJarvis: passe -Src e -Home ou grave instalacao.json (openjarvis_src e openjarvis_home)."
}
$src = $Src          # clone do OpenJarvis: código em src\openjarvis\...
$dados = $HomeDir    # pasta da instalação; os dados ficam fora do código (exigência do OpenJarvis)
New-Item -ItemType Directory -Force $src, $dados | Out-Null
[Environment]::SetEnvironmentVariable("OPENJARVIS_HOME", $dados, "User")
$env:OPENJARVIS_HOME = $dados

# Versao fixada: o OpenJarvis muda rapido e o Vard depende de detalhes dele (patch, rotas, config).
# Por isso o instalador trava o clone em $OjCommit. Para subir de versao: -Atualizar, rodar o preflight,
# e so se tudo ficar verde gravar o novo SHA aqui.
if (-not (Test-Path (Join-Path $src ".git"))) {
  git clone https://github.com/open-jarvis/OpenJarvis.git $src
  Exigir "git clone"
  git -C $src checkout --detach $OjCommit
  Exigir "git checkout do commit fixado"
} else {
  # Arvore limpa; o patch do Vard e reaplicado logo depois.
  git -C $src checkout -- src/openjarvis/system/_channel_kwargs.py src/openjarvis/engine/_openai_compat.py src/openjarvis/core/utils.py src/openjarvis/channels/telegram.py
  Exigir "git checkout do arquivo com patch"
  if ($Atualizar) {
    git -C $src fetch origin
    Exigir "git fetch"
    git -C $src remote set-head origin --auto   # origin/HEAD = branch padrão do upstream (não supor 'main')
    Exigir "git remote set-head"
    git -C $src checkout --detach origin/HEAD
    Exigir "git checkout origin/HEAD"
  } else {
    git -C $src fetch --quiet origin
    Exigir "git fetch"
    git -C $src checkout --detach $OjCommit
    Exigir "git checkout do commit fixado"
  }
}
[void](AplicarPatch $src $Patch $OjCommit $Atualizar.IsPresent)
[void](AplicarPatch $src $PatchMarca $OjCommit $Atualizar.IsPresent "src/openjarvis/channels/telegram.py" "VARD_MARCA_TELEGRAM" "telegram-marca")
[void](AplicarPatch $src $PatchExtra $OjCommit $Atualizar.IsPresent "src/openjarvis/engine/_openai_compat.py" "_chat_extra()" "chat-extra")
[void](AplicarPatch $src $PatchBrowser $OjCommit $Atualizar.IsPresent "src/openjarvis/core/utils.py" "os.startfile(url)" "open-browser")
if ($Atualizar) {
  $novo = git -C $src rev-parse HEAD
  Write-Host "OpenJarvis agora em $novo. Rode o preflight; se tudo verde, grave esse SHA em `$OjCommit."
}

Push-Location $src
try {
  uv python install 3.13
  Exigir "uv python install 3.13"
  # server: FastAPI/uvicorn do jarvis serve. browser: Playwright. channel-telegram: plano 2. desktop+voice: fala (whisper, Kokoro).
  uv sync --python 3.13 --extra server --extra browser --extra channel-telegram --extra desktop --extra voice
  Exigir "uv sync"
  # Whisper na GPU sem instalar o CUDA toolkit: as DLLs vêm em wheels. O uv sync pode removê-las, por isso reinstala sempre.
  uv pip install "nvidia-cublas-cu12" "nvidia-cudnn-cu12"
  Exigir "cuda wheels"
  uv run playwright install chromium
  Exigir "playwright install chromium"
  uv run jarvis --version
  Exigir "jarvis --version"
} finally {
  Pop-Location
}
