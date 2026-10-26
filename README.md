# Vard

[Read in English](README.en.md) · [Repositório](https://github.com/pauloroos/project-vard)

Widget de voz local para conversa com assistentes de IA. Feito com Tauri 2.

![HUD em repouso](docs/captura-repouso.png) ![HUD falando](docs/captura-falando.png)

## Configuração mínima recomendada

Para ter uma conversa básica funcional, a configuração mínima recomendada é:

- **Voz**: configurar uma voz própria (Kokoro, XTTS, Edge ou Piper) pela aba Voz nas configurações. Sem voz própria, o widget usa a síntese do OpenJarvis (se disponível).
- **Provedor**: configurar pelo menos um provedor de LLM (OpenAI-compatível, Anthropic ou Gemini) na aba Modelos. O cérebro próprio precisa de um provedor para responder.
- **OpenJarvis é opcional**: o Vard funciona sem OpenJarvis quando configurado com voz própria e um provedor. O OpenJarvis é um conector alternativo.
- **Microfone**: necessário para entrada por voz. Push-to-talk também funciona.

O primeiro uso deve focar apenas na conversa básica; sala (tela cheia), modo invisível e personalização avançada ficam fora do primeiro uso.

## Funcionalidades da conversa básica

- Escuta por microfone (VAD) ou push-to-talk.
- Transcrição de fala.
- Resposta do cérebro próprio (com provedor configurado) ou via OpenJarvis.
- Fala da resposta frase por frase (voz própria ou OpenJarvis).
- Interrupção cancela transcrição, resposta e fala.
- Histórico da sessão (par pergunta/resposta).
- Indicadores visuais de estado (transcrevendo, pensando, falando) e erros.
- Recuperação de serviços sem fechar o app.
- Modo jogo libera GPU (requer configuração válida).

## Funcionalidades congeladas

> ⚠️ **Funcionalidades congeladas**: as integrações abaixo existem no código mas não são suportadas nesta versão. O foco atual é a conversa básica confiável.
> - Telegram
> - Reunião
> - CLIs de agentes
> - Pesquisa web
> - Resumo da manhã
> - Sala (tela cheia)
> - Modo invisível
> - Personalização avançada

## Requisitos

- Windows 10 ou 11 (64 bits) com WebView2.
- Um microfone.
- Pelo menos um provedor de LLM configurado OU OpenJarvis rodando.

## Instalar

Baixe o instalador na página de releases e rode um dos dois:

- `Vard_0.9.6_x64-setup.exe` (NSIS): instala só para o seu usuário, sem pedir administrador. Silencioso: `Vard_0.9.6_x64-setup.exe /S`. Fica em `%LOCALAPPDATA%\Vard\`.
- `Vard_0.9.6_x64_en-US.msi` (WiX): instala para a máquina toda e exige administrador. Silencioso: `msiexec /i Vard_0.9.6_x64_en-US.msi /qn`.

Para gerar você mesmo: `npm install` e `npm run tauri build` (os instaladores saem em `src-tauri/target/release/bundle/`).

## Desenvolvimento

Veja [CONTRIBUTING.md](CONTRIBUTING.md). Licença: MIT.

## Links

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/ponte-do-vard.md](docs/ponte-do-vard.md) (opcional)
