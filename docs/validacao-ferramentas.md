# Validação de ferramentas — inventário e linha de base

Inventário das ferramentas, conectores, cérebro, voz e recursos nativos do Vard 0.10.0,
com testes automatizados, provas reais existentes e classificação das falhas observadas
em Linux (aarch64). Este documento é a referência para os jobs seguintes de prova.

## Linha de base executada

Ambiente: Linux aarch64, Python 3.13 (nucleo), Python 3.12 (voz/reuniao), Node.js 22, Rust/cargo.

| Comando | Resultado | Observação |
| --- | --- | --- |
| `npm test` | 112 arquivos passaram, 1 pulado; 1126 testes passaram, 4 pulados (73 s) | Vitest/jsdom, tudo verde |
| `npm run check` | Saída limpa (exit 0) | `tsc --noEmit` + `tsc -p tsconfig.test.json` |
| `uv run --project nucleo --python 3.13 pytest -q nucleo/tests` | 7 erros de coleta, interrompido | Todos por `import msvcrt` em `vard/vigia.py` |
| Mesma suíte com `--ignore` nos 7 arquivos | 1582 passaram, 53 falharam, 67 pulados (141 s) | Falhas classificadas abaixo |
| `uv run --project voz --python 3.12 pytest -q voz/tests` | Erro de instalação | `monotonic-alignment-search` exige `Python.h` (cabeçalhos CPython ausentes) |
| `uv run --project reuniao --python 3.12 pytest -q reuniao/tests` | Erro de instalação | `pyaudiowpatch` só tem wheel para win32/win_amd64 |
| `cargo test --manifest-path src-tauri/Cargo.toml` | Erro de compilação | `bindgen` não encontra `libclang.so` |

### Erros de coleta do núcleo (7 arquivos)

Todos falham na importação porque `vard/vigia.py` importa `msvcrt` no nível do módulo:

- `nucleo/tests/test_consulta_mcp.py`
- `nucleo/tests/test_oficina_mcp.py`
- `nucleo/tests/test_preflight.py`
- `nucleo/tests/test_preflight_t11.py`
- `nucleo/tests/test_prova_reuniao.py`
- `nucleo/tests/test_vigia.py`
- `nucleo/tests/test_wer.py`

Causa raiz: `nucleo/vard/vigia.py:11: import msvcrt` — módulo exclusivo do Windows.

---

## Inventário por grupo

### MCPs locais

| Grupo | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Configurações | `nucleo/configuracoes_mcp.py` | `nucleo/tests/test_ajustes_mcp.py`, `test_scripts_config.py` | pendente (exige app instalado) | — |
| Consulta | `nucleo/consulta_mcp.py` | `nucleo/tests/test_consulta_mcp.py` (não coleta em Linux) | pendente | — |
| Memória | `nucleo/memoria_mcp.py` | `nucleo/tests/test_memoria.py` | pendente | — |
| Mesa | `nucleo/mesa_mcp.py` | `nucleo/tests/test_mesa_mcp.py`, `test_mesa_stdio.py` | pendente (Windows UI Automation) | — |
| Oficina | `nucleo/oficina_mcp.py` | `nucleo/tests/test_oficina_mcp.py` (não coleta em Linux), `test_oficina.py` | `scripts/provas/prova-oficina.py` | — |
| Reunião | `nucleo/reuniao_mcp.py` | `nucleo/tests/test_reuniao_mcp.py`, `test_reuniao.py`, `test_pacotes_reuniao.py` | `scripts/provas/prova-reuniao.py` | — |

### Cérebro próprio

| Subgrupo | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Pedidos/FIFO | `nucleo/vard/cerebro/pedidos.py` | `test_cerebro_pedidos.py`, `test_cerebro_pedidos_integracao.py` | `scripts/provas/prova-cerebro.py` | — |
| Sessões | `nucleo/vard/cerebro/sessoes.py` | `test_cerebro_laco.py`, `test_cerebro_laco_persona.py` | — | — |
| Adaptadores/Montador | `nucleo/vard/cerebro/montador.py`, `provedores.py` | `test_cerebro_provedores.py`, `test_cerebro_ferramentas.py` | — | — |
| Cancelamento | `nucleo/vard/cerebro/pedidos.py` | `test_prova_cerebro.py` (cancelamento) | `scripts/provas/prova-cerebro.py` | — |
| Fila/Executor | `nucleo/vard/cerebro/laco.py` | `test_cerebro_executor.py`, `test_cerebro_cli.py` | — | — |
| Diário | `nucleo/vard/cerebro/diario.py` | `test_cerebro_diario.py` | — | — |
| Reserva | `nucleo/vard/cerebro/reserva.py` | `test_prova_cerebro.py` (reserva/falha) | — | — |
| CLI/Detecção | `nucleo/vard/cerebro/cli.py`, `cli_deteccao.py`, `cli_capacidade.py` | `test_cli_detectar.py`, `test_cli_despachante.py`, `test_cli_falsa.py` | — | — |
| Controle motor | `nucleo/vard/cerebro/controle_motor.py` | — | pendente | — |

