# Capturas visuais de referência do Vard

Este diretório contém as capturas de tela das interfaces do Vard (HUD, Sala e janelas de Configurações), servindo como referência visual antes e depois de alterações de design e interface.

## Estrutura de diretórios

- `antes/`: Capturas do estado visual de referência (antes do redesenho da versão 0.10.0), totalizando 14 imagens cobrindo o HUD, a Sala e todas as 12 seções de Configurações.
- `depois/`: Capturas do novo sistema visual implementado na versão 0.10.0, com tokens unificados, profundidade em vidro fosco, escala tipográfica consistente e acessibilidade completa.

## Comparação antes e depois

| Tela / Aba | Antes (`antes/`) | Depois (`depois/`) | Melhorias visuais aplicadas |
| :--- | :--- | :--- | :--- |
| **HUD** (`index.html`) | `hud.png` | `hud.png` | Chips de andamento, avisos e reunião aperfeiçoados com vidro fosco (`backdrop-filter`), raios pílula e sombras em camadas. Botões com foco visível `:focus-visible`, estados de repouso/hover aprimorados e tipografia técnica em mono com tracking refinado. |
| **Sala** (`sala.html`) | `sala.png` | `sala.png` | Moldura HUD holográfica militar-futurista com cantos técnicos em tela cheia e telemetria discreta. Grade sutil e vinheta escura feitas com gradientes CSS puros. Relógio mono nítido, estado e textos em escala tipográfica balanceada. |
| **Geral** | `configuracoes-geral.png` | `configuracoes-geral.png` | Seletor de cores em pílula com anéis de foco acessíveis, monitor de recursos com tabela de cabeçalho técnico e contrastes uniformizados. |
| **Perfil** | `configuracoes-perfil.png` | `configuracoes-perfil.png` | Cards de perfil pronto em vidro fosco com sombras de profundidade, campos com foco `:focus-visible` de 2px e anel de realce sem remoção cega de outline. |
| **Voz** | `configuracoes-voz.png` | `configuracoes-voz.png` | Grade de motores de voz em cartões de vidro com realce ativo e hover suave; avisos semânticos em âmbar legível. |
| **Transcrição** | `configuracoes-transcricao.png` | `configuracoes-transcricao.png` | Controles de VAD, limiar e formato de instrução com tipografia técnica e inputs unificados nos tokens. |
| **Atalhos** | `configuracoes-atalhos.png` | `configuracoes-atalhos.png` | Botões de captura de atalho em estilo técnico com realce em borda tracejada ao ouvir; linhas com espaçamento harmônico. |
| **Oficina** | `configuracoes-oficina.png` | `configuracoes-oficina.png` | Barra de filtros e busca em vidro fosco, cards de habilidades com bordas sutis e fichas compactas. |
| **Modelos** | `configuracoes-modelos.png` | `configuracoes-modelos.png` | Provedores e modelos com selos de status contrastantes (`selo-ativo`, `selo-reserva`) e foco visível. |
| **Painéis & MCPs** | `configuracoes-paineis-mcps.png` | `configuracoes-paineis-mcps.png` | Tabelas transformadas em cartões de leitura horizontal com bordas de vidro fosco, etiquetas técnicas e botões de ação organizados. |
| **Sistema** | `configuracoes-sistema.png` | `configuracoes-sistema.png` | Opções de inicialização, telemetria e diagnóstico com fieldsets em vidro e contraste de texto AA. |
| **Reunião** | `configuracoes-reuniao.png` | `configuracoes-reuniao.png` | Bloco de reunião ativa com selo semântico e histórico de última reunião integrado ao tema escuro. |
| **Avisos** | `configuracoes-avisos.png` | `configuracoes-avisos.png` | Lista de avisos em cards horizontais com horário mono, texto descritivo e destaque âmbar para novos alertas. |
| **Diagnóstico** | `configuracoes-diagnostico.png` | `configuracoes-diagnostico.png` | Relatório de conectores, latência e saúde de processos com fundo escuro translúcido e texto legível. |

## Tabela de contraste de cores (WCAG AA)

Todos os pares de texto e elementos interativos do sistema de tokens (`src/tokens.css`) foram projetados e validados para atender ou superar os requisitos de conformidade WCAG 2.1 nível AA (mínimo de 4,5:1 para texto normal e 3,0:1 para elementos de destaque/gráficos) contra os fundos reais da interface:

