# Copia a config do Vard para o OpenJarvis, gera o mcp.json e importa segredos.
# Uso: scripts\windows\aplicar-config.ps1 [-Env X:\caminho\.env]
param([string]$Env = "")
$ErrorActionPreference = "Stop"
function Exigir($passo) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $passo (código $LASTEXITCODE)" } }
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts/windows -> raiz do repositório
$nucleo = Join-Path $repo "nucleo"   # projeto uv do núcleo

# Pastas do usuário, na mesma precedência de vard/config.py: VARD_CONFIG e VARD_DADOS,
# e na falta %LOCALAPPDATA%\rdl-vard (config\ e a raiz dos dados).
$pasta = $env:VARD_DADOS
if (-not $pasta) { $pasta = Join-Path $env:LOCALAPPDATA "rdl-vard" }
$config = $env:VARD_CONFIG
if (-not $config) { $config = Join-Path $pasta "config" }
$segredos = Join-Path $pasta "segredos.toml"
if ($env:VARD_CONFIG) { $segredos = Join-Path (Split-Path $config -Parent) "segredos.toml" }
New-Item -ItemType Directory -Force $pasta, $config | Out-Null

# 1. Importar do .env (VARD_OMNIROUTER_API, BOT_VARD_TELEGRAM) sem imprimir.
if ($Env -and (Test-Path $Env)) {
  $linhas = Get-Content $Env
  $omni = ($linhas | Where-Object { $_ -match '^VARD_OMNIROUTER_API=' } | Select-Object -First 1) -replace '^VARD_OMNIROUTER_API=', '' -replace '"', ''
  $tg   = ($linhas | Where-Object { $_ -match '^BOT_VARD_TELEGRAM=' } | Select-Object -First 1)   -replace '^BOT_VARD_TELEGRAM=', ''   -replace '"', ''
  if (-not $omni) { throw "VARD_OMNIROUTER_API ausente ou vazia em $Env" }
  if (-not $tg) { Write-Warning "BOT_VARD_TELEGRAM ausente em $Env (Telegram fica para o plano 2)." }
  $lm = ($linhas | Where-Object { $_ -match '^LM_STUDIO_LOCAL_API=' } | Select-Object -First 1) -replace '^LM_STUDIO_LOCAL_API=', '' -replace '"', ''
  if (-not $lm) { Write-Warning "LM_STUDIO_LOCAL_API ausente em $Env (chamadas ao LM Studio ficam sem token)." }
  # Chave a chave, preservando o resto ([coolify], [liv], [google], token do ai-memory, chat_id...).
  # O valor vai por variável de ambiente, nunca na linha de comando.
  function GravarSegredo($secao, $chave, $valor) {
    $env:VARD_SEGREDO_VALOR = $valor
    try {
      uv run --project $nucleo python -c "import os; from vard import segredos as s; s.gravar('$secao', '$chave', os.environ['VARD_SEGREDO_VALOR'])"
      Exigir "gravar $secao.$chave"
    } finally { Remove-Item Env:VARD_SEGREDO_VALOR -ErrorAction SilentlyContinue }
  }
  GravarSegredo "omniroute" "chave" $omni
  if ($lm) { GravarSegredo "lmstudio" "chave" $lm }
  if ($tg) { GravarSegredo "telegram" "token" $tg }
  $urlMem = (uv run --project $nucleo python -c "from vard import config as c, segredos as s; p = s.ARQUIVO or c.arquivo_segredos(); print(s.ai_memory()[0] if p.exists() else '')" | Out-String).Trim()
  if (-not $urlMem) { GravarSegredo "ai_memory" "url" "http://memoria.exemplo.com/mcp" }
  Write-Host "segredos.toml atualizado em $segredos (valores não exibidos; outras seções preservadas)."
}
if (-not (Test-Path $segredos)) { throw "Falta $segredos. Rode com -Env ou copie segredos.example.toml." }

# 2. Gerar mcp.json a partir dos segredos.
$mcp = Join-Path $pasta "mcp.json"
uv run --project $nucleo python -c "from pathlib import Path; from vard import segredos as s; s.escrever_mcp_json(s.carregar(), Path(r'$nucleo'), Path(r'$mcp'))"
Exigir "gerar mcp.json"