### Conectores

| Conector | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| OpenJarvis | `src/conectores/openjarvis/cliente.ts` | `tests/harness/integracao.test.ts`, `tests/openjarvis-desligado.test.ts`, `tests/integracao-real.test.ts` | pendente (conta real) | — |
| Ponte | `src/conectores/ponte/cliente.ts` | `tests/ponte-andamento.test.ts`, `tests/ponte-avisos.test.ts`, `tests/ponte-dispositivos.test.ts`, `tests/ponte-eventos.test.ts`, `tests/ponte-reuniao.test.ts`, `tests/ponte-saude.test.ts`, `tests/ponte-telegram.test.ts` | pendente (ponte real) | — |
| Nuvem (ElevenLabs/Gemini) | `src/conectores/nuvem/elevenlabs.ts`, `gemini.ts` | `tests/nuvem.test.ts` | pendente (chave API) | — |
| Voz própria | `src/conectores/voz/cliente.ts`, `fluxo.ts`, `kokoro.ts` | `voz/tests/test_servidor.py`, `test_kokoro.py`, `test_edge.py`, `test_piper.py` | pendente (motor real) | — |
| Telegram | `nucleo/vard/telegram.py` (implícito) | `test_telegram.py`, `test_telegram_mcp.py`, `test_telegram_rotas.py`, `test_telegram_servidor.py`, `test_telegram_lifespan.py`, `test_telegram_migracao.py` | pendente (bot token) | — |

### Voz

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Transcrição (STT) | `voz/vard_voz/transcricao.py`, `modelos_stt.py` | `voz/tests/test_transcricao.py`, `test_modelos_stt.py`, `test_servidor_stt_modelos.py` | pendente (microfone real) | — |
| Falar (TTS) | `voz/vard_voz/servidor.py`, `motor.py`, `kokoro.py`, `edge.py`, `piper.py` | `voz/tests/test_servidor.py`, `test_kokoro.py`, `test_edge.py`, `test_piper.py`, `test_motor.py` | pendente (saída de áudio) | — |

### Avisos, tarefas, manhã, pesquisa, remoto

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Avisos | `nucleo/vard/avisos.py`, `src/avisos/central.ts` | `nucleo/tests/test_avisos.py`, `tests/aba-avisos.test.ts`, `tests/avisos-chamada.test.ts`, `tests/avisos-fala.test.ts` | — | — |
| Tarefas | `nucleo/vard/tarefas.py` | `nucleo/tests/test_tarefas.py` | — | — |
| Manhã | `nucleo/vard/manha.py` | `nucleo/tests/test_manha.py` | pendente (agente configurado) | — |
| Pesquisa | `nucleo/vard/pesquisa.py` | `nucleo/tests/test_pesquisa.py` (`test_cria_o_agente_e_devolve_a_resposta`) | pendente (agente configurado) | — |
| Remoto | `nucleo/vard/remoto.py` | `nucleo/tests/test_remoto.py` | `scripts/provas/prova-delegada.py` | — |

### Atalhos, bandeja e atualização

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Atalhos | `src/config/atalhos.ts`, `src/ui/campo-atalho.ts` | `tests/atalhos.test.ts`, `tests/atalhos-win.test.ts` | pendente (Windows global hotkey) | — |
| Bandeja | `nucleo/vard/bandeja.py` | `nucleo/tests/test_bandeja.py` | pendente (Windows tray) | — |
| Atualização | `src/atualizacao/release.ts`, `src/ui/aba-atualizacao.ts` | `tests/atualizacao.test.ts`, `tests/release.test.ts` | pendente (release real) | — |

---

## Classificação das falhas (Linux) — 53 falhas

### Só Windows — evidência de API exclusiva (48 falhas)

