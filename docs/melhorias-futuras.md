# Melhorias futuras

Itens combinados para depois da 1.0. Não são compromisso de data nem fazem parte de versão em andamento.

## Mac e Linux

Hoje o Vard é só para Windows. A base ajuda: o Tauri roda nos três sistemas, e o núcleo e o serviço de voz são
Python, em boa parte portáteis. O que prende ao Windows e teria de ganhar equivalente:

- Credenciais no cofre do Windows: Keychain no Mac, Secret Service no Linux.
- Atalhos globais, bandeja, início com o sistema e migração da instalação.
- Caminhos dos ambientes Python (`.venv\Scripts\python.exe`) e o script `vard-modo.ps1`.
- WebView2: WebKit no Mac e WebKitGTK no Linux, com diferenças de comportamento a testar.
- Instaladores: `.dmg` assinado e notarizado pela Apple; `.deb` ou AppImage no Linux.
- Controle do computador (mesa e Windows-MCP): API de Acessibilidade no Mac (com permissão do usuário);
  X11 ou Wayland no Linux.
- Transcrição: sem CUDA no Mac, o faster-whisper roda na CPU.

Ordem sugerida: Linux primeiro (sem assinatura da Apple), depois Mac.

## Falas fixas em outros idiomas

As falas fixas (`src/fala/falas.ts`) existem só em português. Com o idioma escolhido na configuração, cada
idioma teria a sua tabela.
