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
| **Núcleo Python** | Release: `python.exe -I -X utf8 -m vard servir`<br>Dev nativo: `uv run --project nucleo --frozen python -X utf8 -m vard servir`<br>Dev legado/script: `uv run --no-sync uvicorn server:app --host 127.0.0.1 --port 4700 --timeout-graceful-shutdown 2` (a partir de `nucleo/`) | `src-tauri/src/nucleo.rs`, `scripts/windows/vard-modo.ps1` | Na inicialização do ciclo (`Iniciar` do modo ou subida pelo supervisor nativo). | No modo jogo (para liberar recursos) ou no encerramento geral do app (`Parar`). | Interpretador CPython 3.13 (`>=3.13,<3.14`), framework FastAPI/Starlette, rotas HTTP, conexões stdio ativas com MCPs locais e estado de sessão. |
| **MCP Mesa** | `python.exe nucleo/mesa_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP Python, módulo `mss` para captura de tela, bindings do Windows UI Automation (`uia.py`), tabelas de apelidos e programas. |
| **MCP Oficina** | `python.exe nucleo/oficina_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, módulo executor de tarefas locais e threads vigia de processos trabalhadores (`vigia.py` com travas `msvcrt`). |
| **MCP Consulta** | `python.exe nucleo/consulta_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, bibliotecas HTTP client (`httpx`), rotinas de pesquisa web, extratores e rotinas de agendamento da manhã. |
| **MCP Memória** | `python.exe nucleo/memoria_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, cliente MCP HTTP do ai-memory, leitura de `memoria.toml` e formatação de resultados de busca/leitura/gravação. |
| **MCP Reunião** | `python.exe nucleo/reuniao_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, cliente HTTP local de controle do serviço de reunião (`127.0.0.1:4720`) e formatação de atas. |
| **MCP Configurações** | `python.exe nucleo/configuracoes_mcp.py` (stdio) | `nucleo/server.py` (`lifespan`), `nucleo/vard/segredos.py` (`servidores_locais`) | Na inicialização do lifespan do núcleo ou sob demanda por CLI externa. | Junto com o núcleo (`fechar_tudo`) ou ao encerrar a sessão da CLI. | Servidor MCP, parsers TOML/JSON, catálogo compartilhado de vozes, esquemas de painéis e habilidades da Oficina. |
| **Serviço de Voz** | `python.exe -m vard_voz` (`127.0.0.1:4710`) | `src-tauri/src/instalacao.rs` (`descritor_voz`), `src-tauri/src/servicos.rs` (supervisor nativo), `scripts/windows/vard-modo.ps1` (`Subir "voz"`) | No comando `iniciar`, se configurado e instalado no diretório `voz/`. | No modo `jogo` (libera VRAM/RAM) ou no encerramento (`parar`). | FastAPI, Uvicorn, dependências de áudio (`soundfile`, `numpy`) e o motor de síntese selecionado (Kokoro-ONNX ou Coqui XTTS v2). |
| **Serviço de Reunião** | `python.exe -m vard_reuniao` (`127.0.0.1:4720`) | `src-tauri/src/instalacao.rs` (`descritor_reuniao`), `src-tauri/src/servicos.rs` (supervisor nativo), `scripts/windows/vard-modo.ps1` (`Subir "reuniao"`) | No comando `iniciar`, se configurado e instalado no diretório `reuniao/`. | Antes de entrar no modo `jogo` (após salvar atas pendentes) ou no `parar`. | FastAPI, rotinas de gravação de áudio de loopback e microfone, VAD de reunião e transcritor Whisper/diarizador se instalados. |
| **VAD / ONNX (Silero)** | Executado dentro do worker/processo renderizador do WebView | `src/audio/silero.ts`, `src/audio/vad-selecionavel.ts` | Ao selecionar detector "Silero (local)" nas configurações e abrir áudio. | Quando o detector é trocado para energia, microfone fechado ou app sai. | Módulo WebAssembly do ONNX Runtime Web (`ort-wasm-simd-threaded.wasm` ~11 MB), pesos do modelo Silero VAD (ONNX) (~2.3 MB) e buffers de tensores. |
| **OpenJarvis (Opcional / Externo)** | `jarvis serve --agent orchestrator` (`src-tauri/src/instalacao.rs`) | `src-tauri/src/instalacao.rs` (`descritor_openjarvis`), `scripts/windows/vard-modo.ps1` | Opcional, se configurado em `InstalacaoConfig` e com repositório presente. | Descarregado/parado em modo `jogo` e `parar`. | Processo externo Python de orquestração de agentes. Não inclui o LM Studio (que é executado externamente pelo usuário e não é gerenciado nem iniciado pelo Project Vard). |

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

O núcleo foi iniciado via Uvicorn na porta `4880` com `lifespan` completo (a partir do diretório `nucleo/`, onde o módulo `server:app` reside):
```bash
cd nucleo
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 4880 --timeout-graceful-shutdown 2
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
- *Soma dos componentes individuais*: 54.7 + 69.7 + 68.1 + 68.3 + 69.2 = **330.0 MB** (a diferença de 0.1 MB em relação aos 329.9 MB medidos no total decorre exclusivamente de arredondamento individual de cada processo na conversão de KB para MB).

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

