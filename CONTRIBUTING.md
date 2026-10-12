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
npx tsc --noEmit          # tipos
cargo test --manifest-path src-tauri/Cargo.toml
```

`HUD_REAL=1 HUD_REAL_WAV=<um WAV dizendo "Preflight"> npm run test:real` prova contra um OpenJarvis de verdade (transcrever, perguntar, sintetizar).

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

Sobe um OpenJarvis falso em `http://127.0.0.1:8765` (transcrição fixa, resposta "Agora são 13h.", senoide de 0,3 s). Use `VITE_OJ_ALVO=http://127.0.0.1:8765 npm run tauri dev` e aperte o push-to-talk por 1 s em silêncio. `PONTE=4700 npm run harness` acrescenta uma ponte falsa.
Starts a fake OpenJarvis at `http://127.0.0.1:8765`. Use it with `VITE_OJ_ALVO`. `PONTE=4700` adds a fake bridge.

## Ícone / Icon

`python scripts/gerar-icone.py icone.png` (Pillow) gera o PNG de 1024 px; `npx tauri icon icone.png` produz os tamanhos em `src-tauri/icons/`.

## Instaladores / Installers

`npm run tauri build` gera o `.msi` e o `.exe` (NSIS) em `src-tauri/target/release/bundle/`.

## Convenções / Conventions

- Código e textos da interface em português; UTF-8 sem BOM; commits no estilo `tipo(escopo): resumo`.
- Sem caminhos pessoais, segredos ou letras de unidade nos arquivos do repositório.
- Mudou comportamento? Acrescente um teste em `tests/`.
