# Vard

[Leia em português](README.md) · [Repository](https://github.com/pauloroos/project-vard)

Local voice widget for chatting with AI assistants. Built with Tauri 2.

![HUD idle](docs/captura-repouso.png) ![HUD speaking](docs/captura-falando.png)

## Recommended minimal setup

To get a functional basic conversation, the recommended minimal setup is:

- **Voice**: configure an own voice (Kokoro, XTTS, Edge or Piper) through the Voz tab in settings. Without an own voice, the widget uses OpenJarvis speech synthesis (if available).
- **Provider**: configure at least one LLM provider (OpenAI-compatible, Anthropic or Gemini) in the Modelos tab. The built-in brain requires a provider to respond.
- **OpenJarvis is optional**: Vard works without OpenJarvis when configured with an own voice and a provider. OpenJarvis is an alternative connector.
- **Microphone**: required for voice input. Push-to-talk also works.

First-time use should focus only on basic conversation; full screen (sala), invisible mode and advanced customization remain outside first-time use.

## Basic conversation features

- Microphone listening (VAD) or push-to-talk.
- Speech transcription.
- Responses from the built-in brain (with configured provider) or via OpenJarvis.
- Spoken responses sentence by sentence (own voice or OpenJarvis).
- Interruption cancels transcription, response and speech.
- Session history (question/answer pair).
- Visual status indicators (transcribing, thinking, speaking) and errors.
- Service recovery without closing the app.
- Game mode frees GPU (requires valid configuration).

## Frozen features

> ⚠️ **Frozen features**: the integrations below exist in the code but are not supported in this version. The current focus is reliable basic conversation.
> - Telegram
> - Meeting
> - Agent CLIs
> - Web search
> - Morning brief
> - Full screen (sala)
> - Invisible mode
> - Advanced customization

## Requirements

- Windows 10 or 11 (64-bit) with WebView2.
- A microphone.
- At least one configured LLM provider OR OpenJarvis running.

## Install

Download the installer from the releases page and run one of them:

- `Vard_0.9.6_x64-setup.exe` (NSIS): per-user, no administrator needed. Silent: `Vard_0.9.6_x64-setup.exe /S`. Installs to `%LOCALAPPDATA%\Vard\`.
- `Vard_0.9.6_x64_en-US.msi` (WiX): per-machine, needs administrator. Silent: `msiexec /i Vard_0.9.6_x64_en-US.msi /qn`.

To build it yourself: `npm install` and `npm run tauri build` (installers land in `src-tauri/target/release/bundle/`).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.

## Links

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/ponte-do-vard.md](docs/ponte-do-vard.md) (optional)
