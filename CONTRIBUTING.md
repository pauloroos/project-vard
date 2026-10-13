# Contribuindo / Contributing

## Requisitos / Requirements

Node.js 22+, Rust (MSVC) com as Build Tools C++ do Visual Studio, WebView2. Windows 10/11.
Node.js 22+, Rust (MSVC) with the Visual Studio C++ Build Tools, WebView2. Windows 10/11.

```
npm install
```

## Testes / Tests

```
npm test                  # unitários e integração contra o servidor falso (em processo)
npx tsc --noEmit          # tipos (src/)
npx tsc -p tsconfig.test.json   # tipos dos testes
cargo test --manifest-path src-tauri/Cargo.toml
```

`HUD_REAL=1 HUD_REAL_WAV=<um WAV dizendo "Preflight"> npm run test:real` (PowerShell: `$env:HUD_REAL=1; $env:HUD_REAL_WAV="<wav>"; npm run test:real`) prova contra um OpenJarvis de verdade (transcrever, perguntar, sintetizar).

O front tem três páginas, declaradas em vite.config.ts: index.html (widget), configuracoes.html (painel) e sala.html (tela cheia).
The front end has three pages, declared in vite.config.ts: index.html (widget), configuracoes.html (settings) and sala.html (full screen).

## Rodar em desenvolvimento / Run in development

```
npm run tauri dev
```

No `tauri dev` o front fala com o OpenJarvis por um proxy do Vite em `/oj` (o CORS do OpenJarvis recusa a origem `localhost:1420`); mude o alvo com `VITE_OJ_ALVO`. O app instalado fala direto com `openjarvis_url`.
In `tauri dev` the front end reaches OpenJarvis through a Vite proxy at `/oj` (OpenJarvis' CORS rejects the `localhost:1420` origin); change the target with `VITE_OJ_ALVO`. The installed app talks to `openjarvis_url` directly.

## Harness (sem voz humana) / Harness (no human voice)

```
npm run harness
```

Sobe um OpenJarvis falso em `http://127.0.0.1:8765` (transcrição fixa, resposta "Agora são 13h.", senoide de 0,3 s). Use `VITE_OJ_ALVO=http://127.0.0.1:8765 npm run tauri dev` (PowerShell: `$env:VITE_OJ_ALVO="http://127.0.0.1:8765"; npm run tauri dev`), abra o microfone (duplo clique no núcleo) e aperte o push-to-talk por 1 s em silêncio; com o microfone fechado o push-to-talk é ignorado. `PONTE=4700 npm run harness` (PowerShell: `$env:PONTE=4700; npm run harness`) acrescenta uma ponte falsa. `VOZ=4710 npm run harness` (PowerShell: `$env:VOZ=4710; npm run harness`) acrescenta uma voz própria falsa (`/saude` e `/falar`: 3 pedaços de 0,1 s de silêncio em PCM, ou um WAV de 0,3 s); ela só sobe com a variável, para não brigar com um serviço de voz de verdade na 4710. Contrato em [docs/voz-propria.md](docs/voz-propria.md). `RELEASE=1 npm run harness` (PowerShell: `$env:RELEASE=1; npm run harness`) acrescenta uma release falsa do GitHub (versão 9.9.9, com `/download/` do instalador) para a aba Atualização; no `tauri dev` aponte a consulta para ela com `VITE_RELEASE_URL`.
Starts a fake OpenJarvis at `http://127.0.0.1:8765`. Use it with `VITE_OJ_ALVO`, open the microphone first (double-click the core): push-to-talk is ignored while it is closed. `PONTE=4700` adds a fake bridge. `VOZ=4710` adds a fake voice service (only with the variable, so it never collides with a real one on 4710). `RELEASE=1` adds a fake GitHub release (version 9.9.9, with a `/download/` route) for the Atualização tab; in `tauri dev` point the lookup at it with `VITE_RELEASE_URL`.

No `tauri dev` existem ganchos em `window` (só em desenvolvimento): `__vardPergunta("que horas são")` injeta a pergunta como se viesse do microfone com push-to-talk (sem exigir o nome); com o microfone fechado, toca por uma saída de áudio própria. `__vardOuvido("vard, que horas são")` injeta uma fala pelo caminho do detector de voz (exige o nome, a menos que o modo conversa esteja aberto). `__vardMover(x, y)` move o widget (pixels físicos), para provar o dock dos botões sem mouse. O console mostra `resposta do núcleo em X ms` e `voz: 1º áudio em Y ms após a resposta`.
In `tauri dev`, `window.__vardPergunta("...")` (development only) injects a question as if it came from the microphone with push-to-talk; the console prints both timings. `window.__vardOuvido("...")` injects an utterance through the voice-detector path (the wake word is required unless conversation mode is open) and `window.__vardMover(x, y)` moves the widget (physical pixels) to prove the button dock without a mouse.

## Provas sem injetar teclado / Proofs without keyboard injection

Prove o comportamento por testes, pelo harness e por `window.__vardPergunta`, nunca simulando teclas ou cliques do mouse no sistema (atalhos globais e foco são do usuário). Para capturas do painel, abra `configuracoes.html` no Vite com `invoke` simulado, sem dados pessoais.
Prove behaviour through tests, the harness and `window.__vardPergunta`, never by simulating system-wide key presses or mouse clicks (global shortcuts and focus belong to the user). For panel screenshots, open `configuracoes.html` in Vite with a mocked `invoke` and no personal data.

## Ícone / Icon

`python scripts/gerar-icone.py icone.png` (Pillow) gera o PNG de 1024 px; `npx tauri icon icone.png` produz os tamanhos em `src-tauri/icons/`.

## Instaladores / Installers

`npm run tauri build` gera o `.msi` e o `.exe` (NSIS) em `src-tauri/target/release/bundle/`.

## Convenções / Conventions

- Código e textos da interface em português; UTF-8 sem BOM; commits no estilo `tipo(escopo): resumo`.
- Chaves de API (ElevenLabs, Gemini) ficam só em campos `password` do painel e no `hud.config.json`; nunca em log, em mensagem de erro, em captura de tela nem em teste.
  API keys (ElevenLabs, Gemini) live only in `password` fields and in `hud.config.json`; never in logs, error messages, screenshots or tests.
- Sem caminhos pessoais, segredos ou letras de unidade nos arquivos do repositório.
- Mudou comportamento? Acrescente um teste em `tests/`.