# 3. Copiar a config trocando o marcador pelo conteudo do mcp.json.
#    O OpenJarvis espera em tools.mcp.servers o JSON inline (uma string), nao um caminho.
#    Aspas simples = string literal do TOML, entao as barras invertidas passam sem escape.
#    OPENJARVIS_HOME (pasta de dados do OpenJarvis) foi definida por instalar-openjarvis.ps1.
$destino = [Environment]::GetEnvironmentVariable("OPENJARVIS_HOME", "User")
if (-not $destino) { throw "OPENJARVIS_HOME não definida: rode scripts\windows\instalar-openjarvis.ps1 antes." }
New-Item -ItemType Directory -Force $destino | Out-Null
$toml = Get-Content (Join-Path $config "openjarvis.toml") -Raw -Encoding UTF8
$json = ((Get-Content $mcp -Raw -Encoding UTF8) -replace '\s*[\r\n]+\s*', '').Trim()
if ($json.Contains("'")) { throw "JSON do MCP contém aspas simples; não cabe em string literal TOML" }
$toml = $toml.Replace('"__MCP_JSON__"', "'" + $json + "'")
# 3a. Persona: caminho absoluto de persona.md na pasta de configuração (barras normais, como nos outros marcadores).
$persona = Join-Path $config "persona.md"
if (-not (Test-Path $persona)) { throw "Falta $persona" }
$textoPersona = [IO.File]::ReadAllText($persona, [Text.Encoding]::UTF8)
if ($textoPersona.Contains("'''")) { throw "persona.md não pode conter ''' (string literal TOML)" }
$toml = $toml.Replace('__PERSONA_TEXTO__', $textoPersona)
if ($toml.Contains("__PERSONA_TEXTO__")) { throw "marcador __PERSONA_TEXTO__ não foi substituído" }
# 3b. Telegram: token e chat_id de segredos.toml. Sem chat_id, o canal fica DESLIGADO.
$tgTok  = uv run --project $nucleo python -c "from vard import segredos as s; print(s.chave_telegram())";  Exigir "ler token do Telegram"
$tgChat = uv run --project $nucleo python -c "from vard import segredos as s; print(s.chat_id_telegram())"; Exigir "ler chat_id do Telegram"
$toml = $toml.Replace("__TELEGRAM_TOKEN__", "$tgTok".Trim()).Replace("__TELEGRAM_CHAT__", "$tgChat".Trim())
# Falha fechado: sem o patch allowed_chat_ids no OpenJarvis instalado, o bot atenderia qualquer chat.
# O código fica em <openjarvis_src>/src/openjarvis/system (openjarvis_src = clone; instalacao.json; sem ele, ao lado de OPENJARVIS_HOME).
$srcOj = (uv run --project $nucleo python -c "from vard import instalacao; print(instalacao.ler().get('openjarvis_src', ''))" | Out-String).Trim(); Exigir "ler openjarvis_src"
if ($srcOj) { $kwargsOj = Join-Path $srcOj "src/openjarvis/system/_channel_kwargs.py" }
else { $kwargsOj = Join-Path (Split-Path $destino -Parent) "src/src/openjarvis/system/_channel_kwargs.py" }
$patchOk = (Test-Path $kwargsOj) -and (Get-Content $kwargsOj -Raw -Encoding UTF8).Contains('kw["allowed_chat_ids"]')
$motivo = ""
if (-not "$tgChat".Trim() -or -not "$tgTok".Trim()) { $motivo = "Telegram sem token ou sem chat_id. Mande /start ao bot e rode scripts\windows\telegram-chat-id.ps1." }
elseif (-not $patchOk) { $motivo = "o OpenJarvis instalado não repassa allowed_chat_ids ($kwargsOj sem o patch): o bot atenderia qualquer chat. Rode scripts\windows\instalar-openjarvis.ps1." }
if ($motivo) {
  Write-Warning "Canal do Telegram DESLIGADO: $motivo"
  # Troca so a 1a 'enabled = true' depois de [channel] (o [tools.mcp] fica intacto).
  $ic = $toml.IndexOf("[channel]")
  $ie = $toml.IndexOf("enabled = true", $ic)
  if ($ic -lt 0 -or $ie -lt 0) { throw "bloco [channel] sem 'enabled = true' em $config\openjarvis.toml" }
  $toml = $toml.Substring(0, $ie) + "enabled = false" + $toml.Substring($ie + "enabled = true".Length)
}
# 3c. Rotina da manhã: persona do digest e fontes de notícias (conector news_rss do OpenJarvis).
$personas = Join-Path $destino "prompts/personas"
New-Item -ItemType Directory -Force $personas | Out-Null
Copy-Item (Join-Path $config "persona-manha.md") (Join-Path $personas "vard.md") -Force
$conectores = Join-Path $destino "connectors"
New-Item -ItemType Directory -Force $conectores | Out-Null
uv run --project $nucleo python -c "from pathlib import Path; from vard import manha; manha.escrever_feeds(None, Path(r'$conectores/news_rss.json'))"
Exigir "gravar news_rss.json"
[IO.File]::WriteAllText((Join-Path $destino "config.toml"), $toml, (New-Object Text.UTF8Encoding $false))

