# Configurações pelo agente

O MCP `configuracoes` usa stdio e os mesmos arquivos da tela: `hud.config.json`
na pasta do aplicativo; `paineis.json`, `perfil.json`, `programas.toml` e
`habilidades.json` em `VARD_CONFIG` ou na pasta padrão de configuração.
O supervisor informa `VARD_HUD_CONFIG_DIR` ao núcleo para distinguir os builds
de desenvolvimento. As gravações usam temporário exclusivo na mesma pasta e
troca atômica. Campos desconhecidos são preservados.

As ferramentas permitem consultar e alterar aparência, vozes, provedores,
receitas da Oficina e apelidos de programas/sites. `listar_habilidades` devolve
somente receitas ligadas, com nome, exemplos e instruções, seguidas das habilidades
de fábrica personalizadas e ligadas (situação `capaz`). `editar_habilidade` também
aceita os IDs de fábrica: nome, exemplos e instruções vão para `fabrica` em
`habilidades.json` e `ligada` usa `desligadas`. Fábrica não se exclui;
`restaurar_habilidade` apaga o ajuste e mantém ligada ou desligada. A validação da tela
e do núcleo usa exemplos compartilhados em `tests/fixtures/ajustes` e
`tests/fixtures/habilidades`. O catálogo de vozes de fábrica também é compartilhado.

Instalar, remover provedor, remover programa, excluir habilidade e trocar quem
responde exigem `confirmado=true`. Sem confirmação, a ferramenta descreve o
efeito para o agente pedir autorização à pessoa. O catálogo informa o tamanho
quando disponível; tamanho desconhecido é indicado explicitamente.

Nenhuma ferramenta recebe chaves ou as devolve. Para autenticação, use a tela
de Configurações. Testar provedor e instalar usam o núcleo por HTTP local,
preservando o estado da instalação no processo do servidor. O teste usa somente
o endereço e a credencial do cadastro salvo e devolve um resultado sanitizado.

Claude Code recebe `mcp.json` por sessão. Os cérebros de API e LM Studio
compartilham conexões aos MCPs locais durante a vida do núcleo; a saída fecha
os processos. O ambiente dos filhos remove contexto e credenciais do agente
que iniciou o núcleo. O agy não oferece configuração MCP por execução na ajuda
da CLI consultada; veja [o contrato das CLIs](cli.md). O Vard preserva a
configuração global dessa CLI.

O aplicativo sonda os arquivos a cada segundo e emite `config-salva`,
`paineis-mudaram` e `habilidades-mudaram`. A tela recarrega as seções e o widget
aplica a aparência, a seleção de cérebro e as vozes principal e reserva. A própria
gravação do app não gera eco no observador. Endereços, credenciais, ouvido e atalhos
mantêm o contrato de reinício indicado pela tela.

## MCPs do usuário na sessão da CLI

Ao abrir o processo do Claude Code, o núcleo grava no `mcp.json` da pasta da sessão os MCPs
locais do Vard e, depois deles, os MCPs **habilitados** em `paineis.json` (`mcps`), lidos por
`vard.mcp_usuario.servidores_do_usuario()`:

| Cadastro | Entrada em `mcpServers` |
| --- | --- |
| stdio (`command`, `args`) | `{"command": ..., "args": [...]}` |
| http (`url`) | `{"type": "http", "url": ...}` |
| http com `credencial_ref` | acrescenta `headersHelper` |

Um MCP desabilitado não entra; um identificador igual ao de um MCP local não o substitui; um
`paineis.json` inválido deixa só os locais. O arquivo nunca leva segredo. Para http com
`credencial_ref` no formato `tipo:id` (tipos `provedor`, `voz` ou `mcp`), o `headersHelper` é
`"<python do núcleo>" -I -m vard.mcp_usuario cabecalhos <tipo:id>`: a CLI o roda ao conectar e
ele lê o cofre do Windows e imprime só no próprio stdout `{"Authorization": "Bearer <valor>"}`.
Uma referência fora do formato é ignorada, sem virar comando. Servidores stdio entram sem a
credencial, pois não há forma segura de entregá-la por esse arquivo. A lista vale para cada
processo novo: uma sessão já aberta passa a vê-la na próxima conversa ou após ficar ociosa.
O Windows-MCP tem cadastro pronto; veja [Windows-MCP](windows-mcp.md).
