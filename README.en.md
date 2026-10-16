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
- Tray icon, settings panel in its own window (tabs Geral, Voz, Atalhos, Modelos, Sistema and Atualização), optional start with Windows.
- Three sizes (or the side in pixels, 160 to 800) and a compact mode that leaves only the hologram.
- Full screen ("sala") on a monitor of your choice: a large vortex, what you said, the answer in large type and a clock.
- Pick the model among the ones OpenJarvis exposes.
- Conversation mode: after an answer it keeps listening without the wake word for 20 s (adjustable); "pode parar de me ouvir" or "vou entrar em reunião" mute the microphone until you turn it back on.
- Choice of voice: your own voice (XTTS, with the service's voice list), OpenJarvis' (Kokoro) or, if you want and with your own key, ElevenLabs and Gemini TTS; a Ouvir button plays a sample sentence.
- Invisible mode: the widget disappears and only shows while a conversation lasts.
- The button bar opens on the side away from the monitor edge (above when the widget is at the bottom).
- Atualização tab: checks GitHub for the newest release only when you ask and installs from there.
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

- `Vard_0.9.0_x64-setup.exe` (NSIS): per-user, no administrator needed. Silent: `Vard_0.9.0_x64-setup.exe /S`. Installs to `%LOCALAPPDATA%\Vard\`.
- `Vard_0.9.0_x64_en-US.msi` (WiX): per-machine, needs administrator. Silent: `msiexec /i Vard_0.9.0_x64_en-US.msi /qn`.

To build it yourself: `npm install` and `npm run tauri build` (installers land in `src-tauri/target/release/bundle/`).

## Use

1. Start OpenJarvis with speech on, then the HUD. The status line asks you to double-click the core.
2. **Double-click the core** (or click the microphone button) to open the microphone. Windows may ask for permission the first time.
3. Say "Vard, que horas são". The core turns cyan while listening, amber while thinking, and the answer is spoken.

Only one instance runs at a time: opening Vard again brings the window to the front. During development use `npm run tauri:dev` to coexist with the installed Vard.

### What's new in 0.4.0

- **Listening and speaking split:** "Don't listen" turns the microphone off; "Don't speak" shows the answer as text only. Buttons on the widget, tray items and the `Ctrl+Alt+N` shortcut; the state is remembered.
- **Notice center (with the private install):** a discreet unread counter and a "Notices" tab in the panel (see result, mark as read). Nothing is spoken unless you turn on "Speak notices" (never while "Don't speak" is on).
- **Waiting:** a discreet badge with the number of running tasks; hover for the list.
- **Meeting:** a "Meeting" tab (start, stop, make minutes, last meeting); while a meeting runs the widget stays quiet and shows "meeting".
- **Panel:** recognition language as a list and a "What I can do" tab.

### Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+Space` (hold) | Push-to-talk: speak while holding; the name "Vard" is not required |
| `Ctrl+Alt+.` | Stop the current speech |
| `Ctrl+Alt+V` | Show or hide the widget |
| `Ctrl+Alt+P` | Open or close the settings |
| `Ctrl+Alt+L` | Start listening (opens the microphone) or toggle mute |
| `Ctrl+Alt+N` | Toggle "Don't speak" (answers as text only) |
| `Ctrl+Alt+F` | Toggle full screen (sala) |

All of them can be changed in the Atalhos tab: click the field and press the new combination (Ctrl, Alt or Win plus a key). The panel rejects duplicates and marks any shortcut Windows refused (another program owns it). Changes apply after restarting Vard.

![Shortcuts tab](docs/painel-atalhos.png)

### Conversation mode

After Vard answers, the channel stays open for 20 s: you can keep talking without repeating the name. Each utterance restarts the timer; when it runs out the name is required again. The timer is `conversa_ms` (milliseconds; `0` turns the mode off).

To end it early, say one of these expressions (with or without the name in front; they are matched in Portuguese): "pode parar de me ouvir", "pare de me ouvir", "para de me ouvir", "deixa de me ouvir", "não precisa mais me ouvir", "vou entrar em reunião", "entrando em reunião", "estou em reunião", "tô em reunião", "modo silencioso" or "pode descansar". Vard confirms, closes the channel and mutes the microphone. To listen again, click the microphone button, press `Ctrl+Alt+L` or double-click the core. Asking about a meeting ("tenho reunião hoje?") ends nothing.

### Buttons

Microphone mute, stop, look at the screen (bridge only), open the text conversation, always on top, settings and compact mode. In compact mode only the hologram shows: the buttons appear while the mouse is over the widget and fade 2 s after it leaves (with click-through on they never appear). With the widget in the lower half of the monitor, the button bar sits above the hologram. The tray icon has Show/hide, Always on top, Modo invisível, Settings, Full screen and Quit.

## Configure

Use the gear, **Configurações** in the tray menu or `Ctrl+Alt+P`. The panel opens in its own window with the tabs Geral, Voz, Atalhos, Modelos, Sistema and Atualização. Saving applies size, compact mode, always on top, click-through, your name and the model right away; addresses, voice, call name, language, format instruction, listening and shortcuts apply after a restart (the panel says which). In the file, shortcuts use the key names `Period` and `Comma` (the screen shows `.` and `,`). The fields are those of `hud.config.json` (if the file becomes unreadable the HUD starts with the defaults and keeps the original as `hud.config.json.invalido`; in `%APPDATA%\io.github.pauloroos.vard\`):

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
| `conversa_ms` | `20000` | Conversation mode: ms of listening without the name after an answer (0 turns it off) |
| `voz_provedor`, `voz_propria` | `propria`, empty | Voice provider (`propria`, `openjarvis`, `elevenlabs`, `gemini`) and the own service's voice (empty = its current one) |
| `elevenlabs_chave`, `elevenlabs_voz`, `gemini_chave`, `gemini_voz` | empty, `Kore` | Optional cloud providers; only called when chosen as the provider and a key is set |
| `invisivel` | off | Invisible mode: shows only during a conversation |
| `atualizacao_ao_abrir` | off | Check GitHub for a release when the Atualização tab opens |
| `modelo` | empty | OpenJarvis model (empty = the first one it lists) |
| `sala_monitor` | empty | Full-screen monitor (empty = primary) |
| `atalhos` | see above | Global shortcuts: `falar`, `parar`, `mostrar`, `config`, `escuta`, `sala` |
| `instrucao_formato` | short answers | Instruction sent with every question |

URLs outside `127.0.0.1` or `localhost` raise a warning (the HUD sends what you say and, with the bridge, images of your screen; keep everything on your own machine). **Iniciar com o Windows** creates or removes `Vard.lnk` in your user Startup folder. **Testar OpenJarvis** checks the server and speech.

## Full screen (sala)

![Full-screen sala](docs/sala.png)

`Ctrl+Alt+F` or **Tela cheia** in the tray opens a black borderless window filling the monitor chosen in Geral → Janela: the large vortex, what you said, the answer in large type and a clock. It is only a mirror: the widget, which can stay on another monitor, still listens and speaks. `Esc`, the shortcut or the tray close it. If the chosen monitor is disconnected, it opens on the primary one and the widget says so.

The widget hides while the sala is open and comes back when it closes (same position); it keeps running hidden: microphone, shortcuts and conversation keep working.

## Models

The **Modelos** tab lists the models OpenJarvis exposes (`/v1/models`) and lets you pick the main one; "Automático" uses the first one. If the Vard bridge reports a fallback model, it shows there. With the bridge up, the list comes in two groups: LM Studio (local) and OmniRouter (cloud). **Testar** asks a short question and shows how long it took. Switching providers (OmniRouter, subscriptions, LM Studio) is OpenJarvis configuration: Vard only picks among what it offers. If the chosen model disappears from OpenJarvis, Vard uses the first one. Warning: picking a non-default model, or pressing Testar on it, may make the LLM server (for example LM Studio) load a second model into the GPU and use its memory.

## System

The **Sistema** tab shows the state of the Vard bridge (the author's private setup: mode, whether OpenJarvis is up and how many tasks are open), refreshed every 5 s while the tab is open. It has three buttons:

- **Ligar** brings everything up (model, core, bridge and voice).
- **Modo jogo** turns everything off and takes the models off the GPU.
- **Desligar** also stops the model server and the tray. The bridge goes down with it, so the tab shows "fora" until you start it again some other way.

Each button asks for confirmation: the first click changes the label to **Confirmar** and a second click within 5 s runs it (another button, or the timeout, starts over). Buttons that make no sense in the current mode are disabled, and without the bridge none of them works; the rest of Vard is unaffected. The bridge address (`ponte_url`) is in the Geral tab.

## Invisible mode

Turn it on with the **Modo invisível** checkbox in the panel or the tray item. While on, the widget is transparent and the cursor passes through it; it only shows while Vard is thinking or speaking, while the conversation-mode channel is open or when you reveal it, and hides 1.5 s after the last reason. "Listening" does not count, because the voice detector fires on any noise before it knows you called Vard.

In this mode `Ctrl+Alt+V` and the tray's Show/hide reveal or hide the widget immediately. Without "always on top" the revealed widget may end up behind other windows: keep that option on if you want to see it every time.

## Update

The **Atualização** tab shows the installed version and checks the project's newest GitHub release **only when you click Verificar agora** or, if you tick the box (`atualizacao_ao_abrir`), once when the tab opens. Vard never checks on its own in the background.

If a newer version exists, the tab shows the date and notes and offers **Baixar e instalar**. Vard only talks to GitHub (`api.github.com`, `github.com` and the `*.githubusercontent.com` hosts that serve the files), downloads the `-setup.exe` to `%TEMP%\Vard\`, checks its size and, when the GitHub API reports a sha256, the hash too, runs the installer and closes Vard. The installer is not signed: SmartScreen may warn. The `.msi` is not installed from here (it needs administrator): download it from the release page.

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

Optional parts of the contract: `GET /vozes` returns `{"vozes": ["name", ...], "atual": "name"}` and feeds the Voz tab's list; the `voz` field of `/falar` picks a voice from that list (without it the service's current voice is used). A service without `/vozes` keeps working, just without the list.

If the service is down, takes more than 8 s or rejects a sentence, that sentence is spoken with OpenJarvis' voice and
nothing changes on screen. The full contract is in [docs/voz-propria.md](docs/voz-propria.md) (Portuguese).

### Other voice providers

In the Voz tab the provider can be `propria`, `openjarvis` (Kokoro, OpenJarvis' voice), `elevenlabs` or `gemini`. The last two are optional and in the cloud: they are only called when chosen as the provider and a key is set (password fields; the key never goes to the log), and the text of the spoken lines goes to the vendor. For ElevenLabs also set the voice id; Gemini's default voice is `Kore` and it ignores the speed. The **Ouvir** button plays a sample sentence with the chosen provider.

With a cloud provider on, the fixed phrases ("Voltei." and the others) are synthesized on it once at startup to warm the cache; that sends those short texts to the vendor. With `propria` or `openjarvis` nothing leaves your machine.

## Troubleshooting

- **"núcleo offline"**: OpenJarvis did not answer at `openjarvis_url`. Start the server (`jarvis serve`) and check the address in the panel. The HUD recovers by itself within 5 s.
- **Speech off** (the HUD says so and does not listen): OpenJarvis' `[speech]` is disabled or its backend failed to load. See [docs/ligar-a-fala.md](docs/ligar-a-fala.md) and the server log.
- **Microphone**: if the HUD says the microphone is blocked, allow it under Windows Settings, Privacy, Microphone, then double-click the core again. If it clips the start of sentences or picks up noise, tune `limiar_vad`.
- **The Text button shows nothing useful**: OpenJarvis' text interface is not running at `gui_url`. Start it with `jarvis gui --no-server --no-browser`.
- **A shortcut does nothing**: another program already owns the combination. The Atalhos tab marks the shortcut that did not register; change it and restart Vard.
- **Vard no longer hears me**: you said a conversation-mode closing phrase; click the microphone, press `Ctrl+Alt+L` or double-click the core.
- **The widget vanished**: invisible mode is on; `Ctrl+Alt+V` or Show/hide in the tray reveal it, and the panel checkbox or the tray item turn the mode off.
- **The downloaded installer did not open**: SmartScreen may have blocked it; run the file in `%TEMP%\Vard\` and choose "Run anyway".
- **Full screen opened on the wrong monitor**: the chosen monitor was disconnected, so it opened on the primary one. Pick it again in Geral → Janela.

## Connectors

Vard talks to assistants through connectors. Today there is only one, OpenJarvis (`src/conectores/openjarvis/cliente.ts`). Others are welcome: implement the `Conector` interface in `src/conectores/conector.ts` (`saude`, `modelos`, `definirModelo`, `transcrever`, `perguntar`, `sintetizar`). `definirModelo` stores the preferred model (empty = the first from `modelos()`) and takes effect on the next question. Warning: in the panel's Models tab, picking a non-default model, or pressing Test on it, may make the LLM server (for example LM Studio) load a second model into the GPU and use its memory.

## Core (bridge, MCPs and services)

The Python core, the optional voice and meeting services and the Windows scripts live in this repository (`nucleo/`, `voz/`, `reuniao/`, `scripts/`). User configuration and data stay outside it (`%LOCALAPPDATA%dl-vard`, or `VARD_CONFIG` and `VARD_DADOS`). Layout, tests and the switch-over with rollback are described in [docs/fusao.md](docs/fusao.md) (in Portuguese).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.