### 4.4. Custo de Memória do Runtime ONNX e Modelo Silero VAD (Node.js como Proxy)

Para isolar o custo do runtime de inteligência artificial de áudio sem depender do WebView2 ou de dispositivo de captura física de áudio, executou-se um teste direto no runtime JavaScript Node.js com os assets locais empacotados (`node_modules/@ricky0123/vad-web` e `node_modules/onnxruntime-web`) como medição proxy:

- **Baseline Node.js RSS**: 41.5 MB
- **Após carregar biblioteca (`require('onnxruntime-web')`)**: 48.4 MB (acréscimo de **6.9 MB**)
- **Após inicializar a sessão de inferência do modelo Silero VAD (ONNX)**: 171.8 MB (acréscimo de **123.4 MB**)
- **Custo Total Líquido do VAD Silero + ONNX Runtime (Proxy Node.js)**: **130.4 MB**

*Conclusão e ressalva metodológica*: O carregamento do modelo Silero VAD (ONNX) em WebAssembly/ONNX Runtime no Node.js introduz uma sobrecarga líquida medida de aproximadamente **130 MB** de RSS. No entanto, o teste em Node.js constitui um proxy de engenharia; no Edge WebView2 (V8 e Blink sob Windows, com aceleração DirectComposition e políticas próprias de gestão de memória), o consumo real pode diferir. A confirmação do valor exato em ambiente de produção permanece como pendência de medição no Windows com o medidor nativo.

### 4.5. Componentes Não Medidos no Linux e Justificativas Rigorosas

| Componente | Status | Motivo Técnico Exato |
|---|---|---|
| **Janelas WebView2 (HUD, Configurações, Sala)** | Não medido | O Edge WebView2 é um componente nativo exclusivo do Windows (baseado no motor Edge/Chromium e runtime Evergreen). O ambiente Linux utilizado para testes em servidor não possui display server X11/Wayland instalado nem suporte ao WebView2. |
| **Serviço de Voz Real (`vard-voz` / XTTS v2)** | Não medido | A suíte completa de síntese local XTTS v2 depende de pacotes compilados CUDA, PyTorch para arquitetura específica (`torch==2.11.0+cu128`) e arquivos de pesos pré-treinados (~1.8 GB). As restrições de execução e escopo da medição vedam download de modelos e instalação de bibliotecas pesadas de terceiros. |
| **Serviço de Reunião Real (`vard-reuniao`)** | Não medido | O serviço de reunião requer dispositivos de áudio de captura do sistema operacional (WASAPI Loopback no Windows para capturar som do sistema e microfone simultâneo), além de modelos Whisper e PyTorch ausentes neste ambiente Linux. |
| **MCP Oficina e MCP Consulta** | Não medido em regime | Falha de importação no Linux por ausência do módulo interno de plataforma `msvcrt` (usado por `vard/vigia.py` para sincronização com travas Win32 em disco). |

---

## 5. Metas Windows

Com base nos dados empíricos apurados no Linux (núcleo ~55 MB, cada MCP ~69 MB, ONNX Silero ~130 MB como proxy Node.js) e em estimativas de engenharia preliminares para o Evergreen WebView2 no Windows (faixa provisória estimada de 100–150 MB por janela opaca e 140–180 MB para janela transparente com aceleração DirectComposition; trata-se de estimativa de engenharia, a validar com o medidor Windows; não é medição empírica), estabelecem-se as seguintes metas de **Working Set (WS)** e **Private Bytes (PB)**.

