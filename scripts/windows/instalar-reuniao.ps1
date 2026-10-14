# Instala o modo reunião: dependências do serviço (reuniao/) e o download ÚNICO dos modelos de diarização do Hugging Face.
# Idempotente: roda de novo depois de aceitar as condições dos modelos. Depois disso o serviço roda 100% offline.
# O token vem de segredos.toml ([huggingface] token; grave com scripts\windows\gravar-segredo.ps1 -Secao huggingface -Chave token)
# e passa SÓ por $env:HF_TOKEN: nunca na linha de comando, em log, em arquivo ou na tela.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts/windows -> raiz do repositório
$local = $env:VARD_DADOS
if (-not $local) { $local = Join-Path $env:LOCALAPPDATA "rdl-vard" }
$estado = Join-Path $local "reuniao-modelos.json"
$hfHome = Join-Path $local "modelos\hf"
function Exigir($passo) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $passo (código $LASTEXITCODE)" } }

# Os três aceitos pelo usuário (o community-1 é o usado; o 3.1 é a reserva dele) e a reserva por embeddings (pública).
$modelos = @(
  @{ repo = "pyannote/speaker-diarization-community-1"; url = "https://huggingface.co/pyannote/speaker-diarization-community-1" },
  @{ repo = "pyannote/segmentation-3.0";                url = "https://huggingface.co/pyannote/segmentation-3.0" },
  @{ repo = "pyannote/speaker-diarization-3.1";         url = "https://huggingface.co/pyannote/speaker-diarization-3.1" }
)
$reserva = @{ repo = "pyannote/wespeaker-voxceleb-resnet34-LM"; url = "https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM" }

function GravarEstado([bool]$pronto, [string]$modo, [string]$motivo) {
  New-Item -ItemType Directory -Force (Split-Path $estado) | Out-Null
  $obj = [ordered]@{ pronto = $pronto; modo = $modo; motivo = $motivo; baixado_em = (Get-Date).ToString("s") }
  [IO.File]::WriteAllText($estado, ($obj | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
  Write-Host "Estado gravado em $estado (pronto=$pronto, modo=$modo)."
}

Write-Host "1/4 Dependências do serviço (uv sync --project reuniao)..."
uv sync --project (Join-Path $repo "reuniao")
Exigir "uv sync --project reuniao"

Write-Host "2/4 Token do Hugging Face (de segredos.toml; não é exibido)..."
$ErrorActionPreference = "Continue"      # o uv escreve avisos no stderr; o código de saída decide
$token = (uv run --project (Join-Path $repo "nucleo") python -c "from vard import segredos as s; print(s.huggingface())" 2>$null | Out-String).Trim()
$leu = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $leu -or -not $token) {
  GravarEstado $false "nenhum" "sem token: scripts\windows\gravar-segredo.ps1 -Secao huggingface -Chave token"
  Write-Host "Sem token do Hugging Face. Rode: scripts\windows\gravar-segredo.ps1 -Secao huggingface -Chave token  e depois este script de novo."
  exit 0
}

# Código Python do download (arquivo temporário SEM o token: ele só existe em os.environ do processo filho).
$py = @'
import os, sys
from huggingface_hub import snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError
repo = sys.argv[1]
try:
    snapshot_download(repo_id=repo, token=os.environ["HF_TOKEN"])
except GatedRepoError:
    sys.exit(3)
except HfHubHTTPError as e:
    status = getattr(getattr(e, "response", None), "status_code", None)
    print("HTTP", status, file=sys.stderr)
    sys.exit(3 if status in (401, 403) else 4)
except Exception as e:
    print(type(e).__name__, file=sys.stderr)
    sys.exit(4)
'@
$arqPy = Join-Path ([IO.Path]::GetTempPath()) ("baixar-modelo-" + [guid]::NewGuid().ToString("N") + ".py")
[IO.File]::WriteAllText($arqPy, $py, (New-Object Text.UTF8Encoding($false)))

$baixou = @{}
$recusados = New-Object System.Collections.Generic.List[string]
try {
  $env:HF_TOKEN = $token
  $env:HF_HOME = $hfHome
  $env:HF_HUB_DISABLE_TELEMETRY = "1"
  $env:PYANNOTE_METRICS_ENABLED = "0"             # forçado: a telemetria do pyannote não sai desta máquina
  $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"      # Windows sem modo desenvolvedor: o cache copia em vez de linkar (só avisa)
  $env:HF_HUB_DISABLE_PROGRESS_BARS = "1"
  Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue      # o download precisa de rede; o serviço roda offline
  New-Item -ItemType Directory -Force $hfHome | Out-Null
  Write-Host "3/4 Baixando os modelos para $hfHome ..."
  foreach ($m in ($modelos + $reserva)) {
    $ErrorActionPreference = "Continue"
    uv run --project (Join-Path $repo "reuniao") python $arqPy $m.repo
    $cod = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($cod -eq 0) { $baixou[$m.repo] = $true; Write-Host "  ok: $($m.repo)" }
    elseif ($cod -eq 3) {
      $recusados.Add($m.url)
      Write-Host "  Aceite as condições em $($m.url) e rode de novo"
    }
    else { Write-Host "  falhou: $($m.repo) (código $cod; rede ou outro erro)" }
  }

  $modo = "nenhum"; $motivo = ""
  if ($baixou[$modelos[0].repo]) { $modo = "community-1" }
  elseif ($baixou[$reserva.repo]) { $modo = "reserva"; $motivo = "só a reserva por embeddings (community-1 indisponível)" }
  else { $motivo = if ($recusados.Count -gt 0) { "condições não aceitas: " + ($recusados -join " ") } else { "download falhou (rede?); rode de novo" } }

  if ($modo -ne "nenhum") {
    Write-Host "4/4 Prova offline (HF_HUB_OFFLINE=1, carrega da pasta local)..."
    Remove-Item Env:HF_TOKEN -ErrorAction SilentlyContinue      # a prova não pode depender do token
    $env:HF_HUB_OFFLINE = "1"
    $env:PYANNOTE_METRICS_ENABLED = "0"
    $prova = if ($modo -eq "community-1") {
      "from pyannote.audio import Pipeline; p = Pipeline.from_pretrained('pyannote/speaker-diarization-community-1'); import sys; sys.exit(0 if p is not None else 1)"
    } else {
      "from pyannote.audio import Model; m = Model.from_pretrained('pyannote/wespeaker-voxceleb-resnet34-LM'); import sys; sys.exit(0 if m is not None else 1)"
    }
    $ErrorActionPreference = "Continue"
    uv run --project (Join-Path $repo "reuniao") python -c $prova 2>$null
    $okOffline = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if ($okOffline) { Write-Host "  prova offline: carregou ($modo)." }
    else { $motivo = "baixou, mas não carregou offline; rode de novo"; $modo = "nenhum"; Write-Host "  prova offline FALHOU." }
  }
  GravarEstado ($modo -ne "nenhum") $modo $motivo
}
finally {
  Remove-Item Env:HF_TOKEN -ErrorAction SilentlyContinue
  Remove-Item $arqPy -ErrorAction SilentlyContinue
}
