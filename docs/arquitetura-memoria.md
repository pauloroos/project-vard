# Arquitetura e Medição de Memória — Vard 0.10.0

Este documento estabelece a fundamentação técnica sobre consumo de memória, inventário de processos, metodologia de medição, dados empíricos coletados em ambiente Linux e as metas projetadas para validação em ambiente Windows nos quatro cenários operacionais da versão 0.10.0.

---

## 1. Objetivo e Escopo

### O que é memória neste produto
No Project Vard, memória representa o consumo de memória física (RAM do sistema) e virtual alocado e retido pelos processos locais que compõem o ecossistema do assistente:
- **Processos gerenciados diretamente pelo executável hospedeiro (`vard.exe`)**: a aplicação nativa Tauri/Rust, suas janelas WebView2, o serviço HTTP do núcleo Python (`server.py`) e os servidores MCP locais disparados pelo núcleo ou pelo supervisor nativo.
- **Serviços auxiliares e conectores locais**: serviço local de voz (`vard-voz`), serviço de reunião (`vard-reuniao`) e processos de bandeja quando aplicável.
- **Runtimes integrados nas interfaces**: instâncias de motores de inferência em WebAssembly/JavaScript (como o ONNX Runtime Web para o detector de voz Silero VAD).

### O que entra no escopo
1. Memória física privada e compartilhada de cada processo pertencente ao produto (Tauri, WebViews, Python, subprocessos MCP).
2. Memória consumida pela árvore completa do núcleo e pelo runtime de áudio no frontend.
3. Impacto nas transições de ciclo de vida (repouso, conversa ativa, exibição da sala e painel de configurações).
4. Diretrizes de medição fidedignas (distinção matemática e operacional entre RSS, Working Set e Private Bytes).

### O que não entra no escopo
1. **Modelos em VRAM de GPU externa**: pesos de modelos neurais carregados em VRAM dedicada de aceleradores gráficos (por exemplo, modelos LLM no LM Studio, Whisper ou Coqui XTTS rodando em CUDA). O Windows e os drivers de GPU não expõem essa alocação de forma unificada nas métricas de processo do sistema operacional.
2. **Processos de terceiros não gerenciados**: instâncias globais do Google Chrome ou navegadores abertos externamente pelo usuário, servidores LM Studio iniciados fora da supervisão do aplicativo e serviços externos de provedores em nuvem.
3. **Consumo de hardware exclusivo do usuário**: memória de paginação do sistema operacional (swapfile de disco) que não seja atribuível diretamente aos descritores de processo do Vard.

---

## 2. Inventário de Processos

A tabela a seguir inventaria todos os componentes de processo do Project Vard, seus executáveis, comandos observáveis, arquivos responsáveis pela inicialização, condições de subida e encerramento, e o que cada componente retém em memória.