### Tabela de Metas por Cenário Operacional (Windows)

| Componente | 1. Repouso (Ocioso) | 2. Conversa Ativa | 3. Sala Aberta | 4. Configurações Abertas | Justificativa Técnica da Meta |
|---|---|---|---|---|---|
| **HUD (Widget WebView2)** | WS: ≤ 140 MB<br>PB: ≤ 110 MB | WS: ≤ 180 MB<br>PB: ≤ 150 MB | WS: ≤ 90 MB<br>PB: ≤ 75 MB | WS: ≤ 140 MB<br>PB: ≤ 110 MB | Em repouso com VAD de energia, o HUD opera com DOM estático. Na conversa, buffers de áudio elevam o uso. Na sala, o widget é **escondido** (`hide`), permitindo ao SO realizar *trim* do working set. |
| **Sobrecarga Silero VAD (se ativo no HUD)** | WS: +120 MB<br>PB: +135 MB | WS: +135 MB<br>PB: +140 MB | WS: +120 MB<br>PB: +135 MB | WS: +120 MB<br>PB: +135 MB | Custo medido no proxy ONNX Web / Node.js (~130 MB). Caso o usuário opte por energia, essa sobrecarga não existe. |
| **Janela de Configurações** | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | WS: ≤ 110 MB<br>PB: ≤ 95 MB | Janela só existe quando aberta. Ao fechar (`close`), o processo WebView correspondente é destruído e a memória é liberada. |
| **Janela da Sala** | *Fechada*:<br>0 MB | *Fechada*:<br>0 MB | WS: ≤ 160 MB<br>PB: ≤ 130 MB | *Fechada*:<br>0 MB | Tela cheia decorada com canvas. Destruída ao fechar (`Destroyed` restaura o HUD). |
| **Núcleo Python** | WS: ≤ 60 MB<br>PB: ≤ 50 MB | WS: ≤ 80 MB<br>PB: ≤ 70 MB | WS: ≤ 70 MB<br>PB: ≤ 60 MB | WS: ≤ 70 MB<br>PB: ≤ 60 MB | Medido em Linux: 54.7 MB em repouso e 60.5 MB após coleta de recursos. A meta estabelece folga de 10–20 MB para buffers de streaming SSE. |
| **MCPs Locais (6 processos stdio)** | WS: ≤ 420 MB<br>PB: ≤ 390 MB | WS: ≤ 460 MB<br>PB: ≤ 420 MB | WS: ≤ 420 MB<br>PB: ≤ 390 MB | WS: ≤ 420 MB<br>PB: ≤ 390 MB | Medido em Linux: ~68–70 MB por MCP. Para os 6 processos (`mesa`, `oficina`, `consulta`, `memoria`, `reuniao`, `configuracoes`), 6 × 70 MB = 420 MB. |
| **Serviço de Voz (Kokoro — padrão leve)** | WS: ≤ 120 MB<br>PB: ≤ 110 MB | WS: ≤ 160 MB<br>PB: ≤ 150 MB | WS: ≤ 120 MB<br>PB: ≤ 110 MB | WS: ≤ 120 MB<br>PB: ≤ 110 MB | Motor Kokoro-ONNX leve (82M int8). Se o usuário optar por Coqui XTTS v2, a meta específica de processo host isolado é WS ≤ 300 MB / PB ≤ 280 MB em repouso (somando ~180 MB aos totais de host, com pesos em VRAM de GPU); não deve ser misturado com Kokoro. |
| **Serviço de Reunião** | *Ocioso*:<br>WS: ≤ 50 MB<br>PB: ≤ 40 MB | *Ocioso*:<br>WS: ≤ 50 MB<br>PB: ≤ 40 MB | *Ocioso*:<br>WS: ≤ 50 MB<br>PB: ≤ 40 MB | *Ocioso*:<br>WS: ≤ 50 MB<br>PB: ≤ 40 MB | Em repouso apenas escuta rota `/status` (FastAPI ocioso: WS ≤ 50 MB, PB ≤ 40 MB). Se ativa em gravação e diarização, aloca até 250 MB na RAM. |
| **Total Global do Produto (sem Silero)** | **WS: ≤ 790 MB**<br>**PB: ≤ 700 MB** | **WS: ≤ 930 MB**<br>**PB: ≤ 830 MB** | **WS: ≤ 910 MB**<br>**PB: ≤ 805 MB** | **WS: ≤ 910 MB**<br>**PB: ≤ 805 MB** | Somatório auditável de todos os componentes ativos em cada cenário operacional estável (ver detalhamento aritmético abaixo). |
| **Total Global do Produto (com Silero VAD)** | **WS: ≤ 910 MB**<br>**PB: ≤ 835 MB** | **WS: ≤ 1065 MB**<br>**PB: ≤ 970 MB** | **WS: ≤ 1030 MB**<br>**PB: ≤ 940 MB** | **WS: ≤ 1030 MB**<br>**PB: ≤ 940 MB** | Somatório auditável incluindo a sobrecarga do runtime WASM/ONNX do Silero VAD no HUD. |

