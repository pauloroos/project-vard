# Monta build/nucleo/python: Python 3.13 standalone fixado + dependencias do lock + vard (T2 do plano 0.7).
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$build = Join-Path $raiz 'build'
$destino = Join-Path $build 'nucleo'
$py = Join-Path $destino 'python\python.exe'

function Executar([string]$que, [scriptblock]$bloco) {
    & $bloco
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $que (codigo $LASTEXITCODE)." }
}

# 1. runtime.toml
$toml = Get-Content -Raw -Encoding UTF8 (Join-Path $raiz 'nucleo\runtime.toml')
if ($toml -notmatch '(?m)^url = "(.+)"') { throw 'runtime.toml sem a linha url.' }
$url = $Matches[1]
if ($toml -notmatch '(?m)^sha256 = "([0-9a-f]{64})"') { throw 'runtime.toml sem sha256 valido (64 hex minusculos).' }
$esperado = $Matches[1]
if ($toml -notmatch '(?m)^versao = "(.+)"') { throw 'runtime.toml sem a linha versao.' }
$versaoPython = $Matches[1]

# 2. download e conferencia
if (-not ($url.StartsWith('https://github.com/') -or $url.StartsWith('https://objects.githubusercontent.com/'))) {
    throw "URL do runtime fora dos hosts permitidos: $url"
}
$cache = Join-Path $build 'cache'
New-Item -ItemType Directory -Force $cache | Out-Null
$arquivo = Join-Path $cache ([System.Uri]::UnescapeDataString(($url -split '/')[-1]))
if (-not (Test-Path $arquivo)) {
    Write-Host "Baixando $url"
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $url -OutFile $arquivo -UseBasicParsing
    } catch {
        if (Test-Path $arquivo) { Remove-Item -Force $arquivo -ErrorAction SilentlyContinue }
        throw "Falhou: baixar o Python embutido de $url ($($_.Exception.Message))."
    }
}
$obtido = (Get-FileHash -Algorithm SHA256 $arquivo).Hash.ToLower()
if ($obtido -ne $esperado) {
    Remove-Item -Force $arquivo
    throw "sha256 do Python embutido nao confere (esperado $esperado, obtido $obtido). Arquivo apagado do cache."
}

# 3. extracao
if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
New-Item -ItemType Directory -Force $destino | Out-Null
Executar 'extrair o Python' { & (Join-Path $env:SystemRoot 'System32\tar.exe') -xzf $arquivo -C $destino }
if (-not (Test-Path $py)) { throw "python.exe nao apareceu em $py depois de extrair." }

# 4. poda
$pythonDir = Join-Path $destino 'python'
foreach ($p in 'Lib\test', 'Lib\idlelib', 'Lib\tkinter', 'Lib\turtledemo', 'Lib\ensurepip', 'Lib\lib2to3', 'tcl') {
    $alvo = Join-Path $pythonDir $p
    try {
        if (Test-Path $alvo) { Remove-Item -Recurse -Force $alvo }
    } catch {
        throw "Falhou: podar $alvo ($($_.Exception.Message))."
    }
}
try {
    Get-ChildItem (Join-Path $pythonDir 'Lib\site-packages') -Filter 'pip*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
} catch {
    throw "Falhou: apagar o pip de site-packages ($($_.Exception.Message))."
}

# 5. dependencias do lock, com hashes
$requisitos = Join-Path $build 'requisitos.txt'
Executar 'uv export' { uv export --project (Join-Path $raiz 'nucleo') --frozen --no-dev --no-emit-project --format requirements-txt -o $requisitos }
Executar 'instalar as dependencias' { uv pip install --python $py --require-hashes -r $requisitos --no-cache --link-mode copy }

# 6. o proprio nucleo (wheel da T1)
Executar 'instalar o vard' { uv pip install --python $py --no-deps --no-cache (Join-Path $raiz 'nucleo') }

# 7. lancadores com caminho absoluto
$scripts = Join-Path $pythonDir 'Scripts'
try {
    if (Test-Path $scripts) { Remove-Item -Recurse -Force $scripts }
} catch {
    throw "Falhou: apagar $scripts ($($_.Exception.Message))."
}

# 8. pre-compilacao (a instalacao MSI fica em pasta so de leitura)
Executar 'compileall' { & $py -I -m compileall -q -j 0 (Join-Path $pythonDir 'Lib') }

# 9. teste rapido
$versaoNucleo = $null
if ((Get-Content -Raw -Encoding UTF8 (Join-Path $raiz 'nucleo\pyproject.toml')) -match '(?m)^version = "([^"]+)"') { $versaoNucleo = $Matches[1] }
if (-not $versaoNucleo) { throw 'pyproject.toml do nucleo sem version.' }
$saida = (& $py -I -X utf8 -m vard --versao | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "vard --versao falhou (codigo $LASTEXITCODE)." }
if ($saida -notmatch [regex]::Escape($versaoNucleo)) { throw "Versao do nucleo montado ('$saida') difere do pyproject ($versaoNucleo)." }
Executar 'importar as dependencias' { & $py -I -c 'import fastapi, uvicorn, httpx, psutil' }
Executar 'importar server e MCPs' { & $py -I -c 'import vard.server, vard.consulta_mcp, vard.memoria_mcp, vard.mesa_mcp, vard.oficina_mcp, vard.reuniao_mcp, vard.preflight' }

# 10. medidas
$base = (Resolve-Path $destino).Path.TrimEnd('\') + '\'
$itens = Get-ChildItem $destino -Recurse -Force
$arquivos = @($itens | Where-Object { -not $_.PSIsContainer })
$bytes = ($arquivos | Measure-Object -Property Length -Sum).Sum
$maior = ''
foreach ($i in $itens) {
    $rel = $i.FullName.Substring($base.Length)
    if ($rel.Length -gt $maior.Length) { $maior = $rel }
}
$medidas = [ordered]@{
    bytes_total = [int64]$bytes
    arquivos = $arquivos.Count
    maior_caminho = $maior
    maior_caminho_len = $maior.Length
    python = $versaoPython
    versao = $versaoNucleo
}
$json = $medidas | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $build 'nucleo-medidas.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host $json
if ($maior.Length -gt 160) { throw "Maior caminho do runtime tem $($maior.Length) caracteres (limite 160): $maior" }
Write-Host 'Runtime montado em build\nucleo.'