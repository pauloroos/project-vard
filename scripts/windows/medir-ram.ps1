<#
.SYNOPSIS
    Medidor de memória RAM por árvore de processos para o Project Vard no Windows.
.DESCRIPTION
    Script somente leitura que recebe um ou mais PIDs raiz (-PidsRaiz) e inspeciona
    a árvore completa de processos utilizando Win32_Process e Get-Process.
    Calcula Working Set (WorkingSet64) e Private Bytes (PrivateMemorySize64)
    por processo, agregando os totais por componente do Vard e total geral.
    Também suporta modo de autoteste puramente lógico (-AutoTeste) com dados
    sintéticos, executável sem tocar em processos reais.

.PARAMETER PidsRaiz
    Um ou mais IDs de processo (PID) raiz da árvore a ser medida.
    Obrigatório, exceto quando -AutoTeste é especificado.

.PARAMETER Estado
    Rótulo do cenário operacional medido. Valores aceitos:
    'repouso', 'conversa', 'sala', 'configuracoes'.
    Obrigatório, exceto quando -AutoTeste é especificado.

.PARAMETER Amostras
    Número de amostras consecutivas a coletar (padrão: 3).

.PARAMETER IntervaloSeg
    Intervalo em segundos entre amostras consecutivas (padrão: 2.0).

.PARAMETER SaidaJson
    Caminho de arquivo opcional para gravação do resultado estruturado em JSON.
    Se omitido, o script emite tabelas formatadas no console padrão.

.PARAMETER AutoTeste
    Executa a verificação lógica interna das rotinas puras (classificação,
    agregação, herança de pai, detecção de PID encerrado, deduplicação de raiz,
    cálculo de mediana/faixa e compatibilidade de início/reutilização de PID)
    com dados fictícios e sai com código 0 ou 1.

.NOTES
    Compatibilidade: Windows PowerShell 5.1+ e PowerShell Core (pwsh 7+).
    Natureza: Somente leitura. Não altera, inicia nem finaliza processos.

    === Os quatro cenários operacionais e como atingir cada um ===
    1. repouso:
       Aplicação Vard aberta e ociosa. O widget HUD está visível na tela,
       o microfone escuta com VAD ativado e nenhuma interação ou síntese de voz
       está ocorrendo.
    2. conversa:
       Interação ativa em andamento. O assistente está processando uma pergunta
       do usuário, transmitindo tokens via SSE do cérebro ou sintetizando áudio
       via serviço de voz.
    3. sala:
       Janela da sala aberta em tela cheia (disparada via atalho ou comando).
       O widget HUD é escondido (hide) enquanto a sala permanece em primeiro
       plano desenhando visualizações/canvas.
    4. configuracoes:
       Janela dedicada de Configurações aberta (atalho ou clique na engrenagem),
       com suas abas de opções ativas em processo WebView2 próprio.

    === Limitações técnicas da medição ===
    1. Páginas compartilhadas e Working Set:
       A soma simples de Working Set (WorkingSet64 / RSS) entre processos conta
       páginas de memória compartilhadas (ex.: DLLs do sistema, runtime WebView2,
       bibliotecas CPython) mais de uma vez.
    2. Private Bytes é aditivo:
       Private Bytes (PrivateMemorySize64 / Commit Charge Privado) representa
       a memória física/virtual de uso exclusivo do processo e constitui a
       métrica aditiva rigorosa para auditoria de consumo e vazamento.
    3. Múltiplos subprocessos do WebView2:
       O Microsoft Edge WebView2 instancia dinamicamente processos de navegador,
       GPU, utilitários e renderizadores dedicados para cada janela web.
    4. Memória de GPU não aferida:
       Pesos de modelos neurais residentes em VRAM de aceleradores gráficos
       (GPU dedicada) não são visíveis nas métricas de processo do Windows NT.
    5. Amostragem instantânea (fotografia):
       A medição reflete o estado instantâneo do heap no momento da coleta,
       sujeito a rotinas de coleta de lixo (GC) e alocações dinâmicas.
    6. Validação de PID reutilizado:
       A data do snapshot é comparada ao StartTime, quando ambos estão disponíveis.
       Datas ausentes e trocas entre consultas limitam essa detecção.
    7. Permissões de leitura:
       Requer permissão de usuário padrão para inspecionar processos próprios
       ou privilégios administrativos para processos de contas de serviço.
#>