### Demonstração Aritmética Auditável dos Totais por Cenário

Para assegurar total rastreabilidade, a composição aritmética de cada total global é demonstrada componente a componente:

1. **Cenário 1: Repouso (Ocioso)**
   - Componentes: HUD (140 WS / 110 PB) + Configurações (0 / 0) + Sala (0 / 0) + Núcleo (60 WS / 50 PB) + 6 MCPs (420 WS / 390 PB) + Voz Kokoro (120 WS / 110 PB) + Reunião ocioso (50 WS / 40 PB).
   - **Total sem Silero**:
     - Working Set: `140 + 0 + 0 + 60 + 420 + 120 + 50 = 790 MB`
     - Private Bytes: `110 + 0 + 0 + 50 + 390 + 110 + 40 = 700 MB`
   - **Total com Silero VAD** (+120 WS / +135 PB):
     - Working Set: `790 + 120 = 910 MB`
     - Private Bytes: `700 + 135 = 835 MB`

2. **Cenário 2: Conversa Ativa**
   - Componentes: HUD (180 WS / 150 PB) + Configurações (0 / 0) + Sala (0 / 0) + Núcleo (80 WS / 70 PB) + 6 MCPs (460 WS / 420 PB) + Voz Kokoro (160 WS / 150 PB) + Reunião ocioso (50 WS / 40 PB).
   - **Total sem Silero**:
     - Working Set: `180 + 0 + 0 + 80 + 460 + 160 + 50 = 930 MB`
     - Private Bytes: `150 + 0 + 0 + 70 + 420 + 150 + 40 = 830 MB`
   - **Total com Silero VAD** (+135 WS / +140 PB):
     - Working Set: `930 + 135 = 1065 MB`
     - Private Bytes: `830 + 140 = 970 MB`

3. **Cenário 3: Sala Aberta**
   - Componentes: HUD escondido (90 WS / 75 PB) + Janela da Sala (160 WS / 130 PB) + Configurações (0 / 0) + Núcleo (70 WS / 60 PB) + 6 MCPs (420 WS / 390 PB) + Voz Kokoro (120 WS / 110 PB) + Reunião ocioso (50 WS / 40 PB).
   - **Total sem Silero**:
     - Working Set: `90 + 160 + 0 + 70 + 420 + 120 + 50 = 910 MB`
     - Private Bytes: `75 + 130 + 0 + 60 + 390 + 110 + 40 = 805 MB`
   - **Total com Silero VAD** (+120 WS / +135 PB):
     - Working Set: `910 + 120 = 1030 MB`
     - Private Bytes: `805 + 135 = 940 MB`

4. **Cenário 4: Configurações Abertas**
   - Componentes: HUD ativo (140 WS / 110 PB) + Janela de Configurações (110 WS / 95 PB) + Sala (0 / 0) + Núcleo (70 WS / 60 PB) + 6 MCPs (420 WS / 390 PB) + Voz Kokoro (120 WS / 110 PB) + Reunião ocioso (50 WS / 40 PB).
   - **Total sem Silero**:
     - Working Set: `140 + 110 + 0 + 70 + 420 + 120 + 50 = 910 MB`
     - Private Bytes: `110 + 95 + 0 + 60 + 390 + 110 + 40 = 805 MB`
   - **Total com Silero VAD** (+120 WS / +135 PB):
     - Working Set: `910 + 120 = 1030 MB`
     - Private Bytes: `805 + 135 = 940 MB`

