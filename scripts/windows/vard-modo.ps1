# Ciclo de vida do Vard. Fonte de verdade: tudo que liga ou desliga passa por aqui.
# Uso: vard-modo.ps1 iniciar | jogo | voltar | parar | recarregar | status | aba | sonda [-Corrigir]
# A ponte e a bandeja disparam este script por um intermediário (vard\modo.py): ele não é
# descendente delas, e o taskkill /T que ele dá nelas não o alcança. Mesmo assim, por defesa,
# estado e log são gravados ANTES de matar a ponte (jogo) e a bandeja (parar).
param([Parameter(Position = 0)][string]$Verbo = "", [switch]$Corrigir, [string]$Instalacao = "")
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------- caminhos
# Instalação da máquina: instalacao.json (-Instalacao, VARD_INSTALACAO ou %LOCALAPPDATA%\rdl-vard\instalacao.json).
# Campos: raiz_codigo, openjarvis_src, modelo, contexto, servicos.{voz_python,reuniao_python}. Sem arquivo, valem os padrões.
$Pasta     = Join-Path $env:LOCALAPPDATA "rdl-vard"
$ArqInst   = if ($Instalacao) { $Instalacao } elseif ($env:VARD_INSTALACAO) { $env:VARD_INSTALACAO } else { Join-Path $Pasta "instalacao.json" }
$Inst      = $null
if (Test-Path $ArqInst) { try { $Inst = Get-Content $ArqInst -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw "instalacao.json ilegível: $ArqInst" } }
function Cfg($valor, $padrao) { if ($valor) { return $valor } else { return $padrao } }
$Repo      = Cfg $Inst.raiz_codigo (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)   # padrão: raiz do repositório deste script
$OjSrc     = Cfg $Inst.openjarvis_src ""
$Chrome    = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$Pids      = Join-Path $Pasta "pids"
$Logs      = Join-Path $Pasta "logs"
$Estado    = Join-Path $Pasta "estado.json"
$Modelo    = Cfg $Inst.modelo "gemma-4-12b-it-qat@q4_k_xl"
$Contexto  = [int](Cfg $Inst.contexto 16384)   # o JIT do LM Studio recarrega com o contexto padrão (128k Gemma, 262k ornith) e a geração cai de ~110 para ~10 tok/s
# Dois formatos de raiz: o novo (nucleo\server.py, scripts\windows\bandeja.py) e o antigo (server.py na raiz, deploy\bandeja.py).
$Novo      = Test-Path (Join-Path $Repo "nucleo\server.py")
$Nucleo    = if ($Novo) { Join-Path $Repo "nucleo" } else { $Repo }
$Bandeja   = if ($Novo) { Join-Path $Repo "scripts\windows\bandeja.py" } else { Join-Path $Repo "deploy\bandeja.py" }
$VozDir    = Join-Path $Repo "voz"
$VozExe    = Cfg $Inst.servicos.voz_python (Join-Path $VozDir ".venv\Scripts\python.exe")
$ReuniaoDir = Join-Path $Repo "reuniao"
$ReuniaoExe = Cfg $Inst.servicos.reuniao_python (Join-Path $ReuniaoDir ".venv\Scripts\python.exe")
if ($Novo) {   # o código novo lê config e dados por estas variáveis (o antigo as ignora)
  $env:VARD_CONFIG = Join-Path $Pasta "config"; $env:VARD_DADOS = $Pasta
  if (Test-Path $ArqInst) { $env:VARD_INSTALACAO = $ArqInst }
}
$ArgsGui   = "run --no-sync jarvis gui --no-server --no-browser --api-port 8000 --frontend-port 5173"
New-Item -ItemType Directory -Force $Pids, $Logs | Out-Null

# ---------------------------------------------------------------- utilidades
function Log($msg) {
  $linha = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $msg
  Add-Content -Path (Join-Path $Logs "vard-modo.log") -Value $linha -Encoding UTF8
  Write-Host $linha
}
# Falhar: o ciclo quebrou no meio (iniciar, voltar, recarregar). Grava modo "erro" com o detalhe:
# a bandeja fica vermelha e avisa. Recusar: pedido inválido; o estado atual fica como está.
function Falhar($msg) {
  Log "ERRO: $msg"
  try { GravarEstado "erro" $msg } catch {}
  [Console]::Error.WriteLine($msg); exit 1
}
function Recusar($msg) { Log "RECUSADO: $msg"; [Console]::Error.WriteLine($msg); exit 1 }
function Exigir($passo) { if ($LASTEXITCODE -ne 0) { Falhar "Falhou: $passo (código $LASTEXITCODE)" } }