| Componente | Processo / Comando Observável | Arquivo que Inicia | Quando Sobe | Quando Termina | O que Mantém em Memória |
|---|---|---|---|---|---|
| **WebView HUD (Widget)** | `vard.exe` / `msedgewebview2.exe` (processos de renderização, GPU e utilitários) | `src-tauri/src/main.rs`, `src-tauri/tauri.conf.json`, `scripts/windows/vard-modo.ps1` | No arranque da aplicação (`tauri::Builder` cria a janela `hud`). | Na saída do aplicativo (`parar` ou encerramento pelo usuário). | Runtime do WebView2, árvore DOM do HUD, motor V8, buffers WebAudio, VAD (energia ou Silero/ONNX) e cache de áudio fixo. |
| **WebView Configurações** | `msedgewebview2.exe` (janela `configuracoes`) | `src-tauri/src/janelas.rs` (`abrir_configuracoes`) | Ao disparar atalho de configurações ou clicar no ícone de engrenagem. | Ao fechar a janela (tecla Esc, botão fechar ou atalho). | DOM do painel (abas, CSS, formulários), instâncias de teste e conexões temporárias com o núcleo. Liberado ao fechar janela. |
| **WebView Sala** | `msedgewebview2.exe` (janela `sala`) | `src-tauri/src/janelas.rs` (`alternar_sala`) | Ao disparar o atalho da sala (abre tela cheia no monitor configurado). | Ao fechar a sala (tecla Esc ou atalho). Esconde/restaura o widget. | DOM em tela cheia da sala, renderização de canvas/efeitos visuais, estado de presença e eventos sincronizados. |
| **Núcleo Python** | `python.exe -m vard servir` / `uvicorn server:app --host 127.0.0.1 --port 4700` | `src-tauri/src/nucleo.rs`, `src-tauri/src/servicos.rs`, `scripts/windows/vard-modo.ps1` | Na inicialização do ciclo (`Iniciar` do modo ou subida pelo supervisor nativo). | No modo jogo (para liberar recursos) ou no encerramento geral do app (`Parar`). | Interpretador CPython 3.12+, framework FastAPI/Starlette, rotas HTTP, conexões stdio ativas com MCPs locais e estado de sessão. |
| **MCP Mesa** | `python.exe nucleo/mesa_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP Python, módulo `mss` para captura de tela, bindings do Windows UI Automation (`uia.py`), tabelas de apelidos e programas. |
| **MCP Oficina** | `python.exe nucleo/oficina_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, módulo executor de tarefas locais e threads vigia de processos trabalhadores (`vigia.py` com travas `msvcrt`). |
| **MCP Consulta** | `python.exe nucleo/consulta_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, bibliotecas HTTP client (`httpx`), rotinas de pesquisa web, extratores e rotinas de agendamento da manhã. |
| **MCP Memória** | `python.exe nucleo/memoria_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, cliente de integração com o serviço `ai-memory`, cache de sessões e formatação de contexto histórico. |
| **MCP Reunião** | `python.exe nucleo/reuniao_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, cliente HTTP local de controle do serviço de reunião (`127.0.0.1:4720`) e formatação de atas. |
| **MCP Configurações** | `python.exe nucleo/configuracoes_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, parsers TOML/JSON, catálogo compartilhado de vozes, esquemas de painéis e habilidades da Oficina. |
| **Serviço de Voz** | `python.exe -m vard_voz` (`127.0.0.1:4710`) | `scripts/windows/vard-modo.ps1` (`Subir "voz"`), `src-tauri/src/servicos.rs` | No comando `iniciar`, se configurado e instalado no diretório `voz/`. | No modo `jogo` (libera VRAM/RAM) ou no encerramento (`parar`). | FastAPI, Uvicorn, dependências de áudio (`soundfile`, `numpy`) e o motor de síntese selecionado (Kokoro-ONNX ou Coqui XTTS v2). |
| **Serviço de Reunião** | `python.exe -m vard_reuniao` (`127.0.0.1:4720`) | `scripts/windows/vard-modo.ps1` (`Subir "reuniao"`), `src-tauri/src/servicos.rs` | No comando `iniciar`, se configurado e instalado no diretório `reuniao/`. | Antes de entrar no modo `jogo` (após salvar atas pendentes) ou no `parar`. | FastAPI, rotinas de gravação de áudio de loopback e microfone, VAD de reunião e transcritor Whisper/diarizador se instalados. |
| **VAD / ONNX (Silero)** | Executado dentro do worker/processo renderizador do WebView | `src/audio/silero.ts`, `src/audio/vad-selecionavel.ts` | Ao selecionar detector "Silero (local)" nas configurações e abrir áudio. | Quando o detector é trocado para energia, microfone fechado ou app sai. | Módulo WebAssembly do ONNX Runtime Web (`ort-wasm-simd-threaded.wasm` ~11 MB), pesos do modelo (`silero_vad_v5.onnx` ~2.3 MB) e buffers de tensores. |
| **OpenJarvis / LM Studio (Externos)** | `jarvis serve`, `lms server` | Scripts de suporte / inicializados externamente | Opcionais, iniciados conforme fluxo legado de `vard-modo.ps1`. | Descarregados/parados em modo `jogo` e `parar`. | Modelos LLM e pipelines de agentes externos; operam fora do processo do Vard. |

---

## 3. Método de Medição

### Definições de Métricas de Memória

Para eliminar ambiguidades conceituais e garantir comparabilidade rigorosa, o projeto adota os seguintes padrões:

1. **RSS (Resident Set Size — Linux / POSIX)**:
   - Volume de páginas de memória física (RAM) atualmente mapeadas e pertencentes ao espaço de endereçamento do processo, incluindo páginas de código compartilhado e bibliotecas dinâmicas compartilhadas (`.so`).
   - Coletado via `/proc/[pid]/statm` ou `psutil.Process.memory_info().rss`.
   - **Propriedade**: se múltiplos processos compartilham a mesma biblioteca (ex.: CPython e libc), o RSS de cada um computa essa fração compartilhada, de forma que a soma aritmética simples dos RSS pode exceder a memória física real alocada pelo conjunto.