*Nota sobre perfil XTTS v2*: Caso o usuário adote o motor de voz Coqui XTTS v2 com isolamento de processo no host (WS ≤ 300 MB / PB ≤ 280 MB), a meta total do sistema tem acréscimo de 180 MB em WS e 170 MB em PB em repouso sobre os totais calculados acima.

---

## 6. Antes e Depois por Componente

Esta seção consolida o baseline atual, a meta projetada para a versão 0.10.0, as oportunidades de redução de memória já identificadas no código e os módulos e arquivos responsáveis pelas alterações.

| Componente | Baseline Atual | Meta 0.10.0 | Reduções Seguras Identificadas | Módulos e Arquivos Impactados |
|---|---|---|---|---|
| **Arquitetura dos MCPs Locais** | **~420 MB** (6 processos CPython independentes consumindo ~70 MB cada um). | **≤ 420 MB** (em stdio isolado atual); estimativa futura **≤ 110 MB** (se consolidado em processo único). | **Diagnóstico**: O modelo stdio atual lança 6 processos Python paralelos via `nucleo/vard/segredos.py` (`servidores_locais`), onde cada processo carrega uma cópia completa do runtime Python, Pydantic, Starlette e SDK MCP (~70 MB).<br>**Oportunidade e Estimativa**: No Vard 0.9.4 leve, já houve a eliminação de `uv run` por chamada (poupando 15 subprocessos intermediários). Na versão 0.10.0, a unificação do despacho interno das ferramentas dentro do processo do núcleo ou a criação de um MCP consolidador de entrada única tem potencial estimado de poupar ~300 MB de RAM. Esta economia é uma estimativa/hipótese arquitetural que depende de coordenação técnica entre as ferramentas e o núcleo (já que o gerenciador de ferramentas e a integração externa com OpenJarvis utilizam o contrato stdio); não constitui promessa imediata. | Arquivos: `nucleo/vard/segredos.py`, `nucleo/server.py`, `nucleo/*_mcp.py`. Módulo de ferramentas e integração. |
| **Núcleo Python (Uvicorn / FastAPI)** | **~55–60 MB** (medido: 54.7 MB repouso, 60.5 MB pós-rotas). | **≤ 60 MB** em repouso. | O Uvicorn opera de forma enxuta. Reduções adicionais incluem o descarregamento (*lazy import*) de módulos administrativos (`vard/telegram_migracao.py`, rotas de pacotes) somente quando acionados. | Arquivos: `nucleo/server.py`. Módulo do núcleo. |
| **Janelas WebView2 (HUD / Config / Sala)** | **~150–250 MB** por janela ativa. | **Meta/hipótese**: redução estimada de 30% a 50% no consumo ocioso da Sala e Configurações (a ser validada por medição comparativa de Working Set no Windows antes e após a suspensão de loops visuais/canvas). | **Padrão implementado**: A janela de configurações e a sala já são destruídas ao fechar (`janelas.rs`), impedindo acúmulo de processos inativos. O HUD é escondido (`hide`) quando a sala abre.<br>**Oportunidade**: Interrupção de *requestAnimationFrame*, suspensão de timers CSS e parada de animações canvas quando a janela não estiver visível. | Arquivos: `src-tauri/src/janelas.rs`, `src/main.ts`, `src/sala-main.ts`, `src/sala/`. Módulo de interface. |
| **Detecção de Voz (VAD Silero vs Energia)** | Silero VAD on-demand: **~130 MB** líquido adicionado. Antes, reiniciar o detector sem `fechar()` deixava a sessão ONNX anterior viva até o fim do WebView. | **Zero impacto adicional** quando em modo Energia. Sessão anterior destruída no ponto de troca, coberta pelo teste `reiniciar sem fechar destrói a sessão Silero anterior exatamente uma vez` (`tests/vad-silero.test.ts`). A redução em MB no WebView2 não foi medida nesta máquina; a prova aqui é o teste de destruição, e a medição fica para o Windows. | O carregamento sob demanda (`src/audio/vad-selecionavel.ts` e `src/audio/silero.ts`) só instancia o ONNX Runtime Web e aloca tensores caso o usuário selecione explicitamente "Silero (local)". Destruição do modelo (`destruir()`) ao trocar para energia ou ao reiniciar o detector libera o WebAssembly e o contexto de inferência. | Arquivos: `src/audio/silero.ts`, `src/audio/vad-selecionavel.ts`. Módulo de áudio e interface. |
| **Serviço de Voz Local** | Variável: Kokoro (~100 MB RAM) ou XTTS v2 (~3 GB RAM se carregado em processo compartilhado). | Kokoro: **WS ≤ 120 MB / PB ≤ 110 MB**.<br>XTTS v2: **WS ≤ 300 MB / PB ≤ 280 MB** (processo host isolado; tensores neurais pesados em VRAM dedicada de GPU). | Em `voz/vard_voz/servidor.py`, a descarga de XTTS dentro do mesmo processo não devolve RAM ao sistema operacional. O isolamento do motor Kokoro em ONNX CPU garante estabilidade e baixo consumo. | Arquivos: `voz/vard_voz/servidor.py`. Módulo de síntese de voz. |

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
   Execute o script Python autocontido abaixo a partir da raiz do repositório (com isolamento via `setsid`, `cwd` em `nucleo/` e diretórios limpos em `/tmp`):
   ```bash
   cat << 'EOF' > /tmp/medir_memoria.py
   import os
   import signal
   import subprocess
   import time
   import psutil

   env = os.environ.copy()
   env["VARD_DADOS"] = "/tmp/vard-med-repro/dados"
   env["VARD_CONFIG"] = "/tmp/vard-med-repro/config"
   os.makedirs(env["VARD_DADOS"], exist_ok=True)
   os.makedirs(env["VARD_CONFIG"], exist_ok=True)

   # O módulo server:app exige execução com cwd em nucleo/
   proc = subprocess.Popen(
       [
           ".venv/bin/uvicorn",
           "server:app",
           "--host",
           "127.0.0.1",
           "--port",
           "4880",
           "--timeout-graceful-shutdown",
           "2",
       ],
       cwd="nucleo",
       env=env,
       preexec_fn=os.setsid,
       stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL,
   )
   print(f"Núcleo iniciado com PID {proc.pid}. Aguardando 25s de estabilização...")
   time.sleep(25)

   try:
       pai = psutil.Process(proc.pid)
       filhos = pai.children(recursive=True)
       rss_pai = pai.memory_info().rss / (1024 * 1024)
       print(f"Processo Pai (Uvicorn - PID {pai.pid}): {rss_pai:.1f} MB")

       total = rss_pai
       for f in filhos:
           rss_f = f.memory_info().rss / (1024 * 1024)
           total += rss_f
           print(f"  Filho MCP (PID {f.pid} - {f.name()}): {rss_f:.1f} MB")

       print(f"Árvore Total: {total:.1f} MB")
   finally:
       os.killpg(proc.pid, signal.SIGTERM)
       proc.wait(timeout=5)
       print("Processos encerrados com sucesso.")
   EOF
   ./nucleo/.venv/bin/python /tmp/medir_memoria.py
   rm -f /tmp/medir_memoria.py
   rm -rf /tmp/vard-med-repro
   ```