# 4. Chave do OmniRouter como variável de usuário (o OpenJarvis lê VLLM_API_KEY).
$chave = uv run --project $nucleo python -c "from vard import segredos as s; print(s.chave_omniroute())"
Exigir "ler chave do OmniRouter"
$chave = "$chave".Trim()
if (-not $chave) { throw "Chave do OmniRouter vazia em segredos.toml" }
[Environment]::SetEnvironmentVariable("VLLM_API_KEY", $chave, "User")
# 4b. Token do LM Studio como variavel de usuario (o engine lmstudio do OpenJarvis le LMSTUDIO_API_KEY).
$chaveLm = uv run --project $nucleo python -c "from vard import segredos as s; print(s.chave_lmstudio())"
Exigir "ler chave do LM Studio"
$chaveLm = "$chaveLm".Trim()
if ($chaveLm) { [Environment]::SetEnvironmentVariable("LMSTUDIO_API_KEY", $chaveLm, "User") }
else { Write-Warning "Chave do LM Studio vazia em segredos.toml; LMSTUDIO_API_KEY não definida." }
# 4c. Cliente OAuth do Google para o `jarvis connect gmail` (o OpenJarvis lê OPENJARVIS_GOOGLE_CLIENT_ID/SECRET).
#     Depois do connect, o próprio OpenJarvis guarda o cliente em connectors e renova o token sozinho.
#     Sem client_id/secret é só aviso: a manhã sai com notícias e Liv (passo P3 do usuário).
$gId  = (uv run --project $nucleo python -c "from vard import segredos as s; print(s.google()[0])" | Out-String).Trim(); Exigir "ler google.client_id"
$gSec = (uv run --project $nucleo python -c "from vard import segredos as s; print(s.google()[1])" | Out-String).Trim(); Exigir "ler google.client_secret"
if ($gId -and $gSec) {
  [Environment]::SetEnvironmentVariable("OPENJARVIS_GOOGLE_CLIENT_ID", $gId, "User")
  [Environment]::SetEnvironmentVariable("OPENJARVIS_GOOGLE_CLIENT_SECRET", $gSec, "User")
} else { Write-Warning "Sem [google] client_id/client_secret: e-mail e agenda ficam fora da rotina da manhã (passo P3)." }
# 5. UTF-8 no stdio do MCP: o OpenJarvis abre a mesa com Popen(text=True) sem encoding (cp1252 neste PC) e
#    o SDK mcp escreve UTF-8; um título de janela com acento derrubava a leitura. Vale p/ terminais NOVOS.
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
# 6. Gemma sem raciocinio: o patch openjarvis-chat-extra junta isto ao corpo de todo /chat/completions
#    (reasoning_effort none corta ~3 s de "pensamento" por resposta). Vale p/ terminais NOVOS (jarvis ask).
[Environment]::SetEnvironmentVariable("OPENJARVIS_CHAT_EXTRA", '{"reasoning_effort":"none"}', "User")
Write-Host "Config aplicada em $destino\config.toml; VLLM_API_KEY, LMSTUDIO_API_KEY e PYTHONUTF8=1 e OPENJARVIS_CHAT_EXTRA definidas para o usuário (abra terminal novo antes do jarvis serve)."
