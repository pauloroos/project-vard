# Vard

[Leia em português](README.md) · [Repository](https://github.com/pauloroos/project-vard)

Vard is a local voice interface (floating widget) for assistants; the first connector is [OpenJarvis](https://github.com/open-jarvis/OpenJarvis). Built with Tauri 2. A transparent, frameless, always-on-top window with a cyan core that reacts to your voice: you speak, it transcribes, OpenJarvis answers and the answer is spoken back.

![HUD idle](docs/captura-repouso.png) ![HUD speaking](docs/captura-falando.png)

The interface text is in Portuguese (the author's language); the code and this README are open to anyone.

Independent project, not affiliated with OpenJarvis or Stanford.

## What it does

- Listens through the microphone (automatic voice detection) or through a global push-to-talk shortcut.
- Wake word: say the assistant's name ("Vard, what time is it"); with push-to-talk the name is not needed.
- Transcription, chat and speech synthesis all go to OpenJarvis (`/v1/speech/transcribe`, `/v1/chat/completions`, `/v1/speech/synthesize`).
- Tray icon, settings panel in its own window (tabs Geral, Voz, Atalhos, Ponte and Modelos), optional start with Windows.
- Three sizes (or the side in pixels, 160 to 800) and a compact mode that leaves only the hologram.
- Full screen ("sala") on a monitor of your choice: a large vortex, what you said, the answer in large type and a clock.
- Pick the model among the ones OpenJarvis exposes.
- The **Text** button opens OpenJarvis' graphical text interface.
- Optional: the Vard bridge (the author's private setup, `rdl-vard`) adds screen vision and a game mode. Everything works without it, see [docs/ponte-do-vard.md](docs/ponte-do-vard.md) (Portuguese).
- Optional: your own voice service (any local TTS engine that follows a small contract) speaks the answer sentence by sentence, starting before the whole answer is synthesized. See [Own voice](#own-voice-optional).

## Requirements

- Windows 10 or 11 (64-bit) with WebView2 (included in Windows 11).
- OpenJarvis running at `http://127.0.0.1:8000` **with speech enabled**: see [docs/ligar-a-fala.md](docs/ligar-a-fala.md). Without speech the HUD opens but reports that it cannot listen or talk.
- A microphone.
- For the **Text** button: OpenJarvis' graphical interface (`jarvis gui`) at `http://127.0.0.1:5173`. It needs Node.js and an OpenJarvis source checkout.

## Install

Download the installer from the releases page and run one of them:

- `Vard_0.2.0_x64-setup.exe` (NSIS): per-user, no administrator needed. Silent: `Vard_0.2.0_x64-setup.exe /S`. Installs to `%LOCALAPPDATA%\Vard\`.
- `Vard_0.2.0_x64_en-US.msi` (WiX): per-machine, needs administrator. Silent: `msiexec /i Vard_0.2.0_x64_en-US.msi /qn`.

To build it yourself: `npm install` and `npm run tauri build` (installers land in `src-tauri/target/release/bundle/`).

## Use

1. Start OpenJarvis with speech on, then the HUD. The status line asks you to double-click the core.
2. **Double-click the core** (or click the microphone button) to open the microphone. Windows may ask for permission the first time.
3. Say "Vard, que horas são". The core turns cyan while listening, amber while thinking, and the answer is spoken.

### Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+Space` (hold) | Push-to-talk: speak while holding; the name "Vard" is not required |
| `Ctrl+Alt+Period` | Stop the current speech |
| `Ctrl+Alt+V` | Show or hide the widget |
| `Ctrl+Alt+,` | Open or close the settings |
| `Ctrl+Alt+E` | Start listening (opens the microphone) or toggle mute |
| `Ctrl+Alt+F` | Toggle full screen (sala) |

All of them can be changed in the Atalhos tab: click the field and press the new combination (Ctrl, Alt or Win plus a key). The panel rejects duplicates and marks any shortcut Windows refused (another program owns it). Changes apply after restarting Vard.

![Shortcuts tab](docs/painel-atalhos.png)

### Buttons

Microphone mute, stop, look at the screen (bridge only), open the text conversation, always on top, settings and compact mode. In compact mode only the hologram shows: the buttons appear while the mouse is over the widget and fade 2 s after it leaves (with click-through on they never appear). The tray icon has Show/hide, Always on top, Settings, Full screen and Quit.

## Configure

Use the gear, **Configurações** in the tray menu or `Ctrl+Alt+,`. The panel opens in its own window with the tabs Geral, Voz, Atalhos, Ponte and Modelos. Saving applies size, compact mode, always on top, click-through, your name and the model right away; addresses, voice, listening and shortcuts apply after a restart (the panel says which). The fields are those of `hud.config.json` (if the file becomes unreadable the HUD starts with the defaults and keeps the original as `hud.config.json.invalido`; in `%APPDATA%\io.github.pauloroos.vard\`):

| Field | Default | Purpose |
| --- | --- | --- |
| `openjarvis_url` | `http://127.0.0.1:8000` | Where OpenJarvis is |
| `gui_url` | `http://127.0.0.1:5173` | Text interface (Text button) |
| `ponte_url` | `http://127.0.0.1:4700` | Optional bridge (empty disables) |
| `voz_url` | `http://127.0.0.1:4710` | Optional own voice service (empty disables; while it is down, OpenJarvis' voice is used) |
| `nome`, `variantes` | `vard` and similar spellings | Wake words: `nome` plus `variantes` (with another name the default Vard variants are dropped) |
| `usuario` | empty | Name used in the greeting ("Oi, Ana."); empty says just "Oi." |
| `idioma` | `pt` | Recognition language |
| `voz`, `velocidade` | `pm_alex`, `1.05` | Speech voice and speed |
| `finish_ms`, `limiar_vad` | `900`, `0.02` | Silence that ends an utterance and microphone sensitivity |
| `sempre_no_topo`, `click_through` | on, off | Always visible; clicks pass through the window |
| `tamanho`, `tamanho_px` | `medio`, `320` | Widget size: `pequeno` (240 px), `medio` (320), `grande` (480) or `personalizado` (`tamanho_px`, 160 to 800) |
| `compacto` | off | Hologram only; buttons show on hover |
| `modelo` | empty | OpenJarvis model (empty = the first one it lists) |
| `sala_monitor` | empty | Full-screen monitor (empty = primary) |
| `atalhos` | see above | Global shortcuts: `falar`, `parar`, `mostrar`, `config`, `escuta`, `sala` |
| `instrucao_formato` | short answers | Instruction sent with every question |

URLs outside `127.0.0.1` or `localhost` raise a warning (the HUD sends what you say and, with the bridge, images of your screen; keep everything on your own machine). **Iniciar com o Windows** creates or removes `Vard.lnk` in your user Startup folder. **Testar OpenJarvis** checks the server and speech.

## Full screen (sala)

![Full-screen sala](docs/sala.png)

`Ctrl+Alt+F` or **Tela cheia** in the tray opens a black borderless window filling the monitor chosen in Geral → Janela: the large vortex, what you said, the answer in large type and a clock. It is only a mirror: the widget, which can stay on another monitor, still listens and speaks. `Esc`, the shortcut or the tray close it. If the chosen monitor is disconnected, it opens on the primary one and the widget says so.

The widget is always on top and may cover the sala if both are on the same monitor: put the sala on another monitor or move the widget to a corner.

## Models

The **Modelos** tab lists the models OpenJarvis exposes (`/v1/models`) and lets you pick the main one; "Automático" uses the first one. If the Vard bridge reports a fallback model, it shows there. **Testar** asks a short question and shows how long it took. Switching providers (OmniRouter, subscriptions, LM Studio) is OpenJarvis configuration: Vard only picks among what it offers. If the chosen model disappears from OpenJarvis, Vard uses the first one.

## Own voice (optional)

By default OpenJarvis synthesizes the whole answer before playback starts. With a local voice service at `voz_url`,
the HUD splits the answer into sentences, plays the first one as soon as its first audio chunk arrives and requests
the next sentence while the current one is still playing. The fixed phrases ("Voltei." and the others) go through it
too and are cached.

Any TTS engine works. The service needs two routes on `127.0.0.1`:

- `GET /saude` returns `{"pronta": true, "voz": "voice name", ...}`.
- `POST /falar` takes `{"texto": "one sentence", "velocidade": 1.05}` (up to 400 characters). With `Accept: audio/pcm`
  it answers `200` with streamed 16-bit mono little-endian PCM (`Transfer-Encoding: chunked`) at 24 kHz (headers
  `X-Taxa`, `X-Canais`, `X-Formato`). `400` for empty or too long text, `503 {"erro": "aquecendo"}` while the model loads.
- CORS open to `http://tauri.localhost` (installed app) and `http://localhost:1420` (`tauri dev`).

If the service is down, takes more than 8 s or rejects a sentence, that sentence is spoken with OpenJarvis' voice and
nothing changes on screen. The full contract is in [docs/voz-propria.md](docs/voz-propria.md) (Portuguese).

## Troubleshooting

- **"núcleo offline"**: OpenJarvis did not answer at `openjarvis_url`. Start the server (`jarvis serve`) and check the address in the panel. The HUD recovers by itself within 5 s.
- **Speech off** (the HUD says so and does not listen): OpenJarvis' `[speech]` is disabled or its backend failed to load. See [docs/ligar-a-fala.md](docs/ligar-a-fala.md) and the server log.
- **Microphone**: if the HUD says the microphone is blocked, allow it under Windows Settings, Privacy, Microphone, then double-click the core again. If it clips the start of sentences or picks up noise, tune `limiar_vad`.
- **The Text button shows nothing useful**: OpenJarvis' text interface is not running at `gui_url`. Start it with `jarvis gui --no-server --no-browser`.
- **A shortcut does nothing**: another program already owns the combination. The Atalhos tab marks the shortcut that did not register; change it and restart Vard.
- **Full screen opened on the wrong monitor**: the chosen monitor was disconnected, so it opened on the primary one. Pick it again in Geral → Janela.

## Connectors

Vard talks to assistants through connectors. Today there is only one, OpenJarvis (`src/conectores/openjarvis/cliente.ts`). Others are welcome: implement the `Conector` interface in `src/conectores/conector.ts` (`saude`, `modelos`, `definirModelo`, `transcrever`, `perguntar`, `sintetizar`). `definirModelo` stores the preferred model (empty = the first from `modelos()`) and takes effect on the next question. Warning: in the panel's Models tab, picking a non-default model, or pressing Test on it, may make the LLM server (for example LM Studio) load a second model into the GPU and use its memory.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.
