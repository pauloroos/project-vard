# Fusão (0.5)

O código do Vard passa a viver só neste repositório.

## Estrutura

- `nucleo/`: ponte, MCPs e módulos (Python >=3.13,<3.14).
- `voz/` e `reuniao/`: serviços opcionais (Python >=3.12,<3.13), cada um com venv e lock próprios.
- `scripts/windows/`: ciclo de vida (modo, bandeja, instalação).
- `scripts/provas/`: provas manuais contra serviços reais.
- `scripts/openjarvis/patches/`: patches do OpenJarvis (Apache-2.0).
- `config/examples/`: exemplos neutros; a configuração real fica fora do repositório.

## Dados e configuração do usuário

Configuração em `%LOCALAPPDATA%\rdl-vard\config` e segredos em `%LOCALAPPDATA%\rdl-vard\segredos.toml`.
`VARD_CONFIG` e `VARD_DADOS` sobrescrevem essas pastas.

## Verificação de publicação

`npm run vazamento` varre arquivos rastreados, novos e o conteúdo do índice (IP, caminho de usuário, unidade,
chaves, e-mail). Se `VARD_AUDITORIA_PESSOAL` apontar para uma lista privada (um termo por linha), os termos
também são procurados e o log mostra só arquivo, linha e regra. Exceções ficam em `scripts/vazamento-permitido.txt`,
sempre por arquivo e trecho.

## Testes

```
uv run --project nucleo --frozen pytest -q nucleo/tests      # núcleo (Python 3.13)
uv run --project voz --frozen pytest -q voz/tests            # voz opcional (Python 3.12)
uv run --project reuniao --frozen pytest -q reuniao/tests    # reunião opcional (Python 3.12)
node --test nucleo/tests/rotas.test.mjs                      # viewer de contingência
npm test; npm run check; npm run build                       # widget
npm run vazamento                                            # busca de dados pessoais antes de publicar
```

## Instalação da máquina (`instalacao.json`)

Fica em `%LOCALAPPDATA%\rdl-vard\instalacao.json` (ou em `VARD_INSTALACAO`). Campos: `raiz_codigo`, `openjarvis_src`,
`openjarvis_home`, `modelo`, `contexto` e `servicos` (por exemplo `voz_python` e `reuniao_python`, para reaproveitar
ambientes já instalados). Exemplo em `config/examples/instalacao.example.json`. `scripts/windows/vard-modo.ps1` aceita
`-Instalacao <arquivo>` e reconhece o formato novo da raiz (`nucleo\server.py`) e o antigo.

## Troca da instalação, com retorno

`scripts/windows/trocar-instalacao.ps1`:

1. `-Candidato`: backup (config e `mcp.json` do OpenJarvis, variáveis de usuário, atalhos), gera a configuração para
   esta raiz e recarrega o OpenJarvis e a ponte por ela, sem trocar a instalação ativa. Rode o preflight.
2. `-Promover`: só com o preflight verde; grava `instalacao.json` de forma atômica e aponta logon e atalhos para esta raiz.
3. `-Reverter`: restaura tudo do backup e recarrega pelo script antigo. Não mexe em tarefas, atas nem schemas de dados.
