# openjarvis-hud

Widget de voz flutuante (Tauri 2) para o OpenJarvis: janela transparente, sempre no topo, com atalho global de push-to-talk.

Projeto em construção. README completo (PT-BR e EN) virá depois.

## Como testar

Pré-requisito: OpenJarvis em `http://127.0.0.1:8000` com `[speech]` ligado.

1. `npm install` e `npm run tauri dev`.
2. Clique no núcleo uma vez (o clique libera o microfone). A linha de estado mostra "pronto".
3. Diga "Vard, que horas são". O núcleo fica âmbar ouvindo, azul pensando e a resposta sai em voz alta (voz `pm_alex`).
4. Ou segure `Ctrl+Alt+Space` e fale: com push-to-talk o nome "Vard" é dispensado.
5. Para interromper uma fala: `Ctrl+Alt+Period` ou clique no núcleo enquanto ele fala.

No `tauri dev`, o front fala com o OpenJarvis por um proxy do Vite (`/oj`), porque o CORS do OpenJarvis recusa a origem `localhost:1420`. O alvo padrão é `http://127.0.0.1:8000`; mude com `VITE_OJ_ALVO`. O app instalado usa `openjarvis_url` do `hud.config.json`.

### Sem voz humana (servidor falso)

`npm run harness` sobe um OpenJarvis falso em `http://127.0.0.1:8765` (transcrição fixa, resposta "Agora são 13h.", senoide de 0,3 s). Use `VITE_OJ_ALVO=http://127.0.0.1:8765 npm run tauri dev` e aperte o push-to-talk por 1 s em silêncio.

### Ponte do Vard (opcional)

Com a ponte do Vard no ar (`http://127.0.0.1:4700`) o HUD ganha o botão Tela e o modo jogo. Sem ela funciona igual. Veja [docs/ponte-do-vard.md](docs/ponte-do-vard.md). `PONTE=4700 npm run harness` sobe uma ponte falsa para testar.

### Testes

- `npm test`: unitários e integração contra o servidor falso (em processo).
- `HUD_REAL=1 HUD_REAL_WAV=<um WAV dizendo "Preflight"> npm run test:real`: prova contra o OpenJarvis de verdade (transcrever, perguntar, sintetizar).

Licença: MIT.