2. **Working Set (Windows)**:
   - Equivalente do Windows ao Resident Set Size: quantidade de memória física (RAM) atualmente alocada para as páginas do processo.
   - Divide-se em:
     - **Working Set Total**: páginas privadas + páginas compartilhadas ativas.
     - **Working Set Privado**: páginas de memória física em uso exclusivo pelo processo.
   - Sob pressão de memória do sistema operacional, o Windows reduz dinamicamente o Working Set enviando páginas para o arquivo de paginação ou lista de espera (*standby list*).

3. **Private Bytes (Commit Charge Privado — Windows)**:
   - Quantidade total de memória virtual alocada que o processo reservou e comprometeu exclusivamente para si, que não pode ser compartilhada com outros processos e que exige garantia de espaço de armazenamento (na RAM ou no arquivo de paginação se sofrer *page out*).
   - Métrica primária para detectar vazamentos (*leaks*) de memória em código nativo, V8 e CPython.

### Distinção entre Medição e Estimativa

- **Medição**: Valor numérico obtido diretamente pela instrumentação empírica de um processo real em execução no sistema operacional do host de teste, registrado com PID, arquitetura, kernel, comando executado e timestamp.
- **Estimativa / Meta**: Projeção matemática fundamentada nos limites conhecidos dos runtimes (tamanho de binários, overhead do motor Blink/Chromium, heap baseline do V8, working set mínimo do Edge WebView2) somados às medições de código comum e folgas de segurança calculadas. **Metas nunca são apresentadas como medições concluídas**.

### Por que o Linux não comprova WebView2 e Windows
1. **Diferença de motor e subsistema gráfico**: No Linux não existe o Microsoft Edge WebView2 (motor Edge/Chromium integrado ao Windows com hooks de composição DWM e aceleração DirectX). As janelas do Tauri no Linux utilizariam WebKitGTK se compiladas para desktop Linux, apresentando alocação de heap, consumo de fontes e pipeline de GPU totalmente distintos.
2. **Bibliotecas de baixo nível específicas do Windows**: O módulo de bloqueio de arquivos concorrentes `msvcrt` (usado por `nucleo/vard/vigia.py`), o subsistema UI Automation do Windows (`uia.py`) e chamadas de API Win32 (`user32.dll` em `janelas.rs`) são exclusivos do Windows. No Linux, módulos que dependem de `msvcrt` não carregam em ambiente de produção sem emulação.
3. **Gestão de memória virtual do SO**: O modelo de alocação de páginas do Linux (overcommit agressivo, lazy paging, *fork-with-copy-on-write*) difere fundamentalmente do subsistema de memória do Windows NT (comprometimento estrito de commit charge e working set trims periódicos).

### Procedimento Experimental Adotado no Linux
- **Ambiente isolado**: Uso de diretórios temporários exclusivos em `/tmp/vard-med-*` para `VARD_DADOS` e `VARD_CONFIG`, assegurando ausência de dados de usuários, tokens ou chaves reais.
- **Porta não conflitante**: Seleção da porta livre `4880` (verificada previamente para evitar conflito com 4700, 4710, 4720, 8000, 1420).
- **Grupos de processo independentes**: Todo subprocesso foi lançado com `os.setsid` / `preexec_fn` para formação de grupo de processo isolado (PGID), garantindo que `os.killpg(pgid, signal.SIGTERM)` encerre a árvore completa sem deixar órfãos.
- **Protocolo de amostragem temporal**:
  - Espera mínima de 25 segundos após subida para estabilização completa do heap CPython e dos loops de eventos.
  - Coleta de 3 amostras consecutivas com intervalo de 3 segundos.
  - Relato explícito da mediana e da faixa de dispersão (min-max).

---

## 4. Medições Linux (Medidas)

As medições foram coletadas nesta máquina no dia **02 de novembro de 2026**.

**Dados do Host de Medição**:
- **Sistema Operacional**: Linux
- **Arquitetura**: `aarch64`
- **Versão do Kernel**: `6.17.0-1016-oracle`
- **Ambiente Python**: CPython 3.13.15 virtualenv (`nucleo/.venv`)
- **Runtime Node.js**: Node.js v22+

### 4.1. Medição dos 6 Servidores MCP Locais (Isolados)

Cada servidor MCP foi executado via seu arquivo de entrada `nucleo/<nome>_mcp.py`, mantendo a entrada padrão (*stdin*) aberta via pipe, com diretório de dados limpo em `/tmp/vard-med-mcp-<nome>-*`.