[CmdletBinding(DefaultParameterSetName = "Medicao")]
param(
    [Parameter(ParameterSetName = "Medicao", Mandatory = $true, Position = 0)]
    [int[]]$PidsRaiz,

    [Parameter(ParameterSetName = "Medicao", Mandatory = $true, Position = 1)]
    [ValidateSet("repouso", "conversa", "sala", "configuracoes")]
    [string]$Estado,

    [Parameter(ParameterSetName = "Medicao")]
    [int]$Amostras = 3,

    [Parameter(ParameterSetName = "Medicao")]
    [double]$IntervaloSeg = 2.0,

    [Parameter(ParameterSetName = "Medicao")]
    [string]$SaidaJson = "",

    [Parameter(ParameterSetName = "AutoTeste", Mandatory = $true)]
    [switch]$AutoTeste
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Constantes de componentes alinhadas com nucleo/vard/recursos.py
$script:COMPONENTES_ORDEM = @(
    "Widget",
    "Núcleo",
    "Cérebro (CLI)",
    "MCPs",
    "Voz",
    "Reunião",
    "Bandeja",
    "Outros"
)

# -----------------------------------------------------------------------------
# Funções puras (testáveis e independentes de WMI/Get-Process real)
# -----------------------------------------------------------------------------

function Classificar-Processo {
    <#
    .SYNOPSIS
        Classifica o componente pelo nome do executável e linha de comando,
        seguindo a convenção de nucleo/vard/recursos.py.
    #>
    param(
        [string]$Nome,
        [string]$Comando
    )

    $exe = if ($Nome) { $Nome.Trim().ToLowerInvariant() } else { "" }
    $cmd = if ($Comando) { $Comando.ToLowerInvariant() } else { "" }

    # 1. MCPs: scripts com sufixo _mcp.py ou windows-mcp
    if ($cmd -match '(_mcp\.py\b|windows-mcp)') {
        return "MCPs"
    }

    # 2. Núcleo: uvicorn server:app ou vard servir
    if (($cmd -match 'uvicorn' -and $cmd -match 'server:app') -or ($cmd -match '\bvard\b' -and $cmd -match '\bservir\b')) {
        return "Núcleo"
    }

    # 3. Voz: vard_voz
    if ($cmd -match 'vard_voz') {
        return "Voz"
    }

    # 4. Reunião: vard_reuniao
    if ($cmd -match 'vard_reuniao') {
        return "Reunião"
    }

    # 5. Bandeja: bandeja.py
    if ($cmd -match 'bandeja\.py') {
        return "Bandeja"
    }

    # 6. Cérebro CLI: claude, agy
    if ($exe -in @("claude.exe", "claude", "agy.exe", "agy")) {
        return "Cérebro (CLI)"
    }

    # 7. Widget / Tauri / WebView2
    if ($exe -in @("vard.exe", "msedgewebview2.exe")) {
        return "Widget"
    }

    return $null
}

function Testar-InicioCompativel {
    <#
    .SYNOPSIS
        Verifica se o StartTime atual de um processo é compatível com o esperado.
        Se qualquer lado for nulo ou DateTime.MinValue, não considera compatível.
        Compara em UTC no mesmo microssegundo, precisão do formato CIM_DATETIME.
    #>
    param(
        [object]$InicioEsperado,
        [object]$InicioAtual
    )

    if ($null -eq $InicioEsperado -or $null -eq $InicioAtual) {
        return $false
    }

    # Trata caso de coerção para DateTime.MinValue
    if ($InicioEsperado -is [datetime] -and $InicioEsperado -eq [datetime]::MinValue) {
        return $false
    }
    if ($InicioAtual -is [datetime] -and $InicioAtual -eq [datetime]::MinValue) {
        return $false
    }

    try {
        $dtEsp = [datetime]$InicioEsperado
        $dtAtu = [datetime]$InicioAtual
        if ($dtEsp -eq [datetime]::MinValue -or $dtAtu -eq [datetime]::MinValue) {
            return $false
        }
        $ticksEsp = $dtEsp.ToUniversalTime().Ticks
        $ticksAtu = $dtAtu.ToUniversalTime().Ticks
        return (($ticksEsp - ($ticksEsp % 10)) -eq ($ticksAtu - ($ticksAtu % 10)))
    } catch {
        return $false
    }
}

function Converter-InicioWmi {
    param([object]$Inicio)
    if ($Inicio -is [datetime]) { return $Inicio }
    if (-not $Inicio) { return $null }
    try { return [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$Inicio) }
    catch { return $null }
}

function Obter-Arquitetura {
    param([string]$Nome)
    switch ($Nome.ToUpperInvariant()) {
        "AMD64" { return "x64" }
        "ARM64" { return "arm64" }
        "X86" { return "x86" }
        default { return "desconhecida" }
    }
}

function Calcular-Mediana {
    param([double[]]$Valores)
    if (-not $Valores -or $Valores.Count -eq 0) { return 0.0 }
    $ordenados = @($Valores | Sort-Object)
    $n = $ordenados.Count
    if ($n % 2 -eq 1) {
        return [Math]::Round([double]$ordenados[[int][Math]::Floor($n / 2)], 2)
    } else {
        $m1 = $ordenados[($n / 2) - 1]
        $m2 = $ordenados[$n / 2]
        return [Math]::Round(([double]($m1 + $m2) / 2.0), 2)
    }
}

function Calcular-EstatisticaFaixa {
    param([double[]]$Valores)
    if (-not $Valores -or $Valores.Count -eq 0) {
        return [ordered]@{ mediana = 0.0; min = 0.0; max = 0.0 }
    }
    $ordenados = @($Valores | Sort-Object)
    return [ordered]@{
        mediana = Calcular-Mediana $Valores
        min     = [Math]::Round([double]$ordenados[0], 2)
        max     = [Math]::Round([double]$ordenados[-1], 2)
    }
}

function Resolver-ArvorePura {
    <#
    .SYNOPSIS
        Monta a árvore lógica de processos e propaga a classificação por herança.
        Funciona com [object[]] (CimInstance, PSCustomObject ou Hashtable).
        Cada processo entra uma única vez.
    #>
    param(
        [int[]]$PidsRaiz,
        [object[]]$TabelaProcessos
    )

    $tabelaPorPid = @{}
    $filhosPorPai = @{}

    foreach ($p in $TabelaProcessos) {
        if ($null -eq $p) { continue }
        $processoId = [int]$p.ProcessId
        $paiId = [int]$p.ParentProcessId

        $tabelaPorPid[$processoId] = $p

        if (-not $filhosPorPai.ContainsKey($paiId)) {
            $filhosPorPai[$paiId] = New-Object System.Collections.Generic.List[int]
        }
        $filhosPorPai[$paiId].Add($processoId)
    }

    $vistos = New-Object 'System.Collections.Generic.HashSet[int]'
    $resultadoArvores = @()

    # Ancestrais primeiro preservam a classificação herdada em raízes sobrepostas.
    $raizesOrdenadas = @($PidsRaiz | Sort-Object -Unique | Sort-Object {
        $atual = $_
        $visitados = @{}
        $profundidade = 0
        while ($tabelaPorPid.ContainsKey($atual) -and -not $visitados.ContainsKey($atual)) {
            $visitados[$atual] = $true
            $atual = [int]$tabelaPorPid[$atual].ParentProcessId
            $profundidade++
        }
        $profundidade
    })
    foreach ($raizId in $raizesOrdenadas) {
        if ($vistos.Contains($raizId)) {
            continue
        }
        if (-not $tabelaPorPid.ContainsKey($raizId)) {
            continue
        }

        $raizInfo = $tabelaPorPid[$raizId]
        $nomeRaiz = [string]$raizInfo.Name
        $inicioRaiz = if ($raizInfo.CreationDate) { [string]$raizInfo.CreationDate } else { "" }

        $processosDaArvore = @()
        $fila = New-Object 'System.Collections.Generic.Queue[hashtable]'

        $catRaiz = Classificar-Processo -Nome $raizInfo.Name -Comando $raizInfo.CommandLine
        if (-not $catRaiz) {
            $catRaiz = if ($raizInfo.Name -match '(?i)vard\.exe') { "Widget" } else { "Outros" }
        }

        $fila.Enqueue(@{
            Pid = $raizId
            Pai = [int]$raizInfo.ParentProcessId
            Nome = [string]$raizInfo.Name
            Comando = [string]$raizInfo.CommandLine
            Inicio = $raizInfo.CreationDate
            Categoria = $catRaiz
        })
        [void]$vistos.Add($raizId)

        while ($fila.Count -gt 0) {
            $item = $fila.Dequeue()
            $processoId = [int]$item.Pid
            $processosDaArvore += $item

            if ($filhosPorPai.ContainsKey($processoId)) {
                foreach ($filhoId in $filhosPorPai[$processoId]) {
                    if ($vistos.Contains($filhoId)) {
                        continue
                    }
                    if (-not $tabelaPorPid.ContainsKey($filhoId)) {
                        continue
                    }
                    $fInfo = $tabelaPorPid[$filhoId]
                    $inicioPai = Converter-InicioWmi $tabelaPorPid[$processoId].CreationDate
                    $inicioFilho = Converter-InicioWmi $fInfo.CreationDate
                    if ($null -ne $inicioPai -and $null -ne $inicioFilho -and $inicioFilho -lt $inicioPai) {
                        continue
                    }
                    $catPropria = Classificar-Processo -Nome $fInfo.Name -Comando $fInfo.CommandLine
                    # Se pai for Cérebro (CLI), filhos herdam a categoria obrigatoriamente
                    # conforme nucleo/vard/recursos.py (_categoria: debaixo de CLI tudo conta para ela)
                    $catFinal = if ($item.Categoria -eq "Cérebro (CLI)") {
                        "Cérebro (CLI)"
                    } elseif ($catPropria) {
                        $catPropria
                    } else {
                        $item.Categoria
                    }

                    [void]$vistos.Add($filhoId)
                    $fila.Enqueue(@{
                        Pid = $filhoId
                        Pai = $processoId
                        Nome = [string]$fInfo.Name
                        Comando = [string]$fInfo.CommandLine
                        Inicio = $fInfo.CreationDate
                        Categoria = $catFinal
                    })
                }
            }
        }

        $resultadoArvores += @{
            pid_raiz = $raizId
            nome = $nomeRaiz
            inicio = $inicioRaiz
            processos = $processosDaArvore
        }
    }

    return @{
        arvores = $resultadoArvores
        total_processos_unicos = $vistos.Count
    }
}

function Consolidar-AmostraPura {
    <#
    .SYNOPSIS
        Recebe a árvore resolvida e o mapa de leituras de memória de uma amostra,
        calculando o resumo por processo, por componente e total.
    #>
    param(
        [array]$Arvores,
        [hashtable]$MapaMemoria
    )

    $compMap = @{}
    foreach ($c in $script:COMPONENTES_ORDEM) {
        $compMap[$c] = @{
            nome = $c
            working_set_mb = 0.0
            private_mb = 0.0
            processos = 0
            pids = New-Object System.Collections.Generic.List[int]
        }
    }

    $arvoresFormatadas = @()
    $totalWs = 0.0
    $totalPb = 0.0
    $totalProcsContados = 0

    foreach ($arv in $Arvores) {
        $procsFormatados = @()
        foreach ($p in $arv.processos) {
            $processoId = [int]$p.Pid
            $leitura = if ($MapaMemoria.ContainsKey($processoId)) { $MapaMemoria[$processoId] } else { $null }

            $wsMb = 0.0
            $pbMb = 0.0
            $encerrado = $false

            if ($null -ne $leitura -and -not $leitura.encerrado) {
                $wsMb = [Math]::Round([double]$leitura.working_set_mb, 2)
                $pbMb = [Math]::Round([double]$leitura.private_mb, 2)
            } else {
                $encerrado = $true
            }

            $cat = if ($p.Categoria -and $compMap.ContainsKey($p.Categoria)) { $p.Categoria } else { "Outros" }

            if (-not $encerrado) {
                $compMap[$cat].working_set_mb += $wsMb
                $compMap[$cat].private_mb += $pbMb
                $compMap[$cat].processos += 1
                $compMap[$cat].pids.Add($processoId)

                $totalWs += $wsMb
                $totalPb += $pbMb
                $totalProcsContados += 1
            }

            $procObj = [ordered]@{
                pid = $processoId
                pai = [int]$p.Pai
                nome = [string]$p.Nome
                componente = $cat
                working_set_mb = $wsMb
                private_mb = $pbMb
            }
            if ($encerrado) {
                $procObj["encerrado"] = $true
            }
            if ($null -ne $leitura -and $leitura.ContainsKey("nao_verificavel")) {
                $procObj["nao_verificavel"] = $true
            }
            $procsFormatados += $procObj
        }

        $arvoresFormatadas += [ordered]@{
            pid_raiz = $arv.pid_raiz
            nome = $arv.nome
            inicio = $arv.inicio
            processos = $procsFormatados
        }
    }

    $compLista = @()
    foreach ($c in $script:COMPONENTES_ORDEM) {
        $item = $compMap[$c]
        if ($item.processos -gt 0) {
            $compLista += [ordered]@{
                nome = $c
                working_set_mb = [Math]::Round([double]$item.working_set_mb, 2)
                private_mb = [Math]::Round([double]$item.private_mb, 2)
                processos = [int]$item.processos
            }
        }
    }

    return @{
        arvores = $arvoresFormatadas
        componentes = $compLista
        total = [ordered]@{
            working_set_mb = [Math]::Round([double]$totalWs, 2)
            private_mb = [Math]::Round([double]$totalPb, 2)
            processos = [int]$totalProcsContados
        }
    }
}

function Gerar-ResumoSeries {
    <#
    .SYNOPSIS
        Calcula estatísticas de resumo (mediana, mín e máx) para o total geral,
        para cada componente e para cada processo ativo ao longo de todas as amostras.
    #>
    param(
        [array]$AmostrasColetadas
    )

    if (-not $AmostrasColetadas -or $AmostrasColetadas.Count -eq 0) {
        return [ordered]@{}
    }

    $seriesWsTotal = @()
    $seriesPbTotal = @()
    $seriesComp = @{}
    $seriesProc = @{}

    foreach ($amostra in $AmostrasColetadas) {
        $seriesWsTotal += [double]$amostra.total.working_set_mb
        $seriesPbTotal += [double]$amostra.total.private_mb

        foreach ($c in $amostra.componentes) {
            $cNome = [string]$c.nome
            if (-not $seriesComp.ContainsKey($cNome)) {
                $seriesComp[$cNome] = @{
                    ws = New-Object System.Collections.Generic.List[double]
                    pb = New-Object System.Collections.Generic.List[double]
                }
            }
            $seriesComp[$cNome].ws.Add([double]$c.working_set_mb)
            $seriesComp[$cNome].pb.Add([double]$c.private_mb)
        }

        foreach ($arv in $amostra.arvores) {
            foreach ($p in $arv.processos) {
                $processoId = [int]$p.pid
                if (-not $seriesProc.ContainsKey($processoId)) {
                    $seriesProc[$processoId] = @{
                        nome = [string]$p.nome
                        componente = [string]$p.componente
                        ws = New-Object System.Collections.Generic.List[double]
                        pb = New-Object System.Collections.Generic.List[double]
                    }
                }
                if (-not $p.Contains("encerrado") -or -not $p.encerrado) {
                    $seriesProc[$processoId].ws.Add([double]$p.working_set_mb)
                    $seriesProc[$processoId].pb.Add([double]$p.private_mb)
                }
            }
        }
    }

    $resumoComp = [ordered]@{}
    foreach ($cNome in $script:COMPONENTES_ORDEM) {
        if ($seriesComp.ContainsKey($cNome)) {
            $wsArr = @($seriesComp[$cNome].ws)
            $pbArr = @($seriesComp[$cNome].pb)
            $resumoComp[$cNome] = [ordered]@{
                working_set_mb = Calcular-EstatisticaFaixa $wsArr
                private_mb     = Calcular-EstatisticaFaixa $pbArr
            }
        }
    }

    $resumoProc = @()
    foreach ($processoId in ($seriesProc.Keys | Sort-Object)) {
        $pInfo = $seriesProc[$processoId]
        $wsArr = @($pInfo.ws)
        $pbArr = @($pInfo.pb)
        if ($wsArr.Count -gt 0) {
            $resumoProc += [ordered]@{
                pid            = $processoId
                nome           = $pInfo.nome
                componente     = $pInfo.componente
                working_set_mb = Calcular-EstatisticaFaixa $wsArr
                private_mb     = Calcular-EstatisticaFaixa $pbArr
            }
        }
    }

    return [ordered]@{
        total = [ordered]@{
            working_set_mb = Calcular-EstatisticaFaixa $seriesWsTotal
            private_mb     = Calcular-EstatisticaFaixa $seriesPbTotal
        }
        componentes = $resumoComp
        processos   = $resumoProc
    }
}

# -----------------------------------------------------------------------------
# Autoteste (--AutoTeste) com dados sintéticos
# -----------------------------------------------------------------------------

function Executar-AutoTeste {
    Write-Host "[AutoTeste] Iniciando verificação de lógica do medidor de RAM..."

    # Teste 1: Classificação direta de comandos
    $c1 = Classificar-Processo -Nome "python.exe" -Comando "python nucleo/mesa_mcp.py"
    if ($c1 -ne "MCPs") { throw "Falha Teste 1: esperado MCPs, obteve $c1" }

    $c2 = Classificar-Processo -Nome "python.exe" -Comando "uvicorn server:app --host 127.0.0.1"
    if ($c2 -ne "Núcleo") { throw "Falha Teste 1: esperado Núcleo, obteve $c2" }

    $c3 = Classificar-Processo -Nome "python.exe" -Comando "python -m vard_voz"
    if ($c3 -ne "Voz") { throw "Falha Teste 1: esperado Voz, obteve $c3" }

    $c4 = Classificar-Processo -Nome "python.exe" -Comando "python -m vard_reuniao"
    if ($c4 -ne "Reunião") { throw "Falha Teste 1: esperado Reunião, obteve $c4" }

    $c5 = Classificar-Processo -Nome "python.exe" -Comando "python scripts/windows/bandeja.py"
    if ($c5 -ne "Bandeja") { throw "Falha Teste 1: esperado Bandeja, obteve $c5" }

    $c6 = Classificar-Processo -Nome "claude.exe" -Comando "claude"
    if ($c6 -ne "Cérebro (CLI)") { throw "Falha Teste 1: esperado Cérebro (CLI), obteve $c6" }

    $c7 = Classificar-Processo -Nome "msedgewebview2.exe" -Comando "msedgewebview2.exe --type=renderer"
    if ($c7 -ne "Widget") { throw "Falha Teste 1: esperado Widget, obteve $c7" }
    Write-Host "  [OK] Classificação de executáveis e comandos observáveis."

    # Teste 2: Herança de classificação pelo pai e árvore pura com tipos reais (PSCustomObject / CimInstance)
    # Cenário de processos sintéticos com tipos heterogêneos:
    # 100 (vard.exe) -> 200 (conhost.exe sem comando -> herda Widget)
    # 100 -> 300 (python uvicorn server:app -> Núcleo)
    # 300 -> 301 (python nucleo/mesa_mcp.py -> MCPs)
    # 300 -> 302 (python worker_auxiliar.py sem regra -> herda Núcleo do pai 300)
    # 100 -> 400 (claude.exe -> Cérebro (CLI))
    # 400 -> 401 (cmd.exe auxiliar -> herda Cérebro (CLI) porque está sob CLI)
    # 401 -> 402 (node.exe subprocesso de cmd.exe sob CLI -> herda Cérebro (CLI))
    $tabelaFicticia = @(
        [PSCustomObject]@{ ProcessId = 100; ParentProcessId = 1;   Name = "vard.exe";           CommandLine = "vard.exe"; CreationDate = "20261102000000.000000+000" },
        @{ ProcessId = 200; ParentProcessId = 100; Name = "conhost.exe";        CommandLine = "conhost.exe"; CreationDate = "20261102000001.000000+000" },
        [PSCustomObject]@{ ProcessId = 300; ParentProcessId = 100; Name = "python.exe";         CommandLine = "uv run uvicorn server:app"; CreationDate = "20261102000002.000000+000" },
        @{ ProcessId = 301; ParentProcessId = 300; Name = "python.exe";         CommandLine = "python nucleo/mesa_mcp.py"; CreationDate = "20261102000003.000000+000" },
        [PSCustomObject]@{ ProcessId = 302; ParentProcessId = 300; Name = "python.exe";         CommandLine = "python worker_auxiliar.py"; CreationDate = "20261102000004.000000+000" },
        @{ ProcessId = 400; ParentProcessId = 100; Name = "claude.exe";         CommandLine = "claude.exe"; CreationDate = "20261102000005.000000+000" },
        [PSCustomObject]@{ ProcessId = 401; ParentProcessId = 400; Name = "cmd.exe";            CommandLine = "cmd.exe /c echo ok"; CreationDate = "20261102000006.000000+000" },
        [PSCustomObject]@{ ProcessId = 402; ParentProcessId = 401; Name = "node.exe";           CommandLine = "node worker.js"; CreationDate = "20261102000007.000000+000" }
    )

    $resArvore = Resolver-ArvorePura -PidsRaiz @(100) -TabelaProcessos $tabelaFicticia
    $procMap = @{}
    foreach ($p in $resArvore.arvores[0].processos) {
        $procMap[$p.Pid] = $p.Categoria
    }

    if ($procMap[100] -ne "Widget") { throw "Falha Teste 2: PID 100 deveria ser Widget" }
    if ($procMap[200] -ne "Widget") { throw "Falha Teste 2: PID 200 deveria herdar Widget do pai 100" }
    if ($procMap[300] -ne "Núcleo") { throw "Falha Teste 2: PID 300 deveria ser Núcleo" }
    if ($procMap[301] -ne "MCPs") { throw "Falha Teste 2: PID 301 deveria ser MCPs" }
    if ($procMap[302] -ne "Núcleo") { throw "Falha Teste 2: PID 302 deveria herdar Núcleo do pai 300" }
    if ($procMap[400] -ne "Cérebro (CLI)") { throw "Falha Teste 2: PID 400 deveria ser Cérebro (CLI)" }
    if ($procMap[401] -ne "Cérebro (CLI)") { throw "Falha Teste 2: PID 401 debaixo de CLI deveria ser Cérebro (CLI)" }
    if ($procMap[402] -ne "Cérebro (CLI)") { throw "Falha Teste 2: PID 402 descendente de CLI deveria ser Cérebro (CLI)" }
    Write-Host "  [OK] Herança de categoria (incluindo Cérebro) e suporte a objetos reais."

    # Teste 3: Deduplicação de PID raiz repetido ou sobreposto
    $resDup = Resolver-ArvorePura -PidsRaiz @(100, 100, 300) -TabelaProcessos $tabelaFicticia
    if ($resDup.total_processos_unicos -ne 8) {
        throw "Falha Teste 3: esperado 8 processos únicos, obteve $($resDup.total_processos_unicos)"
    }
    Write-Host "  [OK] Deduplicação de PIDs raiz repetidos ou sobrepostos."

    # Teste 4: Soma por componentes e total geral com simulação de PID encerrado
    $mapaMem = @{
        100 = @{ working_set_mb = 120.0; private_mb = 90.0; encerrado = $false }
        200 = @{ working_set_mb = 15.0;  private_mb = 10.0; encerrado = $false }
        300 = @{ working_set_mb = 60.0;  private_mb = 50.0; encerrado = $false }
        301 = @{ working_set_mb = 70.0;  private_mb = 65.0; encerrado = $false }
        # 302 foi encerrado no meio da coleta
        302 = @{ working_set_mb = 0.0;   private_mb = 0.0;  encerrado = $true }
        400 = @{ working_set_mb = 80.0;  private_mb = 75.0; encerrado = $false }
        401 = @{ working_set_mb = 25.0;  private_mb = 20.0; encerrado = $false }
        402 = @{ working_set_mb = 30.0;  private_mb = 25.0; encerrado = $false }
    }

    $consolidado = Consolidar-AmostraPura -Arvores $resArvore.arvores -MapaMemoria $mapaMem

    # Processos ativos: 7 (302 ignorado por estar encerrado)
    if ($consolidado.total.processos -ne 7) {
        throw "Falha Teste 4: esperado 7 processos ativos no total, obteve $($consolidado.total.processos)"
    }

    # Working set esperado: 120 + 15 + 60 + 70 + 80 + 25 + 30 = 400.0 MB
    if ([Math]::Abs($consolidado.total.working_set_mb - 400.0) -gt 0.01) {
        throw "Falha Teste 4: WS total esperado 400.0 MB, obteve $($consolidado.total.working_set_mb)"
    }

    # Private bytes esperado: 90 + 10 + 50 + 65 + 75 + 20 + 25 = 335.0 MB
    if ([Math]::Abs($consolidado.total.private_mb - 335.0) -gt 0.01) {
        throw "Falha Teste 4: PB total esperado 335.0 MB, obteve $($consolidado.total.private_mb)"
    }

    # Componente Widget: 100 (120/90) + 200 (15/10) = 135.0 WS / 100.0 PB
    $compWidget = $consolidado.componentes | Where-Object { $_.nome -eq "Widget" }
    if ($compWidget.working_set_mb -ne 135.0 -or $compWidget.private_mb -ne 100.0) {
        throw "Falha Teste 4: Widget incorreto: WS=$($compWidget.working_set_mb) PB=$($compWidget.private_mb)"
    }

    # Componente Cérebro (CLI): 400 (80/75) + 401 (25/20) + 402 (30/25) = 135.0 WS / 120.0 PB
    $compCerebro = $consolidado.componentes | Where-Object { $_.nome -eq "Cérebro (CLI)" }
    if ($compCerebro.working_set_mb -ne 135.0 -or $compCerebro.private_mb -ne 120.0) {
        throw "Falha Teste 4: Cérebro (CLI) incorreto: WS=$($compCerebro.working_set_mb) PB=$($compCerebro.private_mb)"
    }
    Write-Host "  [OK] Agregação de memória por componente e tratamento de PID encerrado."

    # Teste 5: Cálculo de mediana e faixa
    $estat = Calcular-EstatisticaFaixa @(105.0, 98.0, 100.0)
    if ($estat.mediana -ne 100.0 -or $estat.min -ne 98.0 -or $estat.max -ne 105.0) {
        throw "Falha Teste 5: Estatística com 3 elementos incorreta"
    }
    $estatPar = Calcular-EstatisticaFaixa @(10.0, 20.0, 30.0, 40.0)
    if ($estatPar.mediana -ne 25.0) {
        throw "Falha Teste 5: Mediana par incorreta"
    }
    Write-Host "  [OK] Estatísticas de dispersão (mediana, mínimo e máximo)."

    # Teste 6: Compatibilidade de StartTime e reutilização de PID
    $dtBase = [datetime]::Parse("2026-11-02T10:00:00Z").ToUniversalTime()
    $dtPerto = $dtBase.AddTicks(9)
    $dtReutilizadoRapido = $dtBase.AddTicks(10)
    $dtLonge = $dtBase.AddSeconds(30)
    $dtMin = [datetime]::MinValue

    # (a) Mesmo início: compatível
    if (-not (Testar-InicioCompativel -InicioEsperado $dtBase -InicioAtual $dtBase)) {
        throw "Falha Teste 6a: Mesmo início deveria ser compatível"
    }
    # (b) O formato CIM limita a precisão a microssegundos (10 ticks de 100 ns).
    if (-not (Testar-InicioCompativel -InicioEsperado $dtBase -InicioAtual $dtPerto)) {
        throw "Falha Teste 6b: mesmo microssegundo deveria ser compatível"
    }
    if (Testar-InicioCompativel -InicioEsperado $dtBase -InicioAtual $dtReutilizadoRapido) {
        throw "Falha Teste 6b: um microssegundo diferente não deve ser compatível"
    }
    # (c) Diferença grande (30s > 5s): PID reutilizado, deve ser incompatível ($false)
    if (Testar-InicioCompativel -InicioEsperado $dtBase -InicioAtual $dtLonge) {
        throw "Falha Teste 6c: Início diferente além da tolerância deveria ser incompatível (reutilizado)"
    }
    # (d) Sem início conhecido: não é possível verificar a identidade.
    if (Testar-InicioCompativel -InicioEsperado $null -InicioAtual $dtBase) {
        throw "Falha Teste 6d: início ausente não deve ser compatível"
    }
    if (Testar-InicioCompativel -InicioEsperado $dtBase -InicioAtual $null) {
        throw "Falha Teste 6d: início atual ausente não deve ser compatível"
    }
    if (Testar-InicioCompativel -InicioEsperado $dtMin -InicioAtual $dtBase) {
        throw "Falha Teste 6d: DateTime.MinValue não deve ser compatível"
    }
    Write-Host "  [OK] Detecção de reutilização de PID e rejeição de identidade desconhecida."

    # Teste 7: Resumo estruturado com séries e agregação por componente e processo
    $amostra1 = $consolidado
    # Amostra 2 sintética com pequena variação
    $mapaMem2 = @{
        100 = @{ working_set_mb = 122.0; private_mb = 91.0; encerrado = $false }
        200 = @{ working_set_mb = 16.0;  private_mb = 11.0; encerrado = $false }
        300 = @{ working_set_mb = 62.0;  private_mb = 52.0; encerrado = $false }
        301 = @{ working_set_mb = 72.0;  private_mb = 66.0; encerrado = $false }
        302 = @{ working_set_mb = 0.0;   private_mb = 0.0;  encerrado = $true }
        400 = @{ working_set_mb = 81.0;  private_mb = 76.0; encerrado = $false }
        401 = @{ working_set_mb = 26.0;  private_mb = 21.0; encerrado = $false }
        402 = @{ working_set_mb = 31.0;  private_mb = 26.0; encerrado = $false }
    }
    $amostra2 = Consolidar-AmostraPura -Arvores $resArvore.arvores -MapaMemoria $mapaMem2
    $resumoMultiplo = Gerar-ResumoSeries -AmostrasColetadas @($amostra1, $amostra2)

    if (-not $resumoMultiplo.total -or -not $resumoMultiplo.componentes -or -not $resumoMultiplo.processos) {
        throw "Falha Teste 7: Resumo múltiplo incompleto"
    }
    if ($resumoMultiplo.processos.Count -ne 7) {
        throw "Falha Teste 7: esperado resumo de 7 processos ativos, obteve $($resumoMultiplo.processos.Count)"
    }
    if ($resumoMultiplo.componentes["Widget"].working_set_mb.mediana -ne 136.5) {
        throw "Falha Teste 7: Mediana do componente Widget esperada 136.5, obteve $($resumoMultiplo.componentes['Widget'].working_set_mb.mediana)"
    }
    Write-Host "  [OK] Estruturação do resumo estatístico por componente e processo."

    $invertida = Resolver-ArvorePura -PidsRaiz @(401, 100) -TabelaProcessos $tabelaFicticia
    $categoriasInvertidas = @{}
    foreach ($arvore in $invertida.arvores) {
        foreach ($processo in $arvore.processos) { $categoriasInvertidas[$processo.Pid] = $processo.Categoria }
    }
    if ($categoriasInvertidas[401] -ne "Cérebro (CLI)" -or $categoriasInvertidas[402] -ne "Cérebro (CLI)") {
        throw "Falha: raízes sobrepostas mudaram a classificação"
    }
    if ((Obter-Arquitetura "ARM64") -ne "arm64" -or (Obter-Arquitetura "AMD64") -ne "x64") {
        throw "Falha: arquitetura incorreta"
    }

    Write-Host "[AutoTeste] Todos os testes passaram com sucesso (código 0)."
    return $true
}

# -----------------------------------------------------------------------------
# Rotinas de medição no ambiente Windows nativo
# -----------------------------------------------------------------------------

function Obter-ProcessosWmi {
    <#
    .SYNOPSIS
        Obtém snapshot de processos via CIM/WMI para mapear árvores pai-filho.
    #>
    try {
        if (Get-Command -Name Get-CimInstance -ErrorAction SilentlyContinue) {
            return Get-CimInstance -ClassName Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine, CreationDate
        } else {
            return Get-WmiObject -Class Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine, CreationDate
        }
    } catch {
        throw "Falha ao consultar Win32_Process: $($_.Exception.Message)"
    }
}

function Ler-MemoriaProcessoWindows {
    param(
        [int]$ProcessId,
        [object]$InicioEsperado
    )

    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) {
        return @{ encerrado = $true; working_set_mb = 0.0; private_mb = 0.0; inicio_atual = $null }
    }

    $inicioAtual = $null
    try {
        $inicioAtual = $proc.StartTime
    } catch {
        $inicioAtual = $null
    }

    if ($null -eq $InicioEsperado -or $null -eq $inicioAtual) {
        return @{ encerrado = $true; nao_verificavel = $true; working_set_mb = 0.0; private_mb = 0.0; inicio_atual = $inicioAtual }
    }

    # Valida reutilização de PID através da função pura Testar-InicioCompativel
    if (-not (Testar-InicioCompativel -InicioEsperado $InicioEsperado -InicioAtual $inicioAtual)) {
        # PID reutilizado pelo sistema operacional
        return @{ encerrado = $true; nao_verificavel = $true; working_set_mb = 0.0; private_mb = 0.0; inicio_atual = $inicioAtual }
    }

    try {
        $wsMb = [Math]::Round(($proc.WorkingSet64 / 1MB), 2)
        $pbMb = [Math]::Round(($proc.PrivateMemorySize64 / 1MB), 2)
        return @{ encerrado = $false; working_set_mb = $wsMb; private_mb = $pbMb; inicio_atual = $inicioAtual }
    } catch {
        return @{ encerrado = $true; working_set_mb = 0.0; private_mb = 0.0; inicio_atual = $inicioAtual }
    }
}

