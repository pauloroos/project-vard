# Capturas visuais de referência do Vard

Este diretório contém as capturas de tela das interfaces do Vard (HUD, Sala e janelas de Configurações), servindo como referência visual antes e depois de alterações de design e interface.

## Estrutura de diretórios

- `antes/`: Capturas do estado visual de referência (antes do redesenho da versão 0.10.0), totalizando 14 imagens cobrindo o HUD, a Sala e todas as 12 seções de Configurações.
- `depois/`: Diretório reservado para o registro visual após a conclusão das melhorias visuais.

## Como reproduzir as capturas

As capturas são geradas automaticamente por script Playwright em Python síncrono (`scripts/provas/capturas-visual.py`), executando Chromium headless.

```bash
PLAYWRIGHT_BROWSERS_PATH=<diretório de navegadores do Playwright> \
python scripts/provas/capturas-visual.py
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