| Servidor MCP | Status no Linux | Amostras RSS (t=25s, 28s, 31s) | Mediana RSS | Faixa RSS | Observações / Motivo de Falha |
|---|---|---|---|---|---|
| `mesa_mcp.py` | **OK** | 69.3 MB, 69.3 MB, 69.3 MB | **69.3 MB** | [69.3 - 69.3] MB | Carregou FastAPI/MCP, MSS e módulos de dados. Subiu e manteve-se estável. |
| `oficina_mcp.py` | **Falha de Import** | — | — | — | `ModuleNotFoundError: No module named 'msvcrt'`. Depende de trava de arquivo Win32 via `msvcrt` em `vard/vigia.py`. |
| `consulta_mcp.py` | **Falha de Import** | — | — | — | `ModuleNotFoundError: No module named 'msvcrt'`. Depende de `vard/vigia.py` importado em `consulta_mcp.py`. |
| `memoria_mcp.py` | **OK** | 67.8 MB, 67.8 MB, 67.8 MB | **67.8 MB** | [67.8 - 67.8] MB | Carregou rotinas MCP e cliente de protocolo. |
| `reuniao_mcp.py` | **OK** | 68.1 MB, 68.1 MB, 68.1 MB | **68.1 MB** | [68.1 - 68.1] MB | Carregou cliente de controle da reunião. |
| `configuracoes_mcp.py` | **OK** | 68.7 MB, 68.7 MB, 68.7 MB | **68.7 MB** | [68.7 - 68.7] MB | Carregou esquemas de configuração e catálogo de vozes. |

*Nota técnica*: Os 4 MCPs que sobem no Linux apresentam consumo praticamente idêntico em repouso (~68 a 69 MB), evidenciando que a maior parte da memória em repouso decorre do carregamento do runtime CPython, Pydantic, Starlette e do SDK MCP.

### 4.2. Medição da Árvore Completa do Núcleo em Repouso

O núcleo foi iniciado via Uvicorn na porta `4880` com `lifespan` completo:
```bash
/home/orca/orca/workspaces/project-vard/vard010-memoria/nucleo/.venv/bin/uvicorn \
  server:app --host 127.0.0.1 --port 4880 --timeout-graceful-shutdown 2
```
Durante a inicialização do `lifespan`, o núcleo consulta `servidores_locais()` e inicia cada MCP disponível via stdio. Como `oficina_mcp.py` e `consulta_mcp.py` falham de imediato no Linux devido à ausência de `msvcrt`, o núcleo registra o aviso e mantém ativos os 4 MCPs compatíveis (`mesa`, `memoria`, `reuniao`, `configuracoes`).

Amostras coletadas após 25 segundos de estabilização:
- Amostra 1 (t=25s): Núcleo Pai = 54.7 MB | Árvore Total = 329.9 MB
- Amostra 2 (t=28s): Núcleo Pai = 54.7 MB | Árvore Total = 329.9 MB
- Amostra 3 (t=31s): Núcleo Pai = 54.7 MB | Árvore Total = 329.9 MB

**Resultado Consolidado em Repouso**:
- **Núcleo sozinho (Processo Pai — Uvicorn/FastAPI)**: **54.7 MB** (faixa: 54.7 – 54.7 MB)
- **Árvore Total (Núcleo + 4 MCPs ativos)**: **329.9 MB** (faixa: 329.9 – 329.9 MB)

**Detalhamento da Árvore por Processo**:
- PID 40550 (`uvicorn server:app` — Pai): **54.7 MB**
- PID 40552 (`python nucleo/mesa_mcp.py` — Filho): **69.7 MB**
- PID 40557 (`python nucleo/memoria_mcp.py` — Filho): **68.1 MB**
- PID 40563 (`python nucleo/reuniao_mcp.py` — Filho): **68.3 MB**
- PID 40579 (`python nucleo/configuracoes_mcp.py` — Filho): **69.2 MB**
- *Soma dos componentes individuais*: 54.7 + 69.7 + 68.1 + 68.3 + 69.2 = **330.0 MB** (concordância com 329.9 MB).

### 4.3. Árvore do Núcleo Durante Uso Leve (Chamadas HTTP)

Disparo de requisições HTTP locais contra o servidor em execução:
1. **Requisição `GET /saude`**:
   - Resposta: `{"ok":true,"versao":"0.9.9","pid":40550}` (Status 200 OK).
   - Núcleo Pai após a chamada: **55.8 MB** (+1.1 MB).
   - Árvore Total após a chamada: **331.0 MB** (+1.1 MB).
