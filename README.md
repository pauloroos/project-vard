# openjarvis-hud

[Read in English](README.en.md)

Widget de voz flutuante para o [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), feito com Tauri 2. Uma janela transparente e sem moldura, sempre no topo, com um núcleo ciano que reage à sua voz: você fala, ele transcreve, o OpenJarvis responde e a resposta sai em voz alta.

![HUD em repouso](docs/captura-repouso.png) ![HUD falando](docs/captura-falando.png)

## O que ele faz

- Escuta pelo microfone (detecção de voz automática) ou por push-to-talk com atalho global.
- Chama o assistente pelo nome ("Vard, que horas são"); com push-to-talk o nome é dispensado.
- Transcreve, pergunta e sintetiza a resposta no próprio OpenJarvis (`/v1/speech/transcribe`, `/v1/chat/completions`, `/v1/speech/synthesize`).
- Ícone na bandeja, painel de configurações, início opcional com o Windows.
- Botão **Texto** abre a interface gráfica de texto do OpenJarvis.
- Opcional: a ponte do Vard (setup privado do autor, `rdl-vard`) dá olhos na tela e modo jogo. Sem ela tudo funciona igual, veja [docs/ponte-do-vard.md](docs/ponte-do-vard.md).

## Requisitos

- Windows 10 ou 11 (64 bits) com o WebView2, que já vem no Windows 11.
- OpenJarvis rodando em `http://127.0.0.1:8000` **com a fala ligada**: veja [docs/ligar-a-fala.md](docs/ligar-a-fala.md). Sem a fala o HUD abre, mas fica avisando que não consegue ouvir nem falar.
- Um microfone.
- Para o botão **Texto**: a interface gráfica do OpenJarvis (`jarvis gui`), em `http://127.0.0.1:5173`. Precisa de Node.js e do checkout do OpenJarvis.

## Instalar

Baixe o instalador na página de releases e rode um dos dois:

- `openjarvis-hud_0.1.0_x64-setup.exe` (NSIS): instala só para o seu usuário, sem pedir administrador. Silencioso: `openjarvis-hud_0.1.0_x64-setup.exe /S`. Fica em `%LOCALAPPDATA%\openjarvis-hud\`.
- `openjarvis-hud_0.1.0_x64_en-US.msi` (WiX): instala para a máquina toda e exige administrador. Silencioso: `msiexec /i openjarvis-hud_0.1.0_x64_en-US.msi /qn`.

Para gerar você mesmo: `npm install` e `npm run tauri build` (os instaladores saem em `src-tauri/target/release/bundle/`).

## Usar

1. Abra o OpenJarvis com a fala ligada e depois o HUD. A linha de estado diz "pronto".
2. Dê **dois cliques no núcleo** (ou clique no botão do microfone) para abrir o microfone. O Windows pode pedir permissão na primeira vez.
3. Diga "Vard, que horas são". O núcleo fica âmbar ouvindo, azul pensando, e a resposta sai em voz alta.

### Atalhos

| Atalho | O que faz |
| --- | --- |
| `Ctrl+Alt+Space` (segurar) | Push-to-talk: fale enquanto segura; o nome "Vard" é dispensado |
| `Ctrl+Alt+Period` | Interrompe a fala em curso |
| `Ctrl+Alt+V` | Mostra ou oculta o HUD |

Os três podem ser trocados no painel de configurações (valem depois de reiniciar o HUD).

### Botões

Mudo do microfone, interromper, olhar a tela (só com a ponte), abrir a conversa em texto, sempre no topo, configurações e modo compacto. O ícone da bandeja tem Mostrar/ocultar, Sempre no topo, Configurações e Sair.

## Configurar

Pela engrenagem do HUD ou pelo item **Configurações** da bandeja. O painel tem todos os campos do arquivo `hud.config.json` (em `%APPDATA%\dev.openjarvis.hud\`):

| Campo | Padrão | Para quê |
| --- | --- | --- |
| `openjarvis_url` | `http://127.0.0.1:8000` | Onde está o OpenJarvis |
| `gui_url` | `http://127.0.0.1:5173` | Interface de texto (botão Texto) |
| `ponte_url` | `http://127.0.0.1:4700` | Ponte opcional (vazio desliga) |
| `nome`, `variantes` | `vard` e grafias parecidas | Palavra que chama o assistente |
| `usuario` | vazio | Como o assistente te chama na saudação ("Oi, Ana."); vazio diz só "Oi." |
| `idioma` | `pt` | Idioma do reconhecimento |
| `voz`, `velocidade` | `pm_alex`, `1.05` | Voz e velocidade da fala |
| `finish_ms`, `limiar_vad` | `900`, `0.02` | Silêncio que encerra a fala e sensibilidade do microfone |
| `sempre_no_topo`, `click_through` | ligado, desligado | Janela sempre visível; clique atravessa a janela |
| `atalhos` | ver acima | Atalhos globais |
| `instrucao_formato` | respostas curtas | Instrução enviada junto com cada pergunta |

Endereços fora de `127.0.0.1` ou `localhost` geram um aviso (o HUD manda o que você diz e, com a ponte, imagens da sua tela; mantenha tudo na própria máquina). A caixa **Iniciar com o Windows** cria ou remove `openjarvis-hud.lnk` na pasta Startup do seu usuário. O botão **Testar OpenJarvis** confere o servidor e a fala.

## Solução de problemas

- **"núcleo offline"**: o OpenJarvis não respondeu em `openjarvis_url`. Suba o servidor (`jarvis serve`) e confira o endereço no painel. O HUD volta sozinho em até 5 s.
- **Fala desligada** (o HUD avisa e não ouve): o `[speech]` do OpenJarvis não está ativo ou o backend não carregou. Veja [docs/ligar-a-fala.md](docs/ligar-a-fala.md) e o log do servidor.
- **Microfone**: se o HUD diz que o microfone está bloqueado, libere em Configurações do Windows, Privacidade, Microfone, e dê dois cliques no núcleo de novo. Se ele corta o começo das frases ou ouve ruído, ajuste `limiar_vad`.
- **O botão Texto não abre nada útil**: a interface de texto do OpenJarvis não está de pé em `gui_url`. Suba com `jarvis gui --no-server --no-browser`.
- **Atalho não funciona**: outro programa já usa a combinação. Troque no painel e reinicie o HUD.

## Desenvolvimento

Veja [CONTRIBUTING.md](CONTRIBUTING.md). Licença: MIT.