# -----------------------------------------------------------------------------
# Fluxo Principal
# -----------------------------------------------------------------------------

if ($AutoTeste) {
    try {
        $ok = Executar-AutoTeste
        if ($ok) { exit 0 } else { exit 1 }
    } catch {
        [Console]::Error.WriteLine("[ERRO AutoTeste] $($_.Exception.Message)")
        exit 1
    }
}

# Validações iniciais de parâmetros de medição
if (-not $PidsRaiz -or $PidsRaiz.Count -eq 0) {
    [Console]::Error.WriteLine("Erro: Informe ao menos um PID raiz em -PidsRaiz.")
    exit 1
}

if (-not $Estado) {
    [Console]::Error.WriteLine("Erro: Informe o cenário operacional em -Estado (repouso|conversa|sala|configuracoes).")
    exit 1
}

if ($Amostras -lt 1) {
    $Amostras = 1
}

# 1. Conferência preliminar dos PIDs raiz
$inicioRaizes = @{}
foreach ($rId in $PidsRaiz) {
    $p = Get-Process -Id $rId -ErrorAction SilentlyContinue
    if (-not $p) {
        [Console]::Error.WriteLine("Erro: Processo raiz PID $rId não foi encontrado.")
        exit 1
    }
    try { $inicioRaizes[$rId] = $p.StartTime } catch { $inicioRaizes[$rId] = $null }
}

