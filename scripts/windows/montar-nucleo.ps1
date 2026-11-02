# Monta build/nucleo/python: Python 3.13 standalone fixado + dependencias do lock + vard (T2 do plano 0.7).
param(
    [string]$Toml,
    [string]$Destino,
    [string]$Cache,
    [switch]$SoVerificar
)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Padroes dos parametros opcionais
if (-not $Toml) { $Toml = Join-Path $raiz 'nucleo\runtime.toml' }
$buildPadrao = Join-Path $raiz 'build'
if (-not $Cache) { $Cache = Join-Path $buildPadrao 'cache' }
if (-not $Destino) { $Destino = Join-Path $buildPadrao 'nucleo' }

function Executar([string]$que, [scriptblock]$bloco) {
    & $bloco
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $que (codigo $LASTEXITCODE)." }
}

function Resolver-Caminho-Seguro([string]$alvo, [string]$descricao) {
    # Resolve caminho absoluto e valida que esta dentro de build/nucleo ou build/cache.
    try {
        $abs = [System.IO.Path]::GetFullPath($alvo)
    } catch {
        throw "Caminho invalido para $descricao`: $alvo"
    }
    $raizBuild = [System.IO.Path]::GetFullPath((Join-Path $raiz 'build'))
    $permitidos = @(
        (Join-Path $raizBuild 'nucleo'),
        (Join-Path $raizBuild 'cache')
    )
    $ok = $false
    foreach ($p in $permitidos) {
        $pNorm = $p.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if ($abs.StartsWith($pNorm, [System.StringComparison]::OrdinalIgnoreCase) -or $abs -eq $p.TrimEnd([System.IO.Path]::DirectorySeparatorChar)) {
            $ok = $true
            break
        }
    }
    if (-not $ok) {
        throw "Caminho recusado para $descricao`: $abs (deve estar dentro de $raizBuild\nucleo ou $raizBuild\cache)."
    }
    $atual = $abs
    while ($atual) {
        $item = Get-Item -LiteralPath $atual -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Link ou reparse point recusado em $descricao."
        }
        if ($atual -eq $raizBuild) { break }
        $atual = [System.IO.Path]::GetDirectoryName($atual)
    }
    return $abs
}

function Validar-Segredos-No-Destino([string]$dest) {
    $proibidos = @('segredos.toml', 'perfil.json', 'hud.config.json', 'paineis.json')
    $encontrados = @()
    foreach ($nome in $proibidos) {
        $hits = Get-ChildItem -Path $dest -Recurse -Force -Filter $nome -ErrorAction SilentlyContinue
        if ($hits) { $encontrados += $hits.FullName }
    }
    # persona*.md
    $personaHits = Get-ChildItem -Path $dest -Recurse -Force -Filter 'persona*.md' -ErrorAction SilentlyContinue
    if ($personaHits) { $encontrados += $personaHits.FullName }
    # *.env
    $envHits = Get-ChildItem -Path $dest -Recurse -Force -Filter '*.env' -ErrorAction SilentlyContinue
    if ($envHits) { $encontrados += $envHits.FullName }
    if ($encontrados.Count -gt 0) {
        $lista = $encontrados -join ', '
        throw "Arquivos proibidos encontrados no destino apos montagem: $lista"
    }
}

