# Gera dois-falantes.wav (16 kHz mono, ~40 s) e dois-falantes.json (referência t0/t1/falante) com o Kokoro do OpenJarvis.
# Uso: powershell -NoProfile -File reuniao\tests\fixtures\gerar_dois_falantes.ps1   (OpenJarvis em 127.0.0.1:8000 e ffmpeg no PATH)
# Falante 1 = pm_alex (voz masculina), falante 2 = pf_dora (voz feminina).
param([string]$Openjarvis = "http://127.0.0.1:8000")
$ErrorActionPreference = "Stop"
$aqui = $PSScriptRoot
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("dois-falantes-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null
function Exigir($passo) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $passo (codigo $LASTEXITCODE)" } }
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = Join-Path (Split-Path $ffmpeg) "ffprobe.exe"

$frases = @(
  @(1, "Bom dia a todos, vamos começar a reunião de hoje falando sobre o orçamento do próximo trimestre."),
  @(2, "Bom dia. Eu revisei os números ontem e o custo com infraestrutura subiu mais do que o esperado."),
  @(1, "Entendi. Você acha que dá para reduzir esse custo sem atrasar a entrega do novo painel de controle?"),
  @(2, "Acho que sim, se a gente migrar os servidores mais antigos até o fim do mês e desligar os que sobraram."),
  @(1, "Perfeito. Então fica combinado que você prepara a proposta de migração e me envia até sexta-feira."),
  @(2, "Combinado. Envio a proposta com os prazos e os riscos, e a gente decide juntos na próxima reunião.")
)
$vozes = @{ 1 = "pm_alex"; 2 = "pf_dora" }

# 0,8 s de silêncio a 24 kHz mono, igual ao formato do Kokoro.
$silencio = Join-Path $tmp "silencio.wav"
& $ffmpeg -v error -y -f lavfi -i "anullsrc=r=24000:cl=mono" -t 0.8 -c:a pcm_s16le $silencio
Exigir "silêncio"

$lista = New-Object System.Collections.Generic.List[string]
$ref = New-Object System.Collections.Generic.List[object]
$t = 0.0
for ($i = 0; $i -lt $frases.Count; $i++) {
  $falante = [int]$frases[$i][0]
  $corpo = @{ text = [string]$frases[$i][1]; voice_id = $vozes[$falante] } | ConvertTo-Json -Compress
  $arq = Join-Path $tmp ("f{0}.wav" -f $i)
  Invoke-WebRequest -Uri "$Openjarvis/v1/speech/synthesize" -Method Post -ContentType "application/json; charset=utf-8" `
    -Body ([Text.Encoding]::UTF8.GetBytes($corpo)) -OutFile $arq -UseBasicParsing
  $dur = [double]::Parse((& $ffprobe -v error -show_entries format=duration -of "default=nw=1:nk=1" $arq), [Globalization.CultureInfo]::InvariantCulture)
  Exigir "ffprobe da frase $i"
  $ref.Add([ordered]@{ t0 = [math]::Round($t, 2); t1 = [math]::Round($t + $dur, 2); falante = $falante })
  $t += $dur + 0.8
  $lista.Add("file '" + ($arq -replace "\\", "/") + "'")
  if ($i -lt $frases.Count - 1) { $lista.Add("file '" + ($silencio -replace "\\", "/") + "'") }
}
$txtLista = Join-Path $tmp "lista.txt"
[IO.File]::WriteAllLines($txtLista, $lista, (New-Object Text.UTF8Encoding($false)))
$saida = Join-Path $aqui "dois-falantes.wav"
$args24 = @("-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", $txtLista, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", $saida)
& $ffmpeg @args24
Exigir "concatenar e reamostrar"
$json = ConvertTo-Json -InputObject $ref.ToArray() -Depth 3
[IO.File]::WriteAllText((Join-Path $aqui "dois-falantes.json"), $json, (New-Object Text.UTF8Encoding($false)))
Remove-Item -Recurse -Force $tmp
Write-Host ("Gerado {0} ({1:N1} s de fala + silêncios)" -f $saida, $t)
