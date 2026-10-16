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

## Módulos entregues (T12/T16)

- `nucleo/vard/cerebro/montador.py` — fábrica unificada de adaptadores (`montar_adaptador`) usada por `server.py` e `primeiro_uso/cerebro.py`. Mapeia `tipo` → classe concreta (OpenAICompat, Anthropic, Google, OpenAINativo).
- `nucleo/server.py::_executar_pedido_cerebro` — executor real com credenciais via cofre (`credenciais.ler_para_uso_interno`), fallback para `segredos.chave_lmstudio()` em lmstudio/local. Falhas estruturadas por `_ErroCerebro` (códigos: `cerebro_sem_provedor`, `cerebro_sem_url_base`, `cerebro_sem_modelo`, `cerebro_tipo_desconhecido`).
- `scripts/provas/prova-cerebro.py` — prova integrativa P1/P2/P4 com servidores falsos em portas livres e núcleo real.
- `nucleo/tests/test_prova_cerebro.py` — 6 testes unitários cobrindo sobreposição, FIFO, cancelamento, falha/reserva, telegram próprio e sem provedor.

## Módulos ainda não entregues (Parte B / 0.7+)

- Controle local de motores (LM Studio/llama-server): mapear na T5 o caminho efetivo entregue pela 0.6/0.7.
- Ponte/painel/voz conectados ao cérebro: T6 (fora do escopo da Parte A).
- STT/Kokoro próprios: T7/T8 (voz/).
- Telegram próprio: T9.
- Manhã sem OpenJarvis: T10.
- Retirada do OpenJarvis do caminho padrão: T11.
- P5 (CDP/um app só): pendente de prova real com `npm run tauri dev` + WebView2.

## Regras

- Config/dados só pelos acessores da fusão (`vard.config`).
- Nada pessoal no repositório; exemplos e fixtures sintéticos.
- Provas por HTTP/SSE/logs; sem injetar teclado/mouse.
- Commits em português, sem coautoria ou menção a IA.
- E-mail: `142347456+pauloroos@users.noreply.github.com`.