function Validar-Caminhos-No-Destino([string]$dest) {
    # PEP 610: uv pip install do diretorio local grava site-packages/*.dist-info/direct_url.json
    # com file:/// + caminho absoluto da maquina. Nenhum pode entrar no instalador.
    $restos = @(Get-ChildItem -Path $dest -Recurse -Force -Filter 'direct_url.json' -ErrorAction SilentlyContinue)
    if ($restos.Count -gt 0) {
        $lista = ($restos | ForEach-Object { $_.FullName }) -join ', '
        throw "Metadata com caminho da maquina no destino: $lista (direct_url.json com file:/// local; remova apos uv pip install)."
    }
    $pacotes = Join-Path $dest 'python\Lib\site-packages'
    if (-not (Test-Path -LiteralPath $pacotes)) { return }
    $alvos = @(Get-ChildItem -Path $pacotes -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @('.pth', '.cfg', '.ini', '.json', '.toml', '.txt') -or
        $_.FullName -match '\.(dist-info|egg-info)[\\/]'
    })
    foreach ($f in $alvos) {
        $texto = $null
        try {
            $texto = Get-Content -Raw -LiteralPath $f.FullName -Encoding UTF8 -ErrorAction Stop
        } catch {
            continue
        }
        if ($null -eq $texto) { continue }
        # .pth (sys.path) e RECORD so levam caminho relativo. Nos demais, SBOMs e licencas de terceiros trazem
        # URLs (https://) e caminhos do CI deles (file:///<unidade>/a/...); so o caminho desta maquina e recusado.
        $estrito = $f.Extension -eq '.pth' -or $f.Name -eq 'RECORD'
        if ($estrito -and ($texto -match 'file:///' -or $texto -match '(?<![A-Za-z0-9])[A-Za-z]:[\\/]')) {
            throw "Caminho de maquina no destino: caminho absoluto em $($f.FullName)."
        }
        foreach ($m in @($dest, $raiz, $env:USERPROFILE)) {
            if (-not $m) { continue }
            # bruto, com / e escapado em JSON/TOML (\\)
            foreach ($forma in @($m, $m.Replace('\', '/'), $m.Replace('\', '\\'))) {
                if ($texto.IndexOf($forma, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    throw "Caminho absoluto da maquina no destino: '$m' em $($f.FullName)."
                }
            }
        }
    }
}

# 1. runtime.toml
$tomlConteudo = Get-Content -Raw -Encoding UTF8 $Toml
if ($tomlConteudo -notmatch '(?m)^url = "(.+)"') { throw 'runtime.toml sem a linha url.' }
$url = $Matches[1]
if ($tomlConteudo -notmatch '(?m)^sha256 = "([0-9a-f]{64})"') { throw 'runtime.toml sem sha256 valido (64 hex minusculos).' }
$esperado = $Matches[1]
if ($tomlConteudo -notmatch '(?m)^versao = "(.+)"') { throw 'runtime.toml sem a linha versao.' }
$versaoPython = $Matches[1]

# 2. Nao substitui uma montagem existente: pode conter dados do usuario.
$destinoSeguro = Resolver-Caminho-Seguro $Destino 'destino da montagem'
$cacheSeguro = Resolver-Caminho-Seguro $Cache 'cache de download'
if (-not $SoVerificar -and (Get-Item -LiteralPath $destinoSeguro -Force -ErrorAction SilentlyContinue)) {
    throw 'Destino da montagem ja existe. Mova ou remova a pasta conscientemente antes de montar novamente.'
}
$requisitos = Join-Path $buildPadrao 'requisitos.txt'
$caminhoMedidas = Join-Path $buildPadrao 'nucleo-medidas.json'
if (-not $SoVerificar) {
    foreach ($saida in @($requisitos, $caminhoMedidas)) {
        if (Get-Item -LiteralPath $saida -Force -ErrorAction SilentlyContinue) {
            throw "Arquivo de requisitos ou medidas ja existe; examine-o antes de remove-lo."
        }
    }
}

# 3. download e conferencia
if (-not ($url.StartsWith('https://github.com/') -or $url.StartsWith('https://objects.githubusercontent.com/'))) {
    throw "URL do runtime fora dos hosts permitidos: $url"
}
New-Item -ItemType Directory -Force $cacheSeguro | Out-Null
$nomeArquivo = [System.Uri]::UnescapeDataString(($url -split '/')[-1])
if ($nomeArquivo -in @('', '.', '..') -or $nomeArquivo -match '[/\\]') { throw 'Nome do arquivo de cache invalido.' }
$arquivo = Resolver-Caminho-Seguro (Join-Path $cacheSeguro $nomeArquivo) 'arquivo do cache'
if (-not $SoVerificar) {
    if (-not (Test-Path -LiteralPath $arquivo)) {
        Write-Host "Baixando $url"
        $ProgressPreference = 'SilentlyContinue'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # Destino temporário próprio: nunca escreve direto no caminho final,
        # então uma corrida não tem o arquivo sobrescrito.
        $tempArquivo = Resolver-Caminho-Seguro (Join-Path $cacheSeguro ("descarga-" + $PID + "-" + [Guid]::NewGuid().ToString("N") + ".tmp")) 'download temporario'
        try {
            Invoke-WebRequest -Uri $url -OutFile $tempArquivo -UseBasicParsing
        } catch {
            throw "Falhou: baixar o Python embutido de $url ($($_.Exception.Message)). Qualquer arquivo parcial foi preservado em $tempArquivo para inspecao."
        }
        $obtidoTemp = (Get-FileHash -Algorithm SHA256 -LiteralPath $tempArquivo).Hash.ToLower()
        if ($obtidoTemp -ne $esperado) {
            throw "sha256 do Python embutido nao confere (esperado $esperado, obtido $obtidoTemp). Temporario $tempArquivo preservado; examine-o antes de remove-lo."
        }
        try {
            # Publicação exclusiva: falha se outro processo instalou o cache primeiro.
            [System.IO.File]::Move($tempArquivo, $arquivo)
        } catch [System.IO.IOException] {
            if (Test-Path -LiteralPath $arquivo) {
                $obtidoVencedor = (Get-FileHash -Algorithm SHA256 -LiteralPath $arquivo).Hash.ToLower()
                if ($obtidoVencedor -eq $esperado) {
                    Remove-Item -LiteralPath $tempArquivo -Force -ErrorAction SilentlyContinue
                } else {
                    throw "sha256 do Python embutido nao confere (esperado $esperado, obtido $obtidoVencedor). Cache e temporario $tempArquivo preservados; examine-os antes de remove-los."
                }
            } else {
                throw
            }
        }
    }
    $obtido = (Get-FileHash -Algorithm SHA256 -LiteralPath $arquivo).Hash.ToLower()
    if ($obtido -ne $esperado) {
        throw "sha256 do Python embutido nao confere (esperado $esperado, obtido $obtido). Arquivo do cache preservado; examine-o antes de remove-lo."
    }
} else {
    # Modo SoVerificar: valida hash se arquivo existir, mas nao baixa
    if (Test-Path $arquivo) {
        $obtido = (Get-FileHash -Algorithm SHA256 $arquivo).Hash.ToLower()
        if ($obtido -ne $esperado) {
            throw "sha256 do Python embutido nao confere (esperado $esperado, obtido $obtido). Arquivo do cache preservado; examine-o antes de remove-lo."
        }
    }
}

# 4. extracao
if (-not $SoVerificar) {
    New-Item -ItemType Directory -Path $destinoSeguro -ErrorAction Stop | Out-Null
    Executar 'extrair o Python' { & (Join-Path $env:SystemRoot 'System32\tar.exe') -xzf $arquivo -C $destinoSeguro }
    $py = Join-Path $destinoSeguro 'python\python.exe'
    if (-not (Test-Path $py)) { throw "python.exe nao apareceu em $py depois de extrair." }

    # 5. poda
    $pythonDir = Join-Path $destinoSeguro 'python'
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

    # 6. dependencias do lock, com hashes.
    # Reserva exclusiva + destino temporário próprio: o uv escreve no temporário
    # e a publicação no caminho final não sobrescreve (CreateNew/Move falham se
    # uma concorrência criar o arquivo primeiro; o temporário é preservado).
    $reserva = [System.IO.File]::Open($requisitos, [System.IO.FileMode]::CreateNew)
    $reserva.Dispose()
    Remove-Item -LiteralPath $requisitos -Force -ErrorAction Stop
    $tempRequisitos = Join-Path $buildPadrao ("requisitos-" + $PID + "-" + [Guid]::NewGuid().ToString("N") + ".tmp")
    $travaTemp = [System.IO.File]::Open($tempRequisitos, [System.IO.FileMode]::CreateNew)
    $travaTemp.Dispose()
    Executar 'uv export' { uv export --project (Join-Path $raiz 'nucleo') --frozen --no-dev --no-emit-project --format requirements-txt -o $tempRequisitos }
    try {
        [System.IO.File]::Move($tempRequisitos, $requisitos)
    } catch [System.IO.IOException] {
        throw "Arquivo de requisitos apareceu durante a exportacao (possivel concorrencia); temporario $tempRequisitos preservado para inspecao."
    }
    Executar 'instalar as dependencias' { uv pip install --python $py --require-hashes -r $requisitos --no-cache --link-mode copy }

    # 7. o proprio nucleo (wheel da T1)
    Executar 'instalar o vard' { uv pip install --python $py --no-deps --no-cache (Join-Path $raiz 'nucleo') }

    # 7b. remove metadata com caminho da maquina (PEP 610 grava file:/// local).
    $pacotesInst = Join-Path $pythonDir 'Lib\site-packages'
    try {
        Get-ChildItem -Path $pacotesInst -Recurse -Force -Filter 'direct_url.json' -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction Stop
        Get-ChildItem -Path $pacotesInst -Force -Filter '*.egg-link' -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction Stop
        Get-ChildItem -Path $pacotesInst -Force -Filter '__editable__*.pth' -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction Stop
    } catch {
        throw "Falhou: remover metadata com caminho da maquina ($($_.Exception.Message))."
    }

    # 7c. varredura: caminho absoluto, file:/// ou letra de unidade travam a montagem.
    Validar-Caminhos-No-Destino $destinoSeguro

    # 8. lancadores com caminho absoluto
    $scripts = Join-Path $pythonDir 'Scripts'
    try {
        if (Test-Path $scripts) { Remove-Item -Recurse -Force $scripts }
    } catch {
        throw "Falhou: apagar $scripts ($($_.Exception.Message))."
    }

    # 9. varredura de segredos ANTES de compileall/smoke
    Validar-Segredos-No-Destino $destinoSeguro

    # 10. pre-compilacao (a instalacao MSI fica em pasta so de leitura).
    # -s/-p evitam embutir o caminho absoluto do build (co_filename) nos .pyc distribuidos.
    Executar 'compileall' { & $py -I -m compileall -q -j 0 -s $pythonDir -p /nucleo (Join-Path $pythonDir 'Lib') }

    # 11. teste rapido
    $versaoNucleo = $null
    if ((Get-Content -Raw -Encoding UTF8 (Join-Path $raiz 'nucleo\pyproject.toml')) -match '(?m)^version = "([^"]+)"') { $versaoNucleo = $Matches[1] }
    if (-not $versaoNucleo) { throw 'pyproject.toml do nucleo sem version.' }
    $saida = (& $py -I -X utf8 -m vard --versao | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "vard --versao falhou (codigo $LASTEXITCODE)." }
    if ($saida -notmatch [regex]::Escape($versaoNucleo)) { throw "Versao do nucleo montado ('$saida') difere do pyproject ($versaoNucleo)." }
    Executar 'importar as dependencias' { & $py -I -c 'import fastapi, uvicorn, httpx, psutil' }
    Executar 'importar server e MCPs' { & $py -I -c 'import vard.server, vard.consulta_mcp, vard.memoria_mcp, vard.mesa_mcp, vard.oficina_mcp, vard.reuniao_mcp, vard.configuracoes_mcp, vard.preflight' }

    # 12. medidas
    $base = (Resolve-Path $destinoSeguro).Path.TrimEnd('\') + '\'
    $itens = Get-ChildItem $destinoSeguro -Recurse -Force
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
    $arquivoMedidas = [System.IO.File]::Open($caminhoMedidas, [System.IO.FileMode]::CreateNew)
    $escritor = New-Object System.IO.StreamWriter($arquivoMedidas, (New-Object System.Text.UTF8Encoding($false)))
    try { $escritor.Write($json) } finally { $escritor.Dispose() }
    Write-Host $json
    if ($maior.Length -gt 160) { throw "Maior caminho do runtime tem $($maior.Length) caracteres (limite 160): $maior" }
    Write-Host 'Runtime montado em build\nucleo.'
} else {
    # SoVerificar: apenas valida caminhos e segredos no destino existente (se houver)
    if (Test-Path $destinoSeguro) {
        Validar-Segredos-No-Destino $destinoSeguro
        Validar-Caminhos-No-Destino $destinoSeguro
    }
    Write-Host 'Verificacao concluida (modo -SoVerificar).'
}