2. **Requisição `GET /recursos`**:
   - A rota dispara a coleta síncrona/concorrente do monitor `vard.recursos`, iterando processos psutil e executando varreduras de árvore.
   - Resposta: Status 200 OK com payload estruturado dos componentes.
   - Núcleo Pai após a chamada: **60.5 MB** (+5.8 MB sobre o repouso original).
   - Árvore Total após a chamada: **335.8 MB** (+5.9 MB sobre o repouso original).

### 4.4. Custo de Memória do Runtime ONNX e Modelo Silero VAD (Node.js)

Para isolar o custo exato do runtime de inteligência artificial de áudio sem depender do WebView2 ou de dispositivo de captura física de áudio, executou-se um teste direto no runtime JavaScript com os assets locais empacotados (`node_modules/@ricky0123/vad-web` e `node_modules/onnxruntime-web`):

- **Baseline Node.js RSS**: 41.5 MB
- **Após carregar biblioteca (`require('onnxruntime-web')`)**: 48.4 MB (acréscimo de **6.9 MB**)
- **Após inicializar a sessão de inferência (`InferenceSession.create('silero_vad_v5.onnx')`)**: 171.8 MB (acréscimo de **123.4 MB**)
- **Custo Total Líquido do VAD Silero + ONNX Runtime**: **130.4 MB**

*Conclusão*: O carregamento do modelo Silero v5 em WebAssembly/ONNX Runtime no frontend introduz uma sobrecarga líquida de aproximadamente **130 MB** de memória na janela do widget.

### 4.5. Componentes Não Medidos no Linux e Justificativas Rigorosas

| Componente | Status | Motivo Técnico Exato |
|---|---|---|
| **Janelas WebView2 (HUD, Configurações, Sala)** | Não medido | O Edge WebView2 é um componente nativo exclusivo do Windows (baseado no motor Edge/Chromium e runtime Evergreen). O ambiente Linux utilizado para testes em servidor não possui display server X11/Wayland instalado nem suporte ao WebView2. |
| **Serviço de Voz Real (`vard-voz` / XTTS v2)** | Não medido | A suíte completa de síntese local XTTS v2 depende de pacotes compilados CUDA, PyTorch para arquitetura específica (`torch==2.11.0+cu128`) e arquivos de pesos pré-treinados (~1.8 GB). As restrições do job vedam download de modelos e instalação de bibliotecas pesadas. |
| **Serviço de Reunião Real (`vard-reuniao`)** | Não medido | O serviço de reunião requer dispositivos de áudio de captura do sistema operacional (WASAPI Loopback no Windows para capturar som do sistema e microfone simultâneo), além de modelos Whisper e PyTorch ausentes neste ambiente Linux. |
| **MCP Oficina e MCP Consulta** | Não medido em regime | Falha de importação no Linux por ausência do módulo interno de plataforma `msvcrt` (usado por `vard/vigia.py` para sincronização com travas Win32 em disco). |

---

## 5. Metas Windows

Com base nos dados empíricos apurados no Linux (núcleo ~55 MB, cada MCP ~69 MB, ONNX Silero ~130 MB) e no histórico de referências do WebView2 no Windows (processo base do Evergreen WebView2 consome tipicamente ~120 MB em repouso por janela opaca e ~150–180 MB em janela transparente com aceleração DirectComposition), estabelecem-se as seguintes metas de **Working Set (WS)** e **Private Bytes (PB)**.

### Tabela de Metas por Cenário Operacional (Windows)