# Mantém identidades entre amostras para não fundir séries de PIDs reutilizados.
$inicioProcessosConhecido = @{}

# Metadados do host
$windowsVer = [System.Environment]::OSVersion.VersionString
$nomeArquitetura = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
$arquitetura = Obter-Arquitetura $nomeArquitetura
$inicioUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

# 4. Coleta de amostras temporais
$amostrasColetadas = @()

for ($i = 1; $i -le $Amostras; $i++) {
    $processosWmi = @(Obter-ProcessosWmi)
    $raizesValidas = @()
    $raizesNaoVerificaveis = @()
    foreach ($rId in $PidsRaiz) {
        $entrada = $processosWmi | Where-Object { $_.ProcessId -eq $rId } | Select-Object -First 1
        $inicioRaizSnapshot = if ($null -ne $entrada) { Converter-InicioWmi $entrada.CreationDate } else { $null }
        if ($null -ne $inicioRaizSnapshot -and $null -ne $inicioRaizes[$rId] -and (Testar-InicioCompativel -InicioEsperado $inicioRaizes[$rId] -InicioAtual $inicioRaizSnapshot)) {
            $raizAtual = Ler-MemoriaProcessoWindows -ProcessId $rId -InicioEsperado $inicioRaizes[$rId]
            if (-not $raizAtual.encerrado) { $raizesValidas += $rId } else { $raizesNaoVerificaveis += $rId }
        } else {
            $raizesNaoVerificaveis += $rId
        }
    }
    $porPid = @{}
    foreach ($processo in $processosWmi) { $porPid[[int]$processo.ProcessId] = $processo }
    $raizesFiltradas = @()
    foreach ($rId in $raizesValidas) {
        $ancestral = [int]$porPid[$rId].ParentProcessId
        $vistosAncestrais = @{}
        $bloqueada = $false
        while ($porPid.ContainsKey($ancestral) -and -not $vistosAncestrais.ContainsKey($ancestral)) {
            if ($ancestral -in $raizesNaoVerificaveis) { $bloqueada = $true; break }
            $vistosAncestrais[$ancestral] = $true
            $ancestral = [int]$porPid[$ancestral].ParentProcessId
        }
        if ($bloqueada) { $raizesNaoVerificaveis += $rId } else { $raizesFiltradas += $rId }
    }
    $raizesValidas = $raizesFiltradas
    $arvoreResolvida = Resolver-ArvorePura -PidsRaiz $raizesValidas -TabelaProcessos $processosWmi
    $mapaAmostra = @{}
    $ramosRejeitados = @{}

    foreach ($arv in $arvoreResolvida.arvores) {
        foreach ($proc in $arv.processos) {
            $processoId = [int]$proc.Pid
            $inicioSnapshot = Converter-InicioWmi $proc.Inicio
            $inicioEsp = if ($inicioProcessosConhecido.ContainsKey($processoId)) { $inicioProcessosConhecido[$processoId] } else { $inicioSnapshot }
            if ($ramosRejeitados.ContainsKey([int]$proc.Pai) -or $null -eq $inicioSnapshot -or $null -eq $inicioEsp -or -not (Testar-InicioCompativel -InicioEsperado $inicioEsp -InicioAtual $inicioSnapshot)) {
                $ramosRejeitados[$processoId] = $true
                $mapaAmostra[$processoId] = @{ encerrado = $true; nao_verificavel = $true; working_set_mb = 0; private_mb = 0; inicio_atual = $null }
                continue
            }
            $leitura = Ler-MemoriaProcessoWindows -ProcessId $processoId -InicioEsperado $inicioEsp
            $mapaAmostra[$processoId] = $leitura
            if ($leitura.encerrado) { $ramosRejeitados[$processoId] = $true }

            # Conserva a identidade para não juntar PIDs reutilizados nas séries.
            if (-not $leitura.encerrado -and -not $inicioProcessosConhecido.ContainsKey($processoId) -and $null -ne $leitura.inicio_atual) {
                $inicioProcessosConhecido[$processoId] = $leitura.inicio_atual
            }
        }
    }

    $consolidadoAmostra = Consolidar-AmostraPura -Arvores $arvoreResolvida.arvores -MapaMemoria $mapaAmostra
    $consolidadoAmostra["raizes_nao_verificaveis"] = $raizesNaoVerificaveis
    $amostrasColetadas += $consolidadoAmostra

    if ($i -lt $Amostras -and $IntervaloSeg -gt 0) {
        Start-Sleep -Milliseconds ([int]([Math]::Round($IntervaloSeg * 1000)))
    }
}