| Elemento / Token | Cor Hex | Fundo de Aplicação | Luminância Relativa | Razão de Contraste | Nível WCAG |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `--vard-texto` | `#d8f4f8` | `--vard-fundo` (`#060b11`) | 0,8841 vs 0,0033 | **17,5 : 1** | AAA (Passa) |
| `--vard-texto` | `#d8f4f8` | `--vard-fundo-elevado` (`#0a141e`) | 0,8841 vs 0,0055 | **16,8 : 1** | AAA (Passa) |
| `--vard-texto-fraco` | `#92c5d1` | `--vard-fundo` (`#060b11`) | 0,5284 vs 0,0033 | **10,8 : 1** | AAA (Passa) |
| `--vard-texto-fraco` | `#92c5d1` | `--vard-fundo-elevado` (`#0a141e`) | 0,5284 vs 0,0055 | **10,4 : 1** | AAA (Passa) |
| `--vard-ciano` | `#00f0ff` | `--vard-fundo` (`#060b11`) | 0,6908 vs 0,0033 | **13,9 : 1** | AAA (Passa) |
| `--vard-ciano` | `#00f0ff` | `--vard-fundo-elevado` (`#0a141e`) | 0,6908 vs 0,0055 | **13,3 : 1** | AAA (Passa) |
| `--vard-ciano-forte` | `#3df3ff` | `--vard-fundo` (`#060b11`) | 0,8037 vs 0,0033 | **16,0 : 1** | AAA (Passa) |
| `--vard-ambar` (pensando/aviso) | `#ffb020` | `--vard-fundo` (`#060b11`) | 0,5262 vs 0,0033 | **10,8 : 1** | AAA (Passa) |
| `--vard-violeta` (transcrição) | `#b59cff` | `--vard-fundo` (`#060b11`) | 0,4079 vs 0,0033 | **8,6 : 1** | AAA (Passa) |
| `--vard-erro` (erro/captura) | `#ff5555` | `--vard-fundo` (`#060b11`) | 0,2858 vs 0,0033 | **6,3 : 1** | AA (Passa) |

*Nota: Em fundos com superfícies translúcidas (`--vard-superficie` ou `--vard-vidro`), o contraste efetivo de `--vard-texto` e `--vard-ciano` permanece acima de 12:1.*

## Como reproduzir as capturas

As capturas são geradas automaticamente por script Playwright em Python síncrono (`scripts/provas/capturas-visual.py`), executando Chromium headless.

```bash
PLAYWRIGHT_BROWSERS_PATH=<diretório de navegadores do Playwright> \
python scripts/provas/capturas-visual.py --saida docs/capturas/depois
```

### Argumentos opcionais

- `--url <URL>`: Especifica uma instância do Vite já em execução (ex.: `http://127.0.0.1:5199`). Quando omitido, o script inicializa o próprio processo do Vite na porta 5199 com `--strictPort` e `VITE_PROVA=repouso`, encerrando-o de forma limpa ao final.
- `--saida <PASTA>`: Diretório de destino dos arquivos PNG gerados (padrão: `docs/capturas/antes`).

## Método e arquitetura de mock

No ambiente Linux headless de CI/desenvolvimento, não há runtime WebView2 nem o subsistema gráfico do Windows. Para capturar as páginas exatamente como renderizadas pelo front-end em Vite:

1. **Mock de IPC do Tauri v2**:
   - Injetado antes do carregamento de qualquer página (`page.add_init_script`), provendo `window.__TAURI__` e `window.__TAURI_INTERNALS__`.
   - Implementa `invoke`, `transformCallback`, `unregisterCallback`, `convertFileSrc` e `metadata`.
   - Responde às chamadas de IPC (`ler_config`, `ler_paineis`, `listar_monitores`, `falhas_de_atalho`, `versao_do_app`, `buscar_release`) com estruturas e dados fictícios pré-definidos (nome "Aurora", provedores e MCPs de exemplo, monitores genéricos), sem conter caminhos pessoais, segredos ou chaves de API.
   - Gerencia eventos através de `plugin:event|listen` permitindo emissão de eventos simulados controlados (como `sala:espelho`).

2. **Fundo sintético escuro no HUD**:
   - O widget do HUD (`index.html`) opera nativamente no Windows como uma janela frameless transparente flutuante sobre a área de trabalho.
   - No navegador headless sem o desktop do sistema operacional, uma janela transparente capturada resultaria em artefatos ou fundo indefinido. Para tornar visíveis a luminescência ciano, os anéis holográficos e as partículas, o script aplica temporariamente um fundo sintético escuro neutro (`#0b0f17`) atrás do elemento `#app` antes de tirar a captura.

3. **Retrato simulado na Sala**:
   - A tela de sala (`sala.html`) funciona como um espelho de tela cheia que aguarda eventos do núcleo. O script dispara via mock o evento `sala:espelho` com um retrato em repouso contendo pergunta e resposta fictícias para registrar a composição tipográfica completa.

4. **Navegação nas Configurações**:
   - A tela de configurações (`configuracoes.html`) tem suas 12 abas navegadas e registradas sequencialmente (`geral`, `perfil`, `voz`, `transcricao`, `atalhos`, `oficina`, `modelos`, `paineis-mcps`, `sistema`, `reuniao`, `avisos`, `diagnostico`), capturando o markup autêntico gerado pelas classes da interface.

## Limites do método

- **Chromium headless vs. WebView2**: A prova é realizada no motor Chromium puro no Linux. Diferenças sutis de renderização de fontes, antialiasing ou flags de GPU do WebView2 no Windows não são reproduzidas.
- **Escala de DPI e sistema operacional**: Viewports e `device_scale_factor` simulam a resolução lógica e 2x de densidade, mas não refletem particularidades do subsistema de janelas do Windows (DPI awareness por monitor, DWM, cantos arredondados nativos do Windows 11).
- **Sem áudio nem hardware**: Analisadores de frequência e VAD são simulados pelo módulo de prova sintética do app; não há validação de dispositivos reais de captura ou drivers WASAPI.
- **Não substitui a prova real**: Capturas visuais automatizadas comprovam apenas a estabilidade do layout, alinhamentos e ausência de regressões visuais óbvias em tela. A validação funcional completa exige a execução real do aplicativo integrado ao ecossistema Windows e seus conectores.
