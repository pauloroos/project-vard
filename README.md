# Vard

[Read in English](README.en.md) · [Repositório](https://github.com/pauloroos/project-vard)

Vard é uma interface de voz local (widget flutuante) para assistentes; o primeiro conector é o [OpenJarvis](https://github.com/open-jarvis/OpenJarvis). Feito com Tauri 2. Uma janela transparente e sem moldura, sempre no topo, com um núcleo ciano que reage à sua voz: você fala, ele transcreve, o OpenJarvis responde e a resposta sai em voz alta.

![HUD em repouso](docs/captura-repouso.png) ![HUD falando](docs/captura-falando.png)

Projeto independente, sem vínculo com o OpenJarvis nem com a Stanford.

## O que ele faz

- Escuta pelo microfone (detecção de voz automática) ou por push-to-talk com atalho global.
- Chama o assistente pelo nome ("Vard, que horas são"); com push-to-talk o nome é dispensado.
- Transcreve, pergunta e sintetiza a resposta no próprio OpenJarvis (`/v1/speech/transcribe`, `/v1/chat/completions`, `/v1/speech/synthesize`).
- Ícone na bandeja, painel de configurações em janela própria (abas Geral, Voz, Atalhos, Ponte e Modelos), início opcional com o Windows.
- Três tamanhos (ou o lado em pixels, de 160 a 800) e um modo compacto que deixa só o holograma.
- Tela cheia ("sala") num monitor à escolha: vórtice grande, o que você disse, a resposta em letra grande e um relógio.
- Escolha do modelo entre os que o OpenJarvis expõe.
- Botão **Texto** abre a interface gráfica de texto do OpenJarvis.
- Opcional: a ponte do Vard (setup privado do autor, `rdl-vard`) dá olhos na tela e modo jogo. Sem ela tudo funciona igual, veja [docs/ponte-do-vard.md](docs/ponte-do-vard.md).
- Opcional: uma voz própria (qualquer motor de voz local que siga um contrato simples) fala a resposta frase a frase, começando antes de a resposta inteira estar sintetizada. Veja [Voz própria](#voz-própria-opcional).

## Requisitos

- Windows 10 ou 11 (64 bits) com o WebView2, que já vem no Windows 11.
- OpenJarvis rodando em `http://127.0.0.1:8000` **com a fala ligada**: veja [docs/ligar-a-fala.md](docs/ligar-a-fala.md). Sem a fala o HUD abre, mas fica avisando que não consegue ouvir nem falar.
- Um microfone.
- Para o botão **Texto**: a interface gráfica do OpenJarvis (`jarvis gui`), em `http://127.0.0.1:5173`. Precisa de Node.js e do checkout do OpenJarvis.

## Instalar

Baixe o instalador na página de releases e rode um dos dois:

- `Vard_0.2.0_x64-setup.exe` (NSIS): instala só para o seu usuário, sem pedir administrador. Silencioso: `Vard_0.2.0_x64-setup.exe /S`. Fica em `%LOCALAPPDATA%\Vard\`.
- `Vard_0.2.0_x64_en-US.msi` (WiX): instala para a máquina toda e exige administrador. Silencioso: `msiexec /i Vard_0.2.0_x64_en-US.msi /qn`.

Para gerar você mesmo: `npm install` e `npm run tauri build` (os instaladores saem em `src-tauri/target/release/bundle/`).

## Usar

1. Abra o OpenJarvis com a fala ligada e depois o HUD. A linha de estado pede para tocar duas vezes no núcleo.
2. Dê **dois cliques no núcleo** (ou clique no botão do microfone) para abrir o microfone. O Windows pode pedir permissão na primeira vez.
3. Diga "Vard, que horas são". O núcleo fica ciano ouvindo, âmbar pensando, e a resposta sai em voz alta.

### Atalhos

| Atalho | O que faz |
| --- | --- |
| `Ctrl+Alt+Space` (segurar) | Push-to-talk: fale enquanto segura; o nome "Vard" é dispensado |
| `Ctrl+Alt+Period` | Interrompe a fala em curso |
| `Ctrl+Alt+V` | Mostra ou oculta o widget |
| `Ctrl+Alt+,` | Abre ou fecha as configurações |
| `Ctrl+Alt+E` | Liga a escuta (abre o microfone) ou alterna o mudo |
| `Ctrl+Alt+F` | Liga ou desliga a tela cheia (sala) |

Todos podem ser trocados na aba Atalhos: clique no campo e pressione a nova combinação (Ctrl, Alt ou Win mais uma tecla). O painel recusa combinações repetidas e marca o atalho que o Windows não aceitou (outro programa já usa). Valem depois de reiniciar o Vard.

![Painel de atalhos](docs/painel-atalhos.png)

### Botões

Mudo do microfone, interromper, olhar a tela (só com a ponte), abrir a conversa em texto, sempre no topo, configurações e modo compacto. No compacto o widget fica só com o holograma: os botões aparecem quando o mouse passa por cima e somem 2 s depois que ele sai (com "clique atravessa" ligado eles não aparecem). O ícone da bandeja tem Mostrar/ocultar, Sempre no topo, Configurações, Tela cheia e Sair.

## Configurar

Pela engrenagem, pelo item **Configurações** da bandeja ou por `Ctrl+Alt+,`. O painel abre numa janela própria com as abas Geral, Voz, Atalhos, Ponte e Modelos. Salvar aplica na hora o tamanho, o compacto, sempre no topo, o clique atravessando, o seu nome e o modelo; endereços, voz, ouvido e atalhos valem depois de reiniciar (o painel diz quais). Os campos são os do arquivo `hud.config.json` (se ele ficar ilegível, o HUD sobe com o padrão e guarda o original como `hud.config.json.invalido`; em `%APPDATA%\io.github.pauloroos.vard\`):

| Campo | Padrão | Para quê |
| --- | --- | --- |
| `openjarvis_url` | `http://127.0.0.1:8000` | Onde está o OpenJarvis |
| `gui_url` | `http://127.0.0.1:5173` | Interface de texto (botão Texto) |
| `ponte_url` | `http://127.0.0.1:4700` | Ponte opcional (vazio desliga) |
| `voz_url` | `http://127.0.0.1:4710` | Voz própria opcional (vazio desliga; sem o serviço no ar, a voz é a do OpenJarvis) |
| `nome`, `variantes` | `vard` e grafias parecidas | Palavras que chamam o assistente: o `nome` mais as `variantes` (com outro nome, as variantes padrão do Vard saem) |
| `usuario` | vazio | Como o assistente te chama na saudação ("Oi, Ana."); vazio diz só "Oi." |
| `idioma` | `pt` | Idioma do reconhecimento |
| `voz`, `velocidade` | `pm_alex`, `1.05` | Voz e velocidade da fala |
| `finish_ms`, `limiar_vad` | `900`, `0.02` | Silêncio que encerra a fala e sensibilidade do microfone |
| `sempre_no_topo`, `click_through` | ligado, desligado | Janela sempre visível; clique atravessa a janela |
| `tamanho`, `tamanho_px` | `medio`, `320` | Tamanho do widget: `pequeno` (240 px), `medio` (320), `grande` (480) ou `personalizado` (`tamanho_px`, de 160 a 800) |
| `compacto` | desligado | Só o holograma; os botões aparecem com o mouse |
| `modelo` | vazio | Modelo do OpenJarvis (vazio = o primeiro da lista dele) |
| `sala_monitor` | vazio | Monitor da tela cheia (vazio = o principal) |
| `atalhos` | ver acima | Atalhos globais: `falar`, `parar`, `mostrar`, `config`, `escuta`, `sala` |
| `instrucao_formato` | respostas curtas | Instrução enviada junto com cada pergunta |

Endereços fora de `127.0.0.1` ou `localhost` geram um aviso (o HUD manda o que você diz e, com a ponte, imagens da sua tela; mantenha tudo na própria máquina). A caixa **Iniciar com o Windows** cria ou remove `Vard.lnk` na pasta Startup do seu usuário. O botão **Testar OpenJarvis** confere o servidor e a fala.

## Tela cheia (sala)

![Sala em tela cheia](docs/sala.png)

`Ctrl+Alt+F` ou **Tela cheia** na bandeja abrem uma janela preta, sem bordas, ocupando o monitor escolhido em Geral → Janela: o vórtice grande, o que você disse, a resposta em letra grande e um relógio. É só um espelho: quem ouve e fala continua sendo o widget, que pode ficar em outro monitor. `Esc`, o atalho ou a bandeja fecham. Se o monitor escolhido estiver desconectado, a sala abre no principal e o widget avisa.

O widget fica sempre no topo e pode cobrir a sala se estiver no mesmo monitor: use outro monitor para a sala ou mova o widget para um canto.

## Modelos

A aba **Modelos** lista os modelos que o OpenJarvis expõe (`/v1/models`) e deixa escolher o principal; "Automático" usa o primeiro da lista. Se a ponte do Vard informar um modelo de reserva, ele aparece ali. **Testar** faz uma pergunta curta e mostra quanto tempo levou. Trocar de provedor (OmniRouter, assinaturas, LM Studio) é configuração do OpenJarvis: o Vard só escolhe entre o que ele oferece. Se o modelo escolhido sumir do OpenJarvis, o Vard usa o primeiro da lista.

## Voz própria (opcional)

Por padrão a resposta é sintetizada inteira pelo OpenJarvis e só então começa a tocar. Com um serviço de voz local em
`voz_url`, o HUD corta a resposta em frases, toca a primeira assim que chega o primeiro pedaço de áudio e pede a
seguinte enquanto a atual ainda toca. As falas fixas ("Voltei." e as outras) também passam por ela e ficam em cache.

O serviço pode usar qualquer motor de voz. Ele precisa de duas rotas em `127.0.0.1`:

- `GET /saude` devolve `{"pronta": true, "voz": "nome da voz", ...}`.
- `POST /falar` recebe `{"texto": "uma frase", "velocidade": 1.05}` (até 400 caracteres). Com `Accept: audio/pcm`
  responde `200` com PCM de 16 bits, mono, little-endian, em fluxo (`Transfer-Encoding: chunked`), a 24 kHz
  (cabeçalhos `X-Taxa`, `X-Canais`, `X-Formato`). `400` para texto vazio ou longo demais, `503 {"erro": "aquecendo"}`
  enquanto carrega o modelo.
- CORS liberado para `http://tauri.localhost` (app instalado) e `http://localhost:1420` (`tauri dev`).

Se o serviço estiver fora, demorar mais de 8 s ou recusar uma frase, aquela frase sai pela voz do OpenJarvis sem aviso
na tela. O contrato completo está em [docs/voz-propria.md](docs/voz-propria.md).

## Solução de problemas

- **"núcleo offline"**: o OpenJarvis não respondeu em `openjarvis_url`. Suba o servidor (`jarvis serve`) e confira o endereço no painel. O HUD volta sozinho em até 5 s.
- **Fala desligada** (o HUD avisa e não ouve): o `[speech]` do OpenJarvis não está ativo ou o backend não carregou. Veja [docs/ligar-a-fala.md](docs/ligar-a-fala.md) e o log do servidor.
- **Microfone**: se o HUD diz que o microfone está bloqueado, libere em Configurações do Windows, Privacidade, Microfone, e dê dois cliques no núcleo de novo. Se ele corta o começo das frases ou ouve ruído, ajuste `limiar_vad`.
- **O botão Texto não abre nada útil**: a interface de texto do OpenJarvis não está de pé em `gui_url`. Suba com `jarvis gui --no-server --no-browser`.
- **Atalho não funciona**: outro programa já usa a combinação. A aba Atalhos marca o atalho que não registrou; troque e reinicie o Vard.
- **A sala abriu no monitor errado**: o monitor escolhido estava desconectado e ela abriu no principal. Escolha de novo em Geral → Janela.

## Conectores

O Vard fala com assistentes por conectores. Hoje existe um só, o OpenJarvis (`src/conectores/openjarvis/cliente.ts`). Outros são bem-vindos: basta implementar a interface `Conector` em `src/conectores/conector.ts` (`saude`, `modelos`, `definirModelo`, `transcrever`, `perguntar`, `sintetizar`). `definirModelo` guarda o modelo preferido (vazio = o primeiro de `modelos()`) e vale na próxima pergunta. Atenção: na aba Modelos do painel, escolher um modelo diferente do automático, ou clicar em Testar nele, pode fazer o servidor de LLM (por exemplo o LM Studio) carregar um segundo modelo na GPU e consumir memória.

## Desenvolvimento

Veja [CONTRIBUTING.md](CONTRIBUTING.md). Licença: MIT.