3. **Comando manual para medição direta de um MCP (ex.: Mesa)**:
   O bloco abaixo é autocontido: mantém o stdin do MCP aberto sem deixar `sleep` órfão,
   mede após estabilização e encerra todo o grupo de processos ao final.
   ```bash
   ./nucleo/.venv/bin/python - << 'PY'
   import os, signal, subprocess, time, psutil
   env = os.environ.copy()
   env["VARD_DADOS"] = "/tmp/vard-med-repro/dados"
   env["VARD_CONFIG"] = "/tmp/vard-med-repro/config"
   os.makedirs(env["VARD_DADOS"], exist_ok=True)
   os.makedirs(env["VARD_CONFIG"], exist_ok=True)
   proc = subprocess.Popen(
       ["./nucleo/.venv/bin/python", "nucleo/mesa_mcp.py"],
       env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
       preexec_fn=os.setsid,
   )
   time.sleep(25)
   try:
       rss = psutil.Process(proc.pid).memory_info().rss / (1024 * 1024)
       print(f"PID {proc.pid}: {rss:.1f} MB")
   finally:
       try: os.killpg(proc.pid, signal.SIGTERM)
       except ProcessLookupError: pass
       proc.wait(timeout=5)
       if proc.stdin: proc.stdin.close()
   PY
   rm -rf /tmp/vard-med-repro
   ```