# Variáveis de usuário: tarefa agendada e shells filhos não as herdam. Copiar sempre.
$Vars = @{}
# As 4 primeiras são obrigatórias; VARD_HUD_EXE (caminho do vard.exe) é opcional e tem padrão abaixo.
$Obrigatorias = "OPENJARVIS_HOME", "VLLM_API_KEY", "LMSTUDIO_API_KEY", "PYTHONUTF8"
foreach ($n in ($Obrigatorias + "VARD_HUD_EXE" + "OPENJARVIS_CHAT_EXTRA")) {
  $v = [Environment]::GetEnvironmentVariable($n, "User")
  if ($v) { $Vars[$n] = $v; Set-Item -Path "Env:$n" -Value $v }
}
# Gemma sem raciocínio (patch openjarvis-chat-extra): opcional; sem a variável de usuário, vale o padrão.
if (-not $Vars["OPENJARVIS_CHAT_EXTRA"]) { $Vars["OPENJARVIS_CHAT_EXTRA"] = '{"reasoning_effort":"none"}'; $env:OPENJARVIS_CHAT_EXTRA = $Vars["OPENJARVIS_CHAT_EXTRA"] }
$Vars["VARD_MARCA_TELEGRAM"] = Join-Path $Pasta "ultimo-telegram.json"
$env:VARD_MARCA_TELEGRAM = $Vars["VARD_MARCA_TELEGRAM"]
$VariaveisOk = (($Obrigatorias | Where-Object { -not $Vars[$_] }).Count -eq 0)
$Hud = if ($Vars["VARD_HUD_EXE"]) { $Vars["VARD_HUD_EXE"] } else { Join-Path $env:LOCALAPPDATA "Vard\vard.exe" }

