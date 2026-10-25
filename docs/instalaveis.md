# Instalação dos provedores

Em **Núcleo → Instalar ou conectar**, o Vard lista os provedores que ainda não estão
instalados ou cadastrados; um provedor já cadastrado (do mesmo tipo) não volta como sugestão.
Antes de instalar, mostra o comando, os requisitos e o tamanho aproximado quando o
fornecedor o informa. Modelos são baixados separadamente. A instalação começa apenas
depois de **Confirmar instalação** e o núcleo aceita uma por vez.

O progresso pode ser fechado e reaberto por **Atualizar instalações → Ver andamento**.
**Cancelar instalação** interrompe o instalador; arquivos ou alterações que ele já
tenha feito podem permanecer. Uma falha permite tentar novamente.

Ao concluir, o Vard abre o cadastro com nome, tipo e endereço preenchidos; escolha
o modelo e salve. O OpenJarvis já possui um card fixo e abre a escolha do seu modelo.
Uma CLI sem sessão mostra **Falta entrar na conta** quando sua sonda oficial consegue
verificar esse estado. Se não houver sonda confiável, o card pede para conferir o login.
**Entrar na conta** abre um PowerShell visível apenas ao clicar. O usuário conduz o login.

Antigravity oferece as instruções oficiais para instalação manual. Gemini CLI pode
ser instalado e autenticado, mas ainda não possui adaptador no Vard: para responder
por aqui, configure a API Google ou use Antigravity. Codex e OpenCode mantêm seu uso
em tarefas delegadas.

OpenJarvis usa `scripts/windows/instalar-openjarvis.ps1` quando o script acompanha o
núcleo. Suas pastas precisam estar definidas no `instalacao.json`, como descrito em
[Fusão e instalação](fusao.md). Sem o script disponível, o card oferece instruções.

## Contrato do núcleo

| Rota | Resultado |
| --- | --- |
| `GET /instalaveis` | `{itens: [...]}` com catálogo, presença, login e andamento |
| `POST /instalaveis/{id}/instalar` | Inicia com corpo `{"confirmado":true}` |
| `GET /instalaveis/{id}/andamento` | `{id, estado, linhas}` |
| `POST /instalaveis/{id}/cancelar` | Solicita cancelamento e devolve o andamento |
| `POST /instalaveis/{id}/login` | Abre o terminal de login da CLI instalada |

IDs: `lmstudio`, `ollama`, `claude`, `codex`, `opencode`, `gemini`, `agy`, `openjarvis`.
Estados: `aguardando`, `instalando`, `concluido`, `falhou`, `cancelado`. A consulta de
andamento não instala nada. Estados ficam na memória do núcleo, até seu encerramento.
IDs desconhecidos devolvem 404, falta de confirmação/instalação manual devolve 400
e instalação simultânea devolve 409. As rotas usam a proteção de origem e loopback
já existente no núcleo.

O módulo `vard.instalaveis.GerenciadorInstalaveis` oferece `listar()`,
`instalar(id, confirmado=True)`, `andamento(id)` e `cancelar(id)`. Seu executor recebe
`(comando, emitir_linha, evento_cancelamento)` e devolve um código de saída. Os testes
injetam esse executor e as sondas de presença/login; nenhum instalador real é chamado.

O executor real usa argumentos em lista e `shell=False`; no Windows chama o npm
pelo Node e seu `npm-cli.js`. Retira `CLAUDE*`, `ANTHROPIC*` e `ORCA_AGENT*` do ambiente
dos filhos. O progresso publica etapas e percentuais, sem saída bruta que possa conter
diretórios ou credenciais. O cancelamento confere PID e instante de criação dos
processos próprios antes de encerrá-los.