4. **Medição do runtime WebAssembly ONNX e modelo Silero VAD em Node.js**:
   ```bash
   node -e "
   const fs = require('fs');
   const path = require('path');
   const baseline = parseInt(fs.readFileSync('/proc/self/status','utf8').match(/VmRSS:\s+(\d+)/)[1])/1024;
   const ort = require('onnxruntime-web');
   (async () => {
     const pastaDist = path.join('node_modules', '@ricky0123', 'vad-web', 'dist');
     const arquivoModelo = fs.readdirSync(pastaDist).find(f => f.endsWith('.onnx'));
     await ort.InferenceSession.create(path.join(pastaDist, arquivoModelo));
     const final = parseInt(fs.readFileSync('/proc/self/status','utf8').match(/VmRSS:\s+(\d+)/)[1])/1024;
     console.log('Delta ONNX Silero:', (final - baseline).toFixed(1), 'MB');
   })();
   "
   ```

### 8.2. Roteiro do Script de Medição no Windows (`scripts/windows/medir-ram.ps1`)

O medidor real entregue em `scripts/windows/medir-ram.ps1` é um script PowerShell somente leitura que inspeciona a árvore completa de processos a partir de um ou mais PIDs raiz, utilizando `Win32_Process` (CIM/WMI) e `Get-Process`. Ele calcula Working Set (`WorkingSet64`) e Private Bytes (`PrivateMemorySize64`) por processo, agrega por componente do Vard e produz um resumo estatístico multi-amostra.

**Parâmetros:**

- `-PidsRaiz` (obrigatório em modo de medição): um ou mais PIDs raiz da árvore a ser medida.
- `-Estado` (obrigatório em modo de medição): rótulo do cenário operacional — `repouso`, `conversa`, `sala` ou `configuracoes`.
- `-Amostras`: número de amostras consecutivas a coletar (padrão: 3).
- `-IntervaloSeg`: intervalo em segundos entre amostras (padrão: 2.0).
- `-SaidaJson`: caminho opcional para gravação do resultado estruturado em JSON; se omitido, o script emite tabelas formatadas no console.
- `-AutoTeste`: executa verificação lógica interna com dados sintéticos (classificação, agregação, herança, deduplicação, mediana/faixa e compatibilidade de StartTime) e sai com código 0 ou 1, sem tocar em processos reais.

**Exemplo de invocação:**

```powershell
.\scripts\windows\medir-ram.ps1 -PidsRaiz 1234,5678 -Estado repouso -Amostras 5 -IntervaloSeg 3 -SaidaJson .\medicao-repouso.json
```

**Conteúdo do JSON de saída:**

- `estado`, `iniciado_em` e metadados da máquina (`windows`, `arquitetura`).
- `amostras[]`: cada amostra contém `arvores[]` (com `processos[]` classificados por componente), `componentes[]` agregados e `total` (working set e private bytes somados).
- `resumo`: estatísticas de dispersão (mediana, mínimo e máximo) para o total geral, para cada componente e para cada processo ativo ao longo de todas as amostras.

Os componentes reconhecidos são: Widget, Núcleo, Cérebro (CLI), MCPs, Voz, Reunião, Bandeja e Outros, seguindo a convenção de classificação de `nucleo/vard/recursos.py`. Processos sob um pai classificado como Cérebro (CLI) herdam essa categoria obrigatoriamente.

**Pendência explícita:** executar e validar o modo `-AutoTeste` em ambiente Windows/PowerShell, pois este repositório é desenvolvido em Linux e não dispõe de PowerShell nativo para prova automatizada. A validação real dos cenários operacionais (`repouso`, `conversa`, `sala`, `configuracoes`) também requer execução manual no Windows com o aplicativo Vard em cada estado.