| Componente | 1. Repouso (Ocioso) | 2. Conversa Ativa | 3. Sala Aberta | 4. Configurações Abertas | Justificativa Técnica da Meta |
|---|---|---|---|---|---|
| **HUD (Widget WebView2)** | WS: ≤ 140 MB<br>PB: ≤ 110 MB | WS: ≤ 180 MB<br>PB: ≤ 150 MB | WS: ≤ 90 MB<br>PB: ≤ 75 MB | WS: ≤ 140 MB<br>PB: ≤ 110 MB | Em repouso com VAD de energia, o HUD opera com DOM estático. Na conversa, buffers de áudio elevam o uso. Na sala, o widget é **escondido** (`hide`), permitindo ao SO realizar *trim* do working set. |
| **Sobrecarga Silero VAD (se ativo no HUD)** | WS: +120 MB<br>PB: +135 MB | WS: +135 MB<br>PB: +140 MB | WS: +120 MB<br>PB: +135 MB | WS: +120 MB<br>PB: +135 MB | Custo medido no runtime ONNX Web (~130 MB). Caso o usuário opte por energia, essa folga é integralmente poupada. |
| **Janela de Configurações** | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | WS: ≤ 110 MB<br>PB: ≤ 95 MB | Janela só existe quando aberta. Ao fechar (`close`), o processo WebView correspondente é destruído e a memória é liberada. |
| **Janela da Sala** | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | WS: ≤ 160 MB<br>PB: ≤ 130 MB | *Fechada*:<br>0 MB | Tela cheia decorada com canvas. Destruída ao fechar (`Destroyed` restaura o HUD). |
| **Núcleo Python** | WS: ≤ 60 MB<br>PB: ≤ 50 MB | WS: ≤ 80 MB<br>PB: ≤ 70 MB | WS: ≤ 70 MB<br>PB: ≤ 60 MB | WS: ≤ 70 MB<br>PB: ≤ 60 MB | Medido em Linux: 54.7 MB em repouso e 60.5 MB após coleta de recursos. A meta estabelece folga de 10–20 MB para buffers de streaming SSE. |
| **MCPs Locais (6 processos stdio)** | WS: ≤ 420 MB<br>PB: ≤ 390 MB | WS: ≤ 460 MB<br>PB: ≤ 420 MB | WS: ≤ 420 MB<br>PB: ≤ 390 MB | WS: ≤ 420 MB<br>PB: ≤ 390 MB | Medido em Linux: ~68–70 MB por MCP. Para os 6 processos (`mesa`, `oficina`, `consulta`, `memoria`, `reuniao`, `configuracoes`), 6 × 70 MB = 420 MB. |
| **Serviço de Voz (Kokoro / TTS)** | WS: ≤ 120 MB<br>PB: ≤ 110 MB | WS: ≤ 160 MB<br>PB: ≤ 150 MB | WS: ≤ 120 MB<br>PB: ≤ 110 MB | WS: ≤ 120 MB<br>PB: ≤ 110 MB | Motor Kokoro-ONNX leve (82M int8). Se XTTS v2 for adotado, alocação sobe para VRAM da GPU, mantendo baseline de host ~300 MB. |
| **Serviço de Reunião** | *Ocioso*:<br>WS: ≤ 50 MB | *Ocioso*:<br>WS: ≤ 50 MB | *Ocioso*:<br>WS: ≤ 50 MB | *Ocioso*:<br>WS: ≤ 50 MB | Em repouso apenas escuta rota `/status`. Se ativa (gravação e diarização), aloca até 250 MB na RAM. |
| **Total Global do Produto (sem Silero)** | **WS: ≤ 670 MB**<br>**PB: ≤ 600 MB** | **WS: ≤ 880 MB**<br>**PB: ≤ 790 MB** | **WS: ≤ 740 MB**<br>**PB: ≤ 655 MB** | **WS: ≤ 780 MB**<br>**PB: ≤ 695 MB** | Somatório de todos os componentes locais em regime operacional estável. |
| **Total Global do Produto (com Silero VAD)** | **WS: ≤ 790 MB**<br>**PB: ≤ 735 MB** | **WS: ≤ 1015 MB**<br>**PB: ≤ 930 MB** | **WS: ≤ 860 MB**<br>**PB: ≤ 790 MB** | **WS: ≤ 900 MB**<br>**PB: ≤ 830 MB** | Somatório incluindo o runtime WASM/ONNX do Silero VAD no HUD. |

---

## 6. Antes e Depois por Componente

Esta seção consolida o baseline atual, a meta projetada para a versão 0.10.0, as oportunidades de redução de memória já identificadas no código e as frentes responsáveis por eventuais alterações.