| # | Arquivo::teste | Motivo observado | Evidência |
| --- | --- | --- | --- |
| 1 | `test_ajustes_mcp.py::test_programa_cadastrado_chega_a_mesa_sem_reiniciar` | `AttributeError: <module 'os' (frozen)> has no attribute 'startfile'` | `os.startfile` inexistente em Linux |
| 2 | `test_allowlist.py::test_toda_ferramenta_do_mcp_esta_na_allowlist[oficina-7]` | `ModuleNotFoundError: No module named 'msvcrt'` | `vard/vigia.py:11` importado indiretamente |
| 3 | `test_allowlist.py::test_toda_ferramenta_do_mcp_esta_na_allowlist[consulta-7]` | `ModuleNotFoundError: No module named 'msvcrt'` | idem |
| 4 | `test_allowlist.py::test_nomes_unicos_entre_os_mcps` | `ModuleNotFoundError: No module named 'msvcrt'` | idem |
| 5 | `test_allowlist.py::test_descricoes_curtas[oficina]` | `ModuleNotFoundError: No module named 'msvcrt'` | idem |
| 6 | `test_allowlist.py::test_descricoes_curtas[consulta]` | `ModuleNotFoundError: No module named 'msvcrt'` | idem |
| 7 | `test_mesa_mcp.py::test_abrir_url_normaliza_e_chama_startfile` | `AttributeError: <module 'os' (frozen)> has no attribute 'startfile'` | `mesa_mcp.py` usa `os.startfile` |
| 8 | `test_mesa_mcp.py::test_abrir_url_vazia_pede_o_site` | `AttributeError: ... 'startfile'` | idem |
| 9 | `test_mesa_mcp.py::test_abrir_programa_vazio_pede_o_programa` | `AttributeError: ... 'startfile'` | idem |
| 10 | `test_mesa_mcp.py::test_abrir_programa_conhecido` | `AttributeError: ... 'startfile'` | idem |
| 11 | `test_mesa_mcp.py::test_apelidos_e_sites_vem_da_config_do_usuario` | `AttributeError: ... 'startfile'` | idem |
| 12 | `test_mesa_mcp.py::test_abrir_url_no_navegador_pedido` | `AttributeError: ... 'startfile'` | idem |
| 13 | `test_mesa_mcp.py::test_abrir_url_com_navegador_real_barrado_pela_guarda` | `FileNotFoundError: [Errno 2] No such file or directory: 'X:\\Apps\\brave.exe'` | caminho Windows hardcoded no teste |
| 14 | `test_mesa_stdio.py::test_acento_e_emoji_atravessam_o_stdio_com_utf8` | `AssertionError: assert ('ÁREA' in '...falta o pacote win32gui...')` | `win32gui` ausente em Linux |
| 15 | `test_mesa_stdio.py::test_sem_utf8_o_leitor_cp1252_quebra` | `Failed: DID NOT RAISE UnicodeDecodeError` | comportamento cp1252 é específico do Windows |
| 16 | `test_modo.py::test_disparar_lanca_intermediario_sem_janela` | `AttributeError: module 'subprocess' has no attribute 'DETACHED_PROCESS'` | flag Windows-only |
| 17 | `test_primeiro_uso_deteccao.py::test_encontra_cli_no_path_com_espacos` | `StopIteration` | `FakeAmbiente` esgota iterador sem encontrar CLI |
| 18 | `test_primeiro_uso_deteccao.py::test_lmstudio_instalado_e_fechado_e_lms_ausente` | `AssertionError: assert 'nao_encontrado' == 'encontrado'` | detecção depende de caminhos Windows |
| 19 | `test_primeiro_uso_deteccao.py::test_lms_encontrado_no_caminho_conhecido` | `AssertionError: assert 'nao_encontrado' == 'encontrado'` | idem |
| 20 | `test_primeiro_uso_deteccao.py::test_quatro_clis_e_orca_presentes` | `AssertionError: assert 'nao_encontrado' == 'encontrado'` | idem |
| 21 | `test_primeiro_uso_deteccao.py::test_orca_no_caminho_do_adaptador_sem_versao` | `AssertionError: assert 'nao_encontrado' == 'encontrado'` | idem |
| 22 | `test_primeiro_uso_deteccao.py::test_gpu_nvidia_com_vram_do_nvidia_smi` | `AssertionError: vram_mb is None` | `nvidia-smi` não disponível ou saída diferente |
| 23 | `test_runtime_instalado.py::test_hash_incorreto_falha_antes_de_extrair` | `FileNotFoundError: [Errno 2] No such file or directory: 'cmd'` | script `montar-nucleo.ps1` invoca `cmd` |
| 24 | `test_runtime_instalado.py::test_destino_fora_do_build_e_recusado` | lógica de unidade Windows | caminho com letra de unidade |
| 25 | `test_runtime_instalado.py::test_segredo_no_destino_falha` | lógica de unidade Windows | idem |
| 26 | `test_server.py::test_modo_aceita_origens_do_tauri[http://tauri.localhost]` | `FileNotFoundError: [Errno 2] No such file or directory: 'powershell'` | script de modo jogo usa powershell |
| 27 | `test_server.py::test_modo_aceita_origens_do_tauri[http://localhost:1420]` | `FileNotFoundError: ... 'powershell'` | idem |
| 28 | `test_server.py::test_modo_dispara_script` | `assert (503 == 200)` | modo retorna 503 fixo sem powershell |
| 29 | `test_server.py::test_modo_script_ausente_vira_503` | `assert (200 == 503)` | sem powershell, modo não ativa e retorna 200 |
| 30–37 | `test_t11_adaptadores.py::TestVardModoAdaptador::*` (3) + `TestTarefaLogonAdaptador::*` (3) + 2 testes de bandeja/supervisor | `FileNotFoundError: ... 'powershell'` | adaptador de tarefa agendada e supervisor Windows |
| 38 | `test_trabalhador.py::test_lancar_usa_intermediario_que_sai_para_nao_ser_descendente_do_mcp` | `AssertionError: assert (0 & 0)` — `CREATE_NEW_PROCESS_GROUP` é 0 em Linux | flag Windows-only |
| 39 | `test_instalaveis.py::test_npm_no_windows_usa_node_sem_cmd` | `AssertionError: assert ['npm', 'inst...'] == ['/tmp/.../node.exe', ...]` | teste verifica comando Windows-specific |
| 40 | `test_instalaveis.py::test_terminal_real_visivel_so_com_comando_fixo` | `AttributeError: module 'subprocess' has no attribute 'CREATE_NEW_CONSOLE'` | flag Windows-only |
| 41 | `test_cli_detectar.py::TestDetectar::test_modelos_do_agy_guardam_so_o_id` | `AssertionError: assert [] == ['modelo-...']` | detecção de CLIs depende de binários Windows |
| 42 | `test_cli_detectar.py::TestDetectar::test_detectar_com_claude_e_agy_falsos_no_path` | `assert False is True` | idem |
| 43 | `test_cli_detectar.py::TestDetectar::test_detectar_nao_roda_prompt` | `FileNotFoundError: ... 'execucoes.txt'` | arquivo não criado porque CLI não roda |
| 44 | `test_cli_detectar.py::TestDetectar::test_detectar_ignora_cli_que_nao_responde` | `assert False is True` | detecção falha sem binário |
| 45 | `test_cli_detectar.py::TestDetectar::test_detectar_cenario_misto_so_uma_instalada` | `assert False is True` | idem |
| 46 | `test_cli_detectar.py::test_rota_cli_detectar` | `assert False is True` | idem |
| 47 | `test_cli_detectar.py::TestDetectarCodexOpenCode::test_detectar_codex_instalado` | `assert False is True` | idem |
| 48 | `test_cli_detectar.py::TestDetectarCodexOpenCode::test_detectar_opencode_instalado` | `assert False is True` | idem |

