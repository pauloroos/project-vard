# CLIs como cérebro — contrato observado (T13)

Sondagem real feita em 2026-10-15 com `claude` (Claude Code) e `agy` (Antigravity) já logados, usando modelos baratos e pergunta trivial ("responda apenas: ola"). Pasta de teste: `.coordenacao/0.8-cli-sonda/` (fora do repo). Nenhum dado pessoal foi gravado.

## Resumo por CLI

| Item | claude (Claude Code) | agy (Antigravity) |
| --- | --- | --- |
| argv base | `claude -p --input-format stream-json --output-format stream-json --verbose` | `agy --input-format stream-json --output-format stream-json --model <modelo> --print ""` |
| Modelo barato testado | padrão da instalação (opus-5-5 via gateway); `claude-haiku-5-5` não existe neste ambiente | `gemini-3.8-flash-low` |
| Linha de entrada (stdin) | `{"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}` | `{"event":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}` |
| Evento de início | `{"type":"system","subtype":"init",...,"tools":[...],"mcp_servers":[...]}` | `{"event":"init","init":{"model":...,"tools":[...],"permission_mode":...}}` |
| Delta de texto | `{"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}` | `{"event":"step_update","step_update":{"state":"ACTIVE","step_type":"agent_response","text_delta":"..."}}` |
| Uso de ferramenta | `{"type":"assistant","message":{"content":[{"type":"server_tool_use","name":"...","id":"..."}]}}` | `{"event":"assistant","message":{"content":[{"type":"tool_use","name":"...","id":"..."}]}}` |
| Resultado de ferramenta | `{"type":"assistant","message":{"content":[{"type":"web_search_tool_result","tool_use_id":"..."}]}}` | `{"event":"assistant","message":{"content":[{"type":"tool_result","tool_use_id":"..."}]}}` |
| Fim de turno | `{"type":"result","stop_reason":"end_turn","result":"...","num_turns":N}` | `{"event":"result","result":{"status":"SUCCESS","response":"...","num_turns":N}}` |
| Erro de login / auth | `{"type":"result","is_error":true,"api_error_status":400,"result":"API Error: ..."}` | `{"event":"result","result":{"status":"ERROR","error":"...","response":""}}` |
| Multi-turno no mesmo processo | SIM: duas mensagens `{"type":"user",...}` enviadas sequencialmente mantiveram contexto ("Seu nome é teste") | NÃO TESTADO diretamente; `--conversation <id>` ou `--continue` existem para retomar sessão por ID |
| Interrupção sem matar processo | capabilities incluem `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `interrupt_send_now_v1` (SDK); no modo `-p` cada linha stdin dispara um turno e o processo encerra ao fechar stdin | Não há flag explícita de interrupção no help; encerrar stdin fecha o turno/processo |
| Perfil / instruções | Lê `CLAUDE.md` e `AGENTS.md` do cwd; pode receber `--append-system-prompt-file` | Lê `AGENTS.md` do cwd; `--agent <nome>` carrega agente definido; `agy agents` lista agentes disponíveis |
| MCP | `--mcp-config <arquivo>` + `--strict-mcp-config`; lista servidores no evento `init` | `agy mcp list/add/remove`; MCPs são globais por usuário (não por execução); listar é só leitura nesta tarefa |
| Permissão / yolo | `--dangerously-skip-permissions` ativa yolo; sem ele, modo `-p` nega ações que pedem permissão | `--dangerously-skip-permissions` ativa yolo; `permission_mode` vem no `init` (`request-review` padrão) |
| Observações | Hooks de SessionStart podem atrasar o primeiro evento útil (~50 s neste ambiente); filtrar eventos `hook_started`/`hook_response` | Resposta veio em ~3 s; `step_update` com `text_delta` traz o texto incremental; `result.response` traz o texto final completo |

## Formato de entrada

### claude
```json
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"pergunta do usuário"}]}}
```

### agy
```json
{"event":"user","message":{"role":"user","content":[{"type":"text","text":"pergunta do usuário"}]}}
```

Ambos leem uma linha NDJSON por turno no modo `stream-json`. O `agy` exige o campo `"event"` no envelope; o `claude` usa `"type"`.

## Eventos de saída mapeados

| Categoria | claude | agy |
| --- | --- | --- |
| início (ferramentas/MCPs) | `type=system, subtype=init` | `event=init` |
| texto (delta) | `type=assistant, content[].type=text` | `event=step_update, step_update.step_type=agent_response, text_delta` |
| ferramenta (uso) | `type=assistant, content[].type=server_tool_use` | `event=assistant, content[].type=tool_use` |
| ferramenta (resultado) | `type=assistant, content[].type=*_tool_result` | `event=assistant, content[].type=tool_result` |
| fim de turno | `type=result, stop_reason=end_turn` | `event=result, result.status=SUCCESS` |
| erro | `type=result, is_error=true` | `event=result, result.status=ERROR` |

## Multi-turno e interrupção

- **claude**: aceita múltiplas linhas `{"type":"user",...}` no mesmo processo stdin; mantém contexto entre turnos. Interrupção via SDK (`interrupt_cancel_queued_v1`) ou fechando stdin.
- **agy**: cada linha `{"event":"user",...}` dispara um turno; para multi-turno usar `--conversation <id>` ou `--continue`. Interrupção: fechar stdin.

## Perfil e MCP

- **claude**: perfil vai em `CLAUDE.md`/`AGENTS.md` no cwd da sessão e opcionalmente via `--append-system-prompt-file`; MCPs via `--mcp-config <arquivo>`.
- **agy**: perfil vai em `AGENTS.md` no cwd; `--agent <nome>` escolhe um agente já definido. A ajuda da CLI não oferece `--mcp-config` nem opção equivalente por sessão: `agy mcp` gerencia os servidores globais do usuário. O Vard não altera essa configuração global, portanto os MCPs locais do Vard só são conectados automaticamente ao Claude Code e aos cérebros de API. O `mcp.json` da sessão fica disponível para inspeção, mas o agy não o consome automaticamente.

## Notas de implementação

- Filtrar eventos `hook_started`/`hook_response`/`informational` do claude antes de processar; só `init`, `assistant` e `result` importam para o cérebro.
- No agy, `step_update` com `state=ACTIVE` e `step_type=agent_response` traz deltas; `state=DONE` com `duration_seconds` e `usage` fecha o passo.
- Ambos retornam `num_turns` no evento final; usar para métricas e timeout.
- O `agy` retorna `response` completo no `result`; o `claude` retorna `result` como string e também como último `assistant.content[].text`.
