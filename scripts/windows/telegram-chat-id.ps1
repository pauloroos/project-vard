# Descobre o chat_id do usuário (depois de ele mandar /start ao bot) e grava em segredos.toml.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts/windows -> raiz do repositório
$tok = uv run --project (Join-Path $repo "nucleo") python -c "from vard import segredos as s; print(s.chave_telegram())"
if ($LASTEXITCODE -ne 0 -or -not "$tok".Trim()) { throw "token do Telegram ausente em segredos.toml" }
$r = Invoke-RestMethod -Uri ("https://api.telegram.org/bot" + "$tok".Trim() + "/getUpdates") -UseBasicParsing
$ids = @($r.result | ForEach-Object { $_.message.chat.id } | Where-Object { $_ } | Sort-Object -Unique)
if ($ids.Count -eq 0) { throw "nenhuma conversa ainda: abra o Telegram, procure o bot e mande /start" }
if ($ids.Count -gt 1) { throw "mais de um chat falou com o bot ($($ids -join ', ')): escolha e grave a mao em segredos.toml" }
$arquivo = Join-Path $env:TEMP "vard-chat.py"
$py = @"
import tomli_w
from vard import segredos as s
d = s.carregar()
d.setdefault("telegram", {})["chat_id"] = "$($ids[0])"
s.ARQUIVO.write_bytes(tomli_w.dumps(d).encode("utf-8"))
"@
Set-Content -Path $arquivo -Value $py -Encoding UTF8
try {
  uv run --project (Join-Path $repo "nucleo") python $arquivo
  if ($LASTEXITCODE -ne 0) { throw "falha ao gravar chat_id" }
} finally { Remove-Item $arquivo -ErrorAction SilentlyContinue }
Write-Host "chat_id gravado em segredos.toml (valor nao exibido). Rode scripts\windows\aplicar-config.ps1 e scripts\windows\vard-modo.ps1 recarregar."