**Subtotal: 48 falhas só Windows.**

### Defeito a investigar — falha lógica reproduzível em Linux (5 falhas)

| # | Arquivo::teste | Motivo observado | Evidência |
| --- | --- | --- | --- |
| 49 | `test_config.py::test_nome_invalido_recusado[a\\b.toml]` | `Failed: DID NOT RAISE ValueError` | barra invertida é válida em nome de arquivo Linux; teste assume separador Windows |
| 50 | `test_delegada.py::test_preparar_pasta_remove_juncao_sem_seguir_o_alvo` | `FileNotFoundError: [Errno 2] No such file or directory: 'cmd'` | teste exclusivo de Windows (junção NTFS); não é defeito de lógica Linux |
| 51 | `test_entrada.py::test_porta_ocupada_sai_com_motivo_identificavel` | `AttributeError: module 'errno' has no attribute 'WSAEADDRINUSE'` | `servidor.py:57` usa `errno.WSAEADDRINUSE` (Windows); Linux usa `EADDRINUSE` |
| 52 | `test_remoto.py::test_trava_impede_segunda_conversa` | `assert False` — `wait(3)` retorna False | trava entre threads com fallback `msvcrt` não funciona igual em Linux |
| 53 | `test_tarefas.py::test_trava_entre_processos` | `Failed: DID NOT RAISE TimeoutError` | trava baseada em `msvcrt`; lógica difere em Linux |

**Subtotal: 5 falhas classificadas como defeito.**