| Componente | Baseline Atual | Meta 0.10.0 | Reduções Seguras Identificadas | Responsabilidade / Arquivos |
|---|---|---|---|---|
| **Arquitetura dos MCPs Locais** | **~420 MB** (6 processos CPython independentes consumindo ~70 MB cada um). | **≤ 110 MB** (em consolidação futura de processo único) ou **≤ 420 MB** (em stdio isolado). | **Diagnóstico**: O modelo stdio atual lança 6 processos Python paralelos via `nucleo/vard/segredos.py` (`servidores_locais`), onde cada processo carrega uma cópia completa do runtime Python, Pydantic, Starlette e SDK MCP (~70 MB).<br>**Oportunidade Segura**: No Vard 0.9.4 leve, já houve a eliminação de `uv run` por chamada (poupando 15 subprocessos intermediários). Na branch 0.10.0, unificar o despacho interno das ferramentas dentro do processo do núcleo ou criar um MCP consolidador de entrada única reduziria ~300 MB de RAM. *Nota de Conflito*: Como o gerenciador de ferramentas do cérebro próprio (`nucleo/vard/cerebro/ferramentas.py`) e a integração do OpenJarvis dependem do contrato stdio individual, a unificação deve ser coordenada entre as frentes de ferramentas e arquitetura. | Arquivos: `nucleo/vard/segredos.py`, `nucleo/server.py`, `nucleo/*_mcp.py`. Responsável: Frente de Arquitetura e Ferramentas. |
| **Núcleo Python (Uvicorn / FastAPI)** | **~55–60 MB** (medido: 54.7 MB repouso, 60.5 MB pós-rotas). | **≤ 60 MB** em repouso. | O Uvicorn opera de forma enxuta. Reduções adicionais incluem o descarregamento (*lazy import*) de módulos administrativos (`vard/telegram_migracao.py`, rotas de pacotes) somente quando acionados. | Arquivos: `nucleo/server.py`. Responsável: Frente de Núcleo. |
| **Janelas WebView2 (HUD / Config / Sala)** | **~150–250 MB** por janela ativa. | **Redução de 30% a 50%** no consumo ocioso da Sala e Configurações. | **Padrão implementado**: A janela de configurações e a sala já são destruídas ao fechar (`janelas.rs`), impedindo acúmulo de processos inativos. O HUD é escondido (`hide`) quando a sala abre.<br>**Oportunidade**: Interrupção de *requestAnimationFrame*, suspensão de timers CSS e parada de animações canvas quando a janela não estiver visível (conforme spec 0.10.0). | Arquivos: `src-tauri/src/janelas.rs`, `src/main.ts`, `src/hud/sala.ts`. Responsável: Frente de Interface (T002). |
| **Detecção de Voz (VAD Silero vs Energia)** | Silero VAD on-demand: **~130 MB** líquido adicionado. | **Zero impacto adicional** quando em modo Energia. | O carregamento sob demanda (`src/audio/vad-selecionavel.ts` e `src/audio/silero.ts`) só instancia o ONNX Runtime Web e aloca tensores caso o usuário selecione explicitamente "Silero (local)". Destruição do modelo (`destruir()`) ao trocar para energia libera o WebAssembly e o contexto de inferência. | Arquivos: `src/audio/silero.ts`, `src/audio/vad-selecionavel.ts`. Responsável: Frente de Voz / Interface. |
| **Serviço de Voz Local** | Variável: Kokoro (~100 MB RAM) ou XTTS v2 (~3 GB RAM se carregado em processo compartilhado). | Kokoro: **≤ 120 MB RAM**.<br>XTTS v2: isolamento estrito de processo. | Em `voz/vard_voz/servidor.py`, a descarga de XTTS dentro do mesmo processo não devolve RAM ao sistema operacional. O isolamento do motor Kokoro em ONNX CPU garante estabilidade e baixo consumo. | Arquivos: `voz/vard_voz/servidor.py`. Responsável: Frente de Voz. |

---

## 7. Limitações e Pendências

1. **Validação Específica do Sistema Operacional Windows**:
   - As medições realizadas neste documento foram conduzidas em ambiente Linux (`aarch64`, kernel 6.17). Elas atestam a integridade matemática e o consumo basal do CPython, do servidor Uvicorn, dos servidores MCP compatíveis e do runtime WebAssembly ONNX.
   - A prova real do Edge WebView2 (processos `msedgewebview2.exe`), das janelas nativas Tauri, da comunicação IPC Rust-WebView2 e dos módulos que dependem de `msvcrt` (`oficina_mcp.py` e `consulta_mcp.py`) depende de execução no sistema operacional Windows.

2. **Variação por Hardware e Arquitetura**:
   - A arquitetura testada foi ARM64 (`aarch64`). Em máquinas x86_64 / x64 Windows, os tamanhos de ponteiros e o alinhamento de binários compilados (MSVC) podem gerar pequenas variações nos consumos de heap e RSS/Working Set (~5% a 10%).

3. **Dependência de Modelos Neurais Carregados**:
   - O consumo do serviço de voz varia radicalmente conforme o motor selecionado:
     - Kokoro-82M int8: consumo previsível de ~100–120 MB de RAM.
     - Coqui XTTS v2: requer alocação de tensores pesados de PyTorch, operando idealmente em VRAM de GPU dedicada para não concorrer com a memória RAM do sistema.
   - O LM Studio aloca a quase totalidade do modelo LLM em VRAM dedicada quando configurado com `--gpu max`. Entretanto, contextos elevados (ex.: 128k/256k tokens) alocam buffers de atenção na memória do sistema caso a VRAM seja excedida.