# 5. Consolidação estatística de todas as amostras coletadas
$ultimaAmostra = $amostrasColetadas[-1]
$resumoEstatistico = Gerar-ResumoSeries -AmostrasColetadas $amostrasColetadas

$saidaFinal = [ordered]@{
    estado       = $Estado
    iniciado_em  = $inicioUtc
    maquina      = [ordered]@{
        windows      = $windowsVer
        arquitetura  = $arquitetura
    }
    amostras     = $amostrasColetadas
    arvores      = $ultimaAmostra.arvores
    componentes  = $ultimaAmostra.componentes
    total        = $ultimaAmostra.total
    resumo       = $resumoEstatistico
}

if ($SaidaJson) {
    try {
        # Profundidade 12 garante serializacao completa sem truncar amostras[] -> arvores[] -> processos[] nem resumo estatistico
        $jsonTexto = $saidaFinal | ConvertTo-Json -Depth 12
        [System.IO.File]::WriteAllText($SaidaJson, $jsonTexto, [System.Text.Encoding]::UTF8)
        Write-Host "Resultado salvo em JSON com sucesso: $SaidaJson"
    } catch {
        [Console]::Error.WriteLine("Erro ao gravar saída JSON: $($_.Exception.Message)")
        exit 1
    }
} else {
    Write-Host "================================================================================"
    Write-Host "  Medição de Memória RAM - Project Vard ($Estado)"
    Write-Host "  Início: $inicioUtc | Amostras: $Amostras (intervalo: ${IntervaloSeg}s)"
    Write-Host "================================================================================"
    Write-Host ""
    $incompleta = $false
    foreach ($amostra in $amostrasColetadas) {
        if ($amostra.raizes_nao_verificaveis.Count -gt 0) { $incompleta = $true }
        foreach ($arv in $amostra.arvores) {
            foreach ($processo in $arv.processos) {
                if ($processo.Contains("nao_verificavel")) { $incompleta = $true }
            }
        }
    }
    if ($incompleta) {
        Write-Host "AVISO: Resultado incompleto; raiz ou processo não verificável foi excluído em pelo menos uma amostra."
    }
    Write-Host "--- Componentes Agregados (Última Amostra) ---"
    $tabelaComps = @()
    foreach ($c in $ultimaAmostra.componentes) {
        $tabelaComps += [PSCustomObject]@{
            Componente     = $c.nome
            Processos      = $c.processos
            "WorkingSet(MB)" = ("{0:N2}" -f $c.working_set_mb)
            "Private(MB)"    = ("{0:N2}" -f $c.private_mb)
        }
    }
    $tabelaComps | Format-Table -AutoSize | Out-String | Write-Host

    Write-Host "--- Total Geral e Dispersão de Amostras ---"
    Write-Host ("Processos ativos : {0}" -f $ultimaAmostra.total.processos)
    Write-Host ("Working Set (MB) : Mediana={0:N2} (Min={1:N2}, Max={2:N2})" -f $resumoEstatistico.total.working_set_mb.mediana, $resumoEstatistico.total.working_set_mb.min, $resumoEstatistico.total.working_set_mb.max)
    Write-Host ("Private Bytes(MB): Mediana={0:N2} (Min={1:N2}, Max={2:N2})" -f $resumoEstatistico.total.private_mb.mediana, $resumoEstatistico.total.private_mb.min, $resumoEstatistico.total.private_mb.max)
    Write-Host "================================================================================"
}

exit 0