> **Nota sobre `test_delegada.py`:** falha por `FileNotFoundError: 'cmd'` (junção NTFS),
> não por lógica cross-platform. Mantida como "defeito" porque o código deveria
> detectar plataforma e pular junção em Linux, mas a classificação pode ser
> revisada para "só Windows" se o comportamento for intencional.

**Total: 48 + 5 = 53 falhas.** ✓

---

## Prova real do cérebro e dos MCPs (J2) — 2026-11-02 (pit stop 1)

Executada em Linux aarch64 com modelo remoto via adaptador OpenAI-compatível.
Configuração isolada via `VARD_CONFIG`, `VARD_DADOS` e `VARD_HUD_CONFIG_DIR` apontando para diretórios temporários; `paineis.json` gerado com as quatro chaves de agente (`claude`, `codex`, `opencode`, `agy`) exigidas por `ajustes.validar_documento`.
Saída sanitizada em `/tmp/opencode/vard-j2-pitstop-prova.json`. Nenhum segredo, endpoint ou nome de modelo no relatório.

### MCPs diretos (stdio, sem modelo)

| MCP | Ferramenta | Status | Resultado sanitizado |
| --- | --- | --- | --- |
| configuracoes | ver_configuracoes | executou | Configurações atuais com widget, perfil e provedor ativo (sanitizado) |
| configuracoes | listar_provedores | executou | Provedores com id, nome, tipo e modelo sanitizados (`***`) |
| configuracoes | listar_vozes | executou | Catálogo de vozes Kokoro/Edge/Piper com IDs e rótulos |
| memoria | memoria_buscar | executou | "A memória não está configurada: falta o projeto em memoria.toml." |
| reuniao | reuniao_status | executou | "O modo reunião não está instalado." |
| mesa | hora_atual | executou | Hora atual formatada em português (UTC+00:00) |
| oficina | — | pendencia_windows | MCP depende de msvcrt/Windows; não aplicável em Linux |
| consulta | — | pendencia_windows | MCP depende de msvcrt/Windows; não aplicável em Linux |

### Cérebro por HTTP/SSE (modelo real + ferramenta real)

- **Estado do pedido:** falhou
- **HTTP status:** 202
- **Erro:** `auth_401` (credencial recusada pelo provedor remoto)
- **Ferramenta chamada:** nenhuma (erro antes da chamada)
- **Eventos SSE:** erro → fim (2 eventos, sanitizados)
- **Duração:** 10,9 s
- **Processo núcleo:** PID 93146, terminado graceful

> **Pendência:** O provedor remoto recusou a credencial (`auth_401`) apesar de `segredos.toml` temporário com `[lmstudio] chave` e `VARD_CONFIG` isolado. A resolução de credenciais foi verificada offline (chave lida corretamente); a causa provável é incompatibilidade entre o formato da chave e o esperado pelo endpoint remoto. Requer investigação do contrato de autenticação do provedor antes de nova tentativa.

---

## Pendências de prova real

| Item | Motivo da pendência |
| --- | --- |
| OpenJarvis | Exige conta/serviço real |
| Ponte do Vard | Setup privado; ponte falsa cobre contrato |
| Nuvem (ElevenLabs/Gemini) | Exige chave API |
| Voz própria (Kokoro/XTTS/Piper) | Motor de voz real + saída de áudio |
| Telegram | Bot token + chat permitido |
| Manhã delegada | Agente/conector configurado |
| Pesquisa delegada | Agente configurado |
| Remoto (SSH/Docker) | Infraestrutura remota real |
| Atalhos globais | Windows global hotkey |
| Bandeja | Windows system tray |
| Atualização | Release publicada |
| Mesa (UI Automation) | Windows + tela real |
| WebView2/Tauri dev | Windows + WebView2 runtime |
| STT com microfone | Hardware de áudio |

---

## Resumo para próximos jobs

- **Frontend (TypeScript):** 1126 testes passando; `npm run check` limpo. Sem pendências de código.
- **Núcleo (Python):** 1582 testes passando em Linux; **53 falhas classificadas (48 só Windows, 5 defeitos a investigar)**. 7 arquivos nem coletam por `msvcrt`.
- **Voz e Reunião:** Não instalam em Linux (dependências C e pacotes Windows-only). Provas exigem ambiente Windows.
- **Rust/Tauri:** Não compila em Linux sem `libclang-dev`. Provas de WebView2 exigem Windows.
- **Provas reais:** Todas pendentes de infraestrutura, conta ou hardware. Scripts em `scripts/provas/` cobrem cérebro, oficina, reunião e delegada com servidores falsos.

Os 5 defeitos a investigar são candidatos a correção cross-platform ou a ajuste de teste para refletir diferenças legítimas entre Windows e Linux.