# Quem responde e a opção extra pertencem ao HUD, nunca ao instalacao.json.
# O núcleo repassa VARD_HUD_CONFIG_DIR com o app_config_dir do build (inclui dev).
function DeveSubirOpenJarvis() {
  if (-not $Inst -or -not $Inst.servicos.openjarvis) { return $false }
  $pastaHud = if ($env:VARD_HUD_CONFIG_DIR) { $env:VARD_HUD_CONFIG_DIR } else { Join-Path $env:APPDATA "io.github.pauloroos.vard" }
  $hudArq = Join-Path $pastaHud "hud.config.json"
  $hudConfig = $null
  if (Test-Path -LiteralPath $hudArq) {
    try { $hudConfig = Get-Content -LiteralPath $hudArq -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
  }
  # Mesmo padrão histórico de src/config/cerebro.ts para arquivo/campo ausente.
  $cerebro = if ($hudConfig.cerebro -is [string]) { $hudConfig.cerebro } else { "openjarvis" }
  return ($cerebro -ceq "openjarvis" -or ($hudConfig.usar_openjarvis -is [bool] -and $hudConfig.usar_openjarvis))
}
function GravarEstado($modo, $detalhe) {
  $obj = @{ modo = $modo; desde = (Get-Date).ToString("s"); detalhe = $detalhe }
  [IO.File]::WriteAllText($Estado, ($obj | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
}
function LerPid($nome) {
  $f = Join-Path $Pids "$nome.pid"
  if (-not (Test-Path $f)) { return $null }
  # Formato "pid|hora de início". Só número (formato antigo) ou hora diferente = obsoleto (PID reaproveitado).
  $partes = (Get-Content $f -Raw).Trim().Split("|")
  if ($partes.Count -eq 2) {
    $proc = Get-Process -Id ([int]$partes[0]) -ErrorAction SilentlyContinue
    if ($proc) {
      try {
        $gravada = [DateTime]::Parse($partes[1], $null, [Globalization.DateTimeStyles]::RoundtripKind)
        if ([Math]::Abs(($proc.StartTime - $gravada).TotalSeconds) -le 5) { return [int]$partes[0] }
      } catch {}
    }
  }
  Remove-Item $f -Force; return $null
}
function Matar($nome) {
  $p = LerPid $nome
  if ($p) { Log "parando $nome (pid $p)"; try { & taskkill.exe /PID $p /T /F 2>&1 | Out-Null } catch {} }   # árvore inteira: uv é só o lançador, o filho segura a porta
  Remove-Item (Join-Path $Pids "$nome.pid") -Force -ErrorAction SilentlyContinue
}
function Subir($nome, $exe, $argumentos, $dir) {
  if (LerPid $nome) { Log "$nome já está no ar"; return }
  if ($nome -eq "openjarvis") {
    # Whisper na GPU: o ctranslate2 acha as DLLs do CUDA (wheels nvidia-cublas/cudnn do venv) pelo PATH.
    $venv = Join-Path $OjSrc ".venv"
    foreach ($sub in "cublas", "cudnn") {
      $bin = Join-Path $venv ("Lib/site-packages/nvidia/" + $sub + "/bin")
      if (Test-Path $bin) { $env:PATH = "$bin;$env:PATH" }
    }
  }
  $out = Join-Path $Logs "$nome.log"
  # O frontend da gui declara npm <12 com engine-strict; este PC tem npm 12. A variável vale só para o filho gui:
  # entra no ambiente antes do Start-Process e sai logo depois (a ponte e os demais não a herdam).
  if ($nome -eq "gui") { $env:npm_config_engine_strict = "false" }
  try {
    $p = Start-Process -FilePath $exe -ArgumentList $argumentos -WorkingDirectory $dir -WindowStyle Hidden `
         -RedirectStandardOutput $out -RedirectStandardError ($out + ".err") -PassThru
  } finally {
    if ($nome -eq "gui") { Remove-Item Env:npm_config_engine_strict -ErrorAction SilentlyContinue }
  }
  try { $conteudo = "$($p.Id)|$($p.StartTime.ToString('o'))" }
  catch { $conteudo = "$($p.Id)"; $cedo = $true }   # só o pid: LerPid trata como obsoleto
  Set-Content -Path (Join-Path $Pids "$nome.pid") -Value $conteudo -Encoding ascii
  if ($cedo) { Log "processo $nome saiu cedo"; return }
  Log "$nome subiu (pid $($p.Id))"
}
# Estado do vard-voz (4710): "ligado" (pronta), "aquecendo" (responde, modelo ainda carregando), "desligado".
function EstadoVoz() {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:4710/saude" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ((ConvertFrom-Json $r.Content).pronta) { return "ligado" } else { return "aquecendo" }
  } catch { return "desligado" }
}
# Voz subida à mão: registra o dono da porta 4710 em voz.pid para o jogo/parar conseguirem matá-la.
function AdotarVoz() {
  if (LerPid "voz") { return }
  $c = Get-NetTCPConnection -LocalPort 4710 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $c) { return }
  $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
  if ($proc) { Set-Content -Path (Join-Path $Pids "voz.pid") -Value "$($proc.Id)|$($proc.StartTime.ToString('o'))" -Encoding ascii; Log "voz adotada (pid $($proc.Id))" }
}
# Estado do vard-reuniao (4720): "ativa" (reunião em andamento), "ligado", "desligado".
function EstadoReuniao() {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:4720/status" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ((ConvertFrom-Json $r.Content).ativa) { return "ativa" } else { return "ligado" }
  } catch { return "desligado" }
}
# Reunião subida à mão: registra o dono da porta 4720 em reuniao.pid para o jogo/parar conseguirem matá-la.
function AdotarReuniao() {
  if (LerPid "reuniao") { return }
  $c = Get-NetTCPConnection -LocalPort 4720 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $c) { return }
  $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
  if ($proc) { Set-Content -Path (Join-Path $Pids "reuniao.pid") -Value "$($proc.Id)|$($proc.StartTime.ToString('o'))" -Encoding ascii; Log "reunião adotada (pid $($proc.Id))" }
}
# Modo jogo: encerra a reunião ANTES de liberar a GPU (nada se perde). Espera a fila esvaziar (até 35 s).
function EncerrarReuniao() {
  if ((EstadoReuniao) -ne "ativa") { return }
  Log "reunião em andamento: encerrando antes do modo jogo"
  try { Invoke-WebRequest -Uri "http://127.0.0.1:4720/encerrar" -Method Post -UseBasicParsing -TimeoutSec 40 -ErrorAction Stop | Out-Null } catch { Log "AVISO: /encerrar: $($_.Exception.Message)" }
  $fim = (Get-Date).AddSeconds(35)
  while ((Get-Date) -lt $fim -and (EstadoReuniao) -eq "ativa") { Start-Sleep -Milliseconds 500 }
}
function Esperar($url, $segundos, $cabecalho = $null) {
  $fim = (Get-Date).AddSeconds($segundos)
  while ((Get-Date) -lt $fim) {
    try {
      $r = Invoke-WebRequest -Uri $url -Headers $cabecalho -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
      if ($r.StatusCode -eq 200) { return $true }
    } catch {}
    Start-Sleep -Milliseconds 800
  }
  return $false
}
# lms escreve progresso no stderr; com ErrorActionPreference=Stop o PS 5.1 trata isso como erro.
function InvocarLms {
  $ErrorActionPreference = "Continue"
  & lms @args 2>&1 | Out-Null
}
function LmHeaders() { if ($Vars["LMSTUDIO_API_KEY"]) { @{ Authorization = "Bearer " + $Vars["LMSTUDIO_API_KEY"] } } else { $null } }
function ModelosCarregados() {
  try { ($(lms ps --json 2>$null | ConvertFrom-Json) | Measure-Object).Count } catch { 0 }
}
# Só lê (lms ps --json). "ok", "ausente", "contexto N (esperado X)" ou "extra <id>"; $null se o lms não respondeu.
function DiagnosticoModelo() {
  try { $lista = @($(lms ps --json 2>$null | ConvertFrom-Json)) } catch { return $null }
  $lista = @($lista | Where-Object { $_ })
  $extra = $lista | Where-Object { $_.modelKey -ne $Modelo -and $_.identifier -ne $Modelo } | Select-Object -First 1
  if ($extra) { return "extra $(if ($extra.identifier) { $extra.identifier } else { $extra.modelKey })" }
  $meu = $lista | Where-Object { $_.modelKey -eq $Modelo -or $_.identifier -eq $Modelo } | Select-Object -First 1
  if (-not $meu) { return "ausente" }
  if ([int]$meu.contextLength -ne $Contexto) { return "contexto $($meu.contextLength) (esperado $Contexto)" }
  return "ok"
}
# Garante UM modelo só, o esperado, com contexto fixo; senão descarrega tudo e recarrega.
function GarantirModelo() {
  $d = DiagnosticoModelo
  if ($d -eq "ok") { Log "modelo: ok ($Modelo, contexto $Contexto)"; return }
  Log "modelo: $(if ($null -eq $d) { 'lms ps não respondeu' } else { $d }); recarregando $Modelo com contexto $Contexto"
  InvocarLms unload --all
  # 2 atendimentos (a Vard quase nunca usa mais) e sem modelo auxiliar de decodificação especulativa: o MTP
  # salvo nas configurações do LM Studio falhou ao carregar em 13/10 ("invalid vector subscript") e deixou a Vard sem cérebro.
  InvocarLms load $Modelo --gpu max --context-length $Contexto --parallel 2 --no-speculative-draft-mtp
  Exigir "lms load"
}

# A janela --app pertence ao processo principal do Chrome (a linha de comando dele não traz --app):
# detectar pelo título da janela (EnumWindows), classe Chrome_WidgetWin_1, título "Vard".
Add-Type -Namespace Vard -Name Jan -MemberDefinition @'
public delegate bool Cb(System.IntPtr h, System.IntPtr l);
[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern bool EnumWindows(Cb f, System.IntPtr l);
[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern bool IsWindowVisible(System.IntPtr h);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)] public static extern int GetWindowText(System.IntPtr h, System.Text.StringBuilder t, int n);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)] public static extern int GetWindowThreadProcessId(System.IntPtr h, out int pid);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)] public static extern int GetClassName(System.IntPtr h, System.Text.StringBuilder t, int n);
'@
function JanelaVardAberta() {
  $achou = New-Object System.Collections.ArrayList
  $cb = [Vard.Jan+Cb]{ param($h, $l)
    if ([Vard.Jan]::IsWindowVisible($h)) {
      $t = New-Object System.Text.StringBuilder 256; $c = New-Object System.Text.StringBuilder 256
      [void][Vard.Jan]::GetWindowText($h, $t, 256); [void][Vard.Jan]::GetClassName($h, $c, 256)
      if ($c.ToString() -eq "Chrome_WidgetWin_1" -and $t.ToString() -match "^Vard( - .*)?$") {
        $dono = 0; [void][Vard.Jan]::GetWindowThreadProcessId($h, [ref]$dono)
        $proc = Get-Process -Id $dono -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "chrome") { [void]$achou.Add($h) }
      }
    }
    return $true }
  [void][Vard.Jan]::EnumWindows($cb, [IntPtr]::Zero)
  return ($achou.Count -gt 0)
}

# ---------------------------------------------------------------- adaptador supervisor
# Com supervisor ativo e app novo vivo, publica o verbo na caixa IPC em vez de executar
# diretamente. O Rust consome o pedido e executa pelo ciclo nativo. Sem supervisor ou sem
# app vivo, devolve $false e o script segue o caminho legado (comportamento atual).
function PublicarNaCaixa($verbo) {
  if (-not $Inst -or -not $Inst.supervisor) { return $false }
  $appJson = Join-Path $Pasta "ciclo\app.json"
  if (-not (Test-Path $appJson)) { return $false }
  try {
    $app = Get-Content $appJson -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch { return $false }
  if (-not $app.sessao_id) { return $false }
  $pedidosDir = Join-Path $Pasta "ciclo\pedidos"
  New-Item -ItemType Directory -Force $pedidosDir | Out-Null
  $id = [guid]::NewGuid().ToString()
  $conteudo = @{ id = $id; verbo = $verbo; sessao = $app.sessao_id } | ConvertTo-Json -Compress
  $tmp = Join-Path $pedidosDir "$id.tmp"
  $alvo = Join-Path $pedidosDir "$id.json"
  [IO.File]::WriteAllText($tmp, $conteudo, (New-Object Text.UTF8Encoding $false))
  Rename-Item -Path $tmp -NewName "$id.json" -Force
  Log "adaptador: publicado '$verbo' na caixa IPC ($id)"
  return $true
}

# ---------------------------------------------------------------- verbos
function ModoAtual() {
  if (Test-Path $Estado) { try { return (Get-Content $Estado -Raw -Encoding UTF8 | ConvertFrom-Json).modo } catch {} }
  return "desconhecido"
}
function AbrirAba() {
  if (Test-Path $Hud) {
    # HUD instalado: abre ele no lugar do Chrome. Uma instância só; o modo jogo não o fecha (fica cinza e mudo).
    if (Get-Process -Name "vard" -ErrorAction SilentlyContinue) { Log "HUD já aberto"; return }
    Start-Process -FilePath $Hud -WorkingDirectory (Split-Path $Hud) | Out-Null
    Log "HUD aberto ($Hud)"
    return
  }
  Log "AVISO: HUD não encontrado em $Hud; abrindo a aba no Chrome"
  if (JanelaVardAberta) { Log "janela do Vard já aberta"; return }
  if (-not (Test-Path $Chrome)) { Log "AVISO: Chrome não encontrado em $Chrome"; return }
  Start-Process $Chrome "--app=http://127.0.0.1:4700 --window-size=720,900" -RedirectStandardOutput (Join-Path $env:TEMP 'vard-chrome.out') -RedirectStandardError (Join-Path $env:TEMP 'vard-chrome.err') | Out-Null
  Log "janela do Vard aberta"
}
function Iniciar() {
  GravarEstado "ligando" "subindo serviços"
  # Bandeja primeiro: se algo abaixo falhar (logon sem LM Studio, variável faltando), o erro aparece nela.
  Subir "bandeja" "uv" "run --no-sync python `"$Bandeja`"" $Nucleo
  if (-not $VariaveisOk) {
    $faltam = ($Obrigatorias | Where-Object { -not $Vars[$_] }) -join ", "
    Falhar "faltam variáveis de usuário (rode scripts\windows\aplicar-config.ps1): $faltam"
  }
  InvocarLms server start
  # Contexto de 16k: com 256k o cache enche a GPU e o modelo cai para ~10 tok/s (achado de 12/10).
  GarantirModelo
  if (-not (Esperar "http://127.0.0.1:1234/v1/models" 60 (LmHeaders))) { Falhar "LM Studio não respondeu" }
  if (DeveSubirOpenJarvis) {
    if (-not $OjSrc) { Falhar "instalacao.json sem openjarvis_src (veja config\examples\instalacao.example.json)" }
    Subir "openjarvis" "uv" "run --no-sync jarvis serve --agent orchestrator" $OjSrc
    if (-not (Esperar "http://127.0.0.1:8000/health" 120)) { Falhar "OpenJarvis não respondeu em 120 s (ver logs\openjarvis.log.err)" }
  } else {
    Log "OpenJarvis desligado (cerebro proprio sem toggle usar_openjarvis)"
  }
  Subir "ponte" "uv" "run --no-sync uvicorn server:app --host 127.0.0.1 --port 4700 --timeout-graceful-shutdown 2" $Nucleo
  if (-not (Esperar "http://127.0.0.1:4700/status" 30)) { Falhar "ponte não respondeu" }
  # Voz (XTTS, Suad): não é crítica. Só precisa responder HTTP (o modelo pode ainda estar carregando);
  # se falhar, o HUD cai no Kokoro. Se já há uma no ar (subida à mão), adota em vez de subir outra.
  if ((EstadoVoz) -ne "desligado") { Log "voz já no ar"; AdotarVoz }
  elseif (-not (Test-Path $VozExe)) { Log "AVISO: voz não instalada ($VozExe); HUD usa Kokoro" }
  else {
    $env:PYTHONUTF8 = "1"
    Subir "voz" $VozExe "-m vard_voz" $VozDir
    if (-not (Esperar "http://127.0.0.1:4710/saude" 60)) { Log "AVISO: voz (4710) não respondeu em 60 s (ver logs\voz.log.err); HUD usa Kokoro" }
  }
  # Modo reunião (4720): não é crítico; sem ele só as ferramentas reuniao_* respondem "não está instalado".
  if ((EstadoReuniao) -ne "desligado") { Log "reunião já no ar"; AdotarReuniao }
  elseif (-not (Test-Path $ReuniaoExe)) { Log "AVISO: modo reunião não instalado ($ReuniaoExe)" }
  else {
    $env:PYTHONUTF8 = "1"
    Subir "reuniao" $ReuniaoExe "-m vard_reuniao" $ReuniaoDir
    if (-not (Esperar "http://127.0.0.1:4720/status" 60)) { Log "AVISO: reunião (4720) não respondeu em 60 s (ver logs\reuniao.log.err)" }
  }
  # Interface de texto do OpenJarvis (botão Texto do HUD). Só sobe quando o OpenJarvis está ativo.
  if (DeveSubirOpenJarvis) {
    Subir "gui" "uv" $ArgsGui $OjSrc
    if (-not (Esperar "http://127.0.0.1:5173/" 90)) { Log "AVISO: interface de texto (5173) não respondeu em 90 s (ver logs\gui.log.err)" }
  } else {
    Log "GUI desligada (OpenJarvis não ativo)"
  }
  AbrirAba
  GravarEstado "ligado" "LM Studio, OpenJarvis, ponte, voz e bandeja no ar"
  Log "Vard ligado"
}
function Jogo() {
  GravarEstado "jogo" "liberando GPU"
  EncerrarReuniao   # antes de tudo: a ata e a diarização precisam da GPU
  InvocarLms unload --all   # primeiro a GPU
  if ($LASTEXITCODE -ne 0) { Log "AVISO: lms unload --all retornou $LASTEXITCODE" }
  # A escolha pode ter mudado desde o arranque: encerra também os processos já ativos.
  Matar "openjarvis"
  Matar "gui"
  AdotarVoz     # uma subida à mão também precisa cair
  Matar "voz"   # libera a VRAM da voz
  AdotarReuniao
  Matar "reuniao"
  # Estado e log antes de matar a ponte: se este script fosse descendente dela, o taskkill /T o levaria junto.
  GravarEstado "jogo" "GPU livre; OpenJarvis e ponte parados; bandeja apagada"
  Log "modo jogo"
  Matar "ponte"
}
function Parar() {
  Jogo
  InvocarLms server stop
  GravarEstado "parado" "tudo desligado"
  Log "Vard parado"
  Matar "bandeja"   # por último: a bandeja pode ter disparado este script
}
function Recarregar() {
  $atual = ModoAtual
  if ($atual -ne "ligado") { Recusar "recarregar só com o Vard ligado (modo atual: $atual)" }
  # Recarregar derruba o OpenJarvis (whisper) por 15 s a 2 min: no meio de uma reunião isso perde a transcrição.
  if ((EstadoReuniao) -eq "ativa") { Recusar "encerre a reunião antes de recarregar (o OpenJarvis cai e a transcrição do trecho se perde)" }
  Matar "openjarvis"
  if (DeveSubirOpenJarvis) {
    # O long-poll do Telegram do processo antigo ainda vale por alguns segundos: subir já devolve 409 e o canal
    # fica em erro. Pausa de 15 s entre parar e subir.
    Start-Sleep -Seconds 15
    Subir "openjarvis" "uv" "run --no-sync jarvis serve --agent orchestrator" $OjSrc
    if (-not (Esperar "http://127.0.0.1:8000/health" 120)) { Falhar "OpenJarvis não voltou" }
  } else {
    Matar "gui"
    Log "Recarregar: OpenJarvis desligado pela configuração"
  }
  # A ponte também reinicia, para carregar rotas novas (este script é órfão da ponte, ver o topo).
  Matar "ponte"
  Start-Sleep -Seconds 2
  Subir "ponte" "uv" "run --no-sync uvicorn server:app --host 127.0.0.1 --port 4700 --timeout-graceful-shutdown 2" $Nucleo
  if (-not (Esperar "http://127.0.0.1:4700/status" 30)) { Falhar "ponte não voltou" }
  GravarEstado "ligado" "OpenJarvis e ponte recarregados"
}
function Status() {
  $obj = [ordered]@{
    modo = (ModoAtual); openjarvis = (LerPid "openjarvis"); gui = $(if (LerPid "gui") { "ligado" } else { "desligado" }); ponte = (LerPid "ponte"); voz = (EstadoVoz); reuniao = (EstadoReuniao); bandeja = (LerPid "bandeja")
    lmstudio_modelos = (ModelosCarregados); modelo = (DiagnosticoModelo); variaveis_ok = $VariaveisOk; layout = $(if ($Novo) { "novo" } else { "antigo" })
  }
  Write-Output ($obj | ConvertTo-Json -Compress)
}
# Sonda do preflight: prova que um disparo pela ponte/bandeja roda o script de verdade. Só reporta o modelo;
# recarrega apenas com -Corrigir (e só se o Vard estiver ligado).
function Sonda() {
  $d = DiagnosticoModelo
  Log "modelo: $(if ($null -eq $d) { 'lms ps não respondeu' } else { $d })"
  if ($Corrigir -and $d -ne "ok" -and $null -ne $d) { GarantirModelo }
  $agora = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  Set-Content -Path (Join-Path $Pasta "sonda.txt") -Value $agora -Encoding ascii
  Log "sonda gravada (voz: $(EstadoVoz))"
}

# Adaptador: com supervisor ativo e app vivo, publica na caixa IPC e sai.
# Sem supervisor ou sem app vivo, segue o caminho legado (comportamento atual).
if (PublicarNaCaixa $Verbo) { exit 0 }

switch ($Verbo) {
  "iniciar"    { Iniciar }
  "voltar"     { Iniciar }
  "jogo"       { Jogo }
  "parar"      { Parar }
  "recarregar" { Recarregar }
  "status"     { Status }
  "aba"        { AbrirAba }
  "sonda"      { Sonda }
  default      { Recusar "verbo inválido: '$Verbo' (use iniciar|jogo|voltar|parar|recarregar|status|aba|sonda)" }
}
exit 0
