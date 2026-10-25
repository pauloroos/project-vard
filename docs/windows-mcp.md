# Windows-MCP (controle do computador)

O Windows-MCP é um servidor MCP **de terceiros** (projeto CursorTouch, licença MIT) que dá ao
assistente ferramentas para clicar, digitar, rolar, trocar de janela e ler a árvore da tela no
Windows. O Vard não o inclui nem o instala: oferece apenas um cadastro pronto na aba
**Ferramentas (MCP)**.

> **Aviso.** Habilitado, o Windows-MCP permite ao assistente clicar e digitar no computador com
> o acesso do seu usuário, inclusive em ações que não se desfazem. Habilite só se confiar no
> cérebro que responde e desabilite quando não precisar.

## Fonte conferida

- Repositório: <https://github.com/CursorTouch/Windows-MCP> (README, seção de instalação).
- Pacote: <https://pypi.org/project/windows-mcp/> (nome `windows-mcp`, licença MIT,
  `requires-python >=3.14`; versão 0.8.8 na consulta de 17/10/2026).
- Comando recomendado pelo projeto: `uvx windows-mcp serve` (transporte stdio, o padrão).
- Requisitos informados: Windows 10 ou 11, Python 3.14+ e o gerenciador `uv`
  (que fornece o `uvx`). A primeira execução baixa dependências e pode demorar.

## Cadastro pronto

**Adicionar Windows-MCP (controle do computador)** abre o modal de cadastro já preenchido:

| Campo | Valor |
| --- | --- |
| Identificador | `windows-mcp` |
| Nome | `Windows-MCP (controle do computador)` |
| Tipo | stdio |
| Comando | `uvx` |
| Argumentos | `windows-mcp serve` |

O modal mostra o aviso acima. Nada é gravado até **Salvar**, e o cadastro salvo fica
**desabilitado**: o uso começa só depois de **Habilitar** no card. Se já existir um cadastro com
o identificador `windows-mcp`, o botão abre a edição dele em vez de duplicar. Os campos podem ser
ajustados antes de salvar (por exemplo, `--exclude-tools` do próprio Windows-MCP).

## Quem recebe

Os MCPs habilitados chegam ao Claude Code pelo `mcp.json` da sessão; veja
[Configurações pelo agente](mcp-configuracoes.md#mcps-do-usuário-na-sessão-da-cli). O agy e os
cérebros de API ainda não recebem os MCPs do usuário.
