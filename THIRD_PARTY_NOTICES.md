# Terceiros

O Vard é MIT (ver [`LICENSE`](LICENSE)). Os itens abaixo são de terceiros.

## OpenJarvis

- Projeto: OpenJarvis — <https://github.com/open-jarvis/OpenJarvis>
- Licença: Apache-2.0
- Versão usada: commit fixado `ccf02ec7bdda2e2b344eeb8dd986d742ff458acc`,
  que `scripts/windows/instalar-openjarvis.ps1` aplica ao clonar (volta ao pin
  sempre que o `-Atualizar` não couber).

## Patches em `scripts/openjarvis/patches/`

Os quatro arquivos abaixo são trechos derivados do OpenJarvis. Seguem a
licença Apache-2.0 e preservam o copyright e a atribuição aos autores do
OpenJarvis, como manda a Seção 4 (Redistribuição) dessa licença:

- `openjarvis-telegram-allowed-chat-ids.patch`
- `openjarvis-telegram-marca.patch`
- `openjarvis-chat-extra.patch`
- `openjarvis-open-browser.patch`

O cabeçalho da Apache License 2.0 está em
[`scripts/openjarvis/patches/LICENSE`](scripts/openjarvis/patches/LICENSE).

## Resto do repositório

Todo o restante dos arquivos deste repositório está sob a licença MIT
([`LICENSE`](LICENSE)).
