# openjarvis-hud

[Leia em português](README.md)

A floating voice widget for [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), built with Tauri 2. A transparent, frameless, always-on-top window with a cyan core that reacts to your voice: you speak, it transcribes, OpenJarvis answers and the answer is spoken back.

![HUD idle](docs/captura-repouso.png) ![HUD speaking](docs/captura-falando.png)

The interface text is in Portuguese (the author's language); the code and this README are open to anyone.

## What it does

- Listens through the microphone (automatic voice detection) or through a global push-to-talk shortcut.
- Wake word: say the assistant's name ("Vard, what time is it"); with push-to-talk the name is not needed.
- Transcription, chat and speech synthesis all go to OpenJarvis (`/v1/speech/transcribe`, `/v1/chat/completions`, `/v1/speech/synthesize`).
- Tray icon, settings panel, optional start with Windows.
- The **Text** button opens OpenJarvis' graphical text interface.
- Optional: the Vard bridge (the author's private setup, `rdl-vard`) adds screen vision and a game mode. Everything works without it, see [docs/ponte-do-vard.md](docs/ponte-do-vard.md) (Portuguese).

## Requirements

- Windows 10 or 11 (64-bit) with WebView2 (included in Windows 11).
- OpenJarvis running at `http://127.0.0.1:8000` **with speech enabled**: see [docs/ligar-a-fala.md](docs/ligar-a-fala.md). Without speech the HUD opens but reports that it cannot listen or talk.
- A microphone.
- For the **Text** button: OpenJarvis' graphical interface (`jarvis gui`) at `http://127.0.0.1:5173`. It needs Node.js and an OpenJarvis source checkout.

## Install

Download the installer from the releases page and run one of them:

- `openjarvis-hud_0.1.0_x64-setup.exe` (NSIS): per-user, no administrator needed. Silent: `openjarvis-hud_0.1.0_x64-setup.exe /S`. Installs to `%LOCALAPPDATA%\openjarvis-hud\`.
- `openjarvis-hud_0.1.0_x64_en-US.msi` (WiX): per-machine, needs administrator. Silent: `msiexec /i openjarvis-hud_0.1.0_x64_en-US.msi /qn`.

To build it yourself: `npm install` and `npm run tauri build` (installers land in `src-tauri/target/release/bundle/`).

## Use

1. Start OpenJarvis with speech on, then the HUD. The status line says "pronto" (ready).
2. **Double-click the core** (or click the microphone button) to open the microphone. Windows may ask for permission the first time.
3. Say "Vard, que horas são". The core turns amber while listening, blue while thinking, and the answer is spoken.

### Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+Space` (hold) | Push-to-talk: speak while holding; the name "Vard" is not required |
| `Ctrl+Alt+Period` | Stop the current speech |
| `Ctrl+Alt+V` | Show or hide the HUD |

All three can be changed in the settings panel (applied after restarting the HUD).

### Buttons

Microphone mute, stop, look at the screen (bridge only), open the text conversation, always on top, settings and compact mode. The tray icon has Show/hide, Always on top, Settings and Quit.

## Configure

Use the gear on the HUD or **Configurações** in the tray menu. The panel covers every field of `hud.config.json` (in `%APPDATA%\dev.openjarvis.hud\`):

| Field | Default | Purpose |
| --- | --- | --- |
| `openjarvis_url` | `http://127.0.0.1:8000` | Where OpenJarvis is |
| `gui_url` | `http://127.0.0.1:5173` | Text interface (Text button) |
| `ponte_url` | `http://127.0.0.1:4700` | Optional bridge |
| `nome`, `variantes` | `vard` and similar spellings | Wake word |
| `idioma` | `pt` | Recognition language |
| `voz`, `velocidade` | `pm_alex`, `1.05` | Speech voice and speed |
| `finish_ms`, `limiar_vad` | `900`, `0.02` | Silence that ends an utterance and microphone sensitivity |
| `sempre_no_topo`, `click_through` | on, off | Always visible; clicks pass through the window |
| `atalhos` | see above | Global shortcuts |
| `instrucao_formato` | short answers | Instruction sent with every question |

URLs outside `127.0.0.1` or `localhost` raise a warning (the HUD sends what you say and, with the bridge, images of your screen; keep everything on your own machine). **Iniciar com o Windows** creates or removes `openjarvis-hud.lnk` in your user Startup folder. **Testar OpenJarvis** checks the server and speech.

## Troubleshooting

- **"núcleo offline"**: OpenJarvis did not answer at `openjarvis_url`. Start the server (`jarvis serve`) and check the address in the panel. The HUD recovers by itself within 5 s.
- **Speech off** (the HUD says so and does not listen): OpenJarvis' `[speech]` is disabled or its backend failed to load. See [docs/ligar-a-fala.md](docs/ligar-a-fala.md) and the server log.
- **Microphone**: if the HUD says the microphone is blocked, allow it under Windows Settings, Privacy, Microphone, then double-click the core again. If it clips the start of sentences or picks up noise, tune `limiar_vad`.
- **The Text button shows nothing useful**: OpenJarvis' text interface is not running at `gui_url`. Start it with `jarvis gui --no-server --no-browser`.
- **A shortcut does nothing**: another program already owns the combination. Change it in the panel and restart the HUD.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.