---

## 8. Reprodução

### 8.1. Reprodução das Medições no Linux

Para reproduzir os testes empíricos documentados na seção 4, execute os seguintes passos a partir da raiz do repositório:

1. **Verificação de portas livres**:
   ```bash
   python3 -c "import socket; s = socket.socket(); exit(s.connect_ex(('127.0.0.1', 4880)) == 0)"
   ```
   (Se o código de saída for 0, a porta está em uso; caso contrário, está livre).

2. **Execução do script de medição individual e de árvore**:
   Crie um script temporário fora do repositório (ex.: `/tmp/medir_memoria.py`) com isolamento via `setsid` e diretórios limpos em `/tmp`:
   ```bash
   python3 /tmp/medir_memoria.py
   ```

3. **Comando manual para medição direta de um MCP (ex.: Mesa)**:
   ```bash
   export VARD_DADOS="/tmp/vard-med-repro/dados"
   export VARD_CONFIG="/tmp/vard-med-repro/config"
   mkdir -p "$VARD_DADOS" "$VARD_CONFIG"
   
   # Inicia em grupo de processos isolado
   ./nucleo/.venv/bin/python nucleo/mesa_mcp.py &
   PID_MCP=$!
   
   # Aguarda 25 segundos
   sleep 25
   
   # Coleta RSS em MB
   ps -o pid,rss,comm -p $PID_MCP | awk 'NR>1 {printf "PID %s (%s): %.1f MB\n", $1, $3, $2/1024}'
   
   # Encerramento limpo do processo
   kill -TERM $PID_MCP
   rm -rf /tmp/vard-med-repro
   ```

4. **Medição do ONNX Runtime Web + Silero V5 em Node.js**:
   ```bash
   node -e "
   const fs = require('fs');
   const baseline = parseInt(fs.readFileSync('/proc/self/status','utf8').match(/VmRSS:\s+(\d+)/)[1])/1024;
   const ort = require('onnxruntime-web');
   (async () => {
     await ort.InferenceSession.create('node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx');
     const final = parseInt(fs.readFileSync('/proc/self/status','utf8').match(/VmRSS:\s+(\d+)/)[1])/1024;
     console.log('Delta ONNX Silero:', (final - baseline).toFixed(1), 'MB');
   })();
   "
   ```

### 8.2. Roteiro do Script de Medição no Windows (`scripts/windows/medir-ram.ps1`)

Para o trabalho subsequente no Windows (planejado no job T001-C), o script PowerShell deverá inspecionar os processos por PID registrado e por árvore hierárquica, utilizando contadores nativos de performance:

```powershell
# Exemplo de comando PowerShell para medição por PID e árvore de processos no Windows
param([string]$Cenario = "repouso")

# 1. Localiza a raiz do Vard (vard.exe ou processos registrados em pids/)
$PidsDir = Join-Path $env:LOCALAPPDATA "rdl-vard\pids"
Write-Host "=== Medição de Memória do Project Vard — Cenário: $Cenario ==="

function Obter-MetricasProcesso($ProcessId) {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    
    # Working Set e Private Bytes em MB
    $wsMb = [Math]::Round($proc.WorkingSet64 / 1MB, 1)
    $pbMb = [Math]::Round($proc.PrivateMemorySize64 / 1MB, 1)
    
    return [PSCustomObject]@{
        PID          = $proc.Id
        Nome         = $proc.ProcessName
        WorkingSetMB = $wsMb
        PrivateBytesMB = $pbMb
    }
}

# Coleta de todos os processos filhos da árvore
$vardProc = Get-Process -Name "vard" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vardProc) {
    Write-Host "Processo principal: PID $($vardProc.Id)"
    Obter-MetricasProcesso $vardProc.Id | Format-Table -AutoSize
}

# Varredura dos PIDs registrados em pids/ (ponte, voz, reuniao, etc.)
if (Test-Path $PidsDir) {
    Get-ChildItem -Path $PidsDir -Filter "*.pid" | ForEach-Object {
        $conteudo = (Get-Content $_.FullName -Raw).Trim().Split("|")
        $pidNum = [int]$conteudo[0]
        $metrica = Obter-MetricasProcesso $pidNum
        if ($metrica) {
            Write-Host "Serviço ($($_.BaseName)): PID $pidNum"
            $metrica | Format-Table -AutoSize
        }
    }
}
```
Este script permite correlacionar diretamente os limites de Working Set e Private Bytes com as metas descritas na seção 5 deste documento durante as provas de homologação em ambiente Windows.
