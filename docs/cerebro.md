# Cérebro próprio do Vard (0.8)

Mapa dos caminhos e contratos efetivos da 0.7/0.8. Este documento é a referência
para tarefas que dependem de módulos ainda não entregues ou renomeados.

## Caminhos do núcleo (Python ≥3.13,<3.14)

- `nucleo/vard/cerebro/__init__.py` — pacote do cérebro próprio.
- `nucleo/vard/cerebro/contratos.py` — `Pedido`, `EventoPedido`, `EstadoPedidoInfo`, enums `Origem`, `EstadoPedido`, `TipoEvento`.
- `nucleo/vard/cerebro/sessoes.py` — histórico isolado por sessão, limite de trocas, persistência atômica em `VARD_DADOS/cerebro/sessoes/`.
- `nucleo/vard/cerebro/pedidos.py` — despachante FIFO por sessão, admissão/consulta/cancelamento, recuperação de interrupções no arranque, persistência em `VARD_DADOS/cerebro/pedidos/`.
- `nucleo/vard/config.py` — acessores `pasta_config()`, `pasta_dados()`, `arquivo_config(nome)`, `arquivo_segredos()`. Respeita `VARD_CONFIG`/`VARD_DADOS`.
- `nucleo/vard/central.py` — avisos da ponte (`avisos.jsonl`), registro atômico.
- `nucleo/vard/tarefas.py` — utilitários de tempo e tarefas existentes.

## Contratos mínimos (T1)

| Interface | Contrato |
| --- | --- |
| `Pedido` | `pedido_id:str`, `sessao_id:str`, `origem:voz|painel|telegram`, `texto:str`, `imagem:bytes|None`. |
| `EventoPedido` | `pedido_id`, `sessao_id`, `seq:int`, `tipo:estado|texto|ferramenta|reserva|fim|erro`, `dados:dict`. |
| `EstadoPedidoInfo` | `estado:na_fila|executando|concluido|falhou|cancelado`, IDs, `ultimo_seq`, `resposta`, `erro`, `provedor_usado`, `tarefas`. |
| `Despachante` | `admitir(pedido) -> (info, criado)`, `consultar(id) -> info`, `cancelar(id) -> info`, `processar_fila(sessao_id)`. Persiste antes do 202; um turno por sessão. |

## Módulos ainda não entregues (Parte B / 0.7+)

- Controle local de motores (LM Studio/llama-server): mapear na T5 o caminho efetivo entregue pela 0.6/0.7.
- Ponte/painel/voz conectados ao cérebro: T6 (fora do escopo da Parte A).
- STT/Kokoro próprios: T7/T8 (voz/).
- Telegram próprio: T9.
- Manhã sem OpenJarvis: entregue na T10 como caminho novo opt-in (ver abaixo).
- Retirada do OpenJarvis do caminho padrão: T11.

## Manhã, pesquisa e remoto sem OpenJarvis (T10)

O caminho novo é explícito e convive com o legado: nada muda por padrão até o corte da T11.

- `nucleo/vard/manha.py` — com `consulta = "delegada"` no `manha.toml`, o resumo do dia vem de uma
  consulta delegada (`delegada.consultar`) ao agente/conectores do `delegada.toml`; o pedido
  (`manha.montar_consulta`) pede agenda, tarefas e notícias e nunca pede correio. Sem agente nem
  conector configurado, ou com agente desconhecido na chave `agente`, o resumo declara a ausência
  (`manha.SEM_CONSULTA`); o caminho novo não chama
  `/api/digest/generate`. Sem a chave, segue o `gerar_digest` legado do OpenJarvis.
- `nucleo/vard/pesquisa.py` — com `consulta = "delegada"` no `pesquisa.toml`, a pesquisa roda pelo
  agente do `delegada.toml` em vez de `/v1/managed-agents`; agente desconhecido ou consulta que não
  termina vira falha declarada na tarefa. Sem a chave, segue o caminho legado.
- `nucleo/vard/remoto.py` — `envelope = "openclaw"` normaliza o envelope JSON do CLI do OpenClaw
  (`final`, ou os `payloads`); `{sessao}` vira sessão por tarefa (`sessao = "tarefa"`, padrão) ou o
  perfil antigo (`sessao = "vard"`). O comando não pode usar `--deliver` nem `/hooks/agent`. Timeout
  remoto não repete a chamada: a tarefa falha dizendo que só a espera local terminou.
- Exemplos: `config/examples/{manha,pesquisa,remoto}.example.toml`.
- Provas: `nucleo/tests/test_{manha,pesquisa,remoto}.py` (a manhã/pesquisa delegadas falham se
  aparecer chamada ao OpenJarvis; nenhuma conta real, SSH real ou infraestrutura remota).

## Regras

- Config/dados só pelos acessores da fusão (`vard.config`).
- Nada pessoal no repositório; exemplos e fixtures sintéticos.
- Provas por HTTP/SSE/logs; sem injetar teclado/mouse.
- Commits em português, sem coautoria ou menção a IA.
- E-mail: `142347456+pauloroos@users.noreply.github.com`.