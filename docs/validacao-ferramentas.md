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
| Mesma suíte com `--ignore` nos 7 arquivos | 1582 passaram, 53 falharam, 67 pulados (137 s) | Falhas classificadas abaixo |
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
| OpenJarvis | `src/conectores/openjarvis/cliente.ts` | `tests/` (vários via harness) | pendente (conta real) | — |
| Ponte | `src/conectores/ponte/cliente.ts` | `tests/` (ponte falsa no harness) | pendente (ponte real) | — |
| Nuvem (ElevenLabs/Gemini) | `src/conectores/nuvem/elevenlabs.ts`, `gemini.ts` | — | pendente (chave API) | — |
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
| Avisos | `nucleo/vard/avisos.py`, `src/avisos/central.ts` | `test_avisos.py` | — | — |
| Tarefas | `nucleo/vard/tarefas.py` | `test_tarefas.py` | — | — |
| Manhã | `nucleo/vard/manha.py` | `test_manha.py` | pendente (agente configurado) | — |
| Pesquisa | `nucleo/vard/pesquisa.py` | — | pendente | — |
| Remoto | `nucleo/vard/remoto.py` | `test_remoto.py` | `scripts/provas/prova-delegada.py` | — |

### Atalhos, bandeja e atualização

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Atalhos | `src/config/atalhos.ts`, `src/ui/campo-atalho.ts` | `tests/` (vitest) | pendente (Windows global hotkey) | — |
| Bandeja | `nucleo/vard/bandeja.py` | `test_bandeja.py` | pendente (Windows tray) | — |
| Atualização | `src/atualizacao/release.ts`, `src/ui/aba-atualizacao.ts` | `tests/` (vitest) | pendente (release real) | — |

---

## Classificação das falhas (Linux)

### Só Windows — evidência de API exclusiva

| Arquivo::teste | Motivo | Evidência |
| --- | --- | --- |
| `test_consulta_mcp.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_oficina_mcp.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_preflight.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_preflight_t11.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_prova_reuniao.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_vigia.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_wer.py` (coleta) | `import msvcrt` | `vard/vigia.py:11` |
| `test_mesa_mcp.py::test_abrir_url_normaliza_e_chama_startfile` | `os.startfile` | `mesa_mcp.py:113,146` |
| `test_mesa_mcp.py::test_abrir_url_vazia_pede_o_site` | `os.startfile` | monkeypatch de atributo inexistente em Linux |
| `test_mesa_mcp.py::test_abrir_programa_vazio_pede_o_programa` | `os.startfile` | idem |
| `test_mesa_mcp.py::test_abrir_programa_conhecido` | `os.startfile` | idem |
| `test_mesa_mcp.py::test_apelidos_e_sites_vem_da_config_do_usuario` | `os.startfile` | idem |
| `test_mesa_mcp.py::test_abrir_url_no_navegador_pedido` | `os.startfile` | idem |
| `test_mesa_mcp.py::test_abrir_url_com_navegador_real_barrado_pela_guarda` | `os.startfile` | idem |
| `test_mesa_stdio.py::test_acento_e_emoji_atravessam_o_stdio_com_utf8` | `win32gui` | erro retorna "falta o pacote win32gui" |
| `test_mesa_stdio.py::test_sem_utf8_o_leitor_cp1252_quebra` | `win32gui` | idem |
| `test_modo.py::test_disparar_lanca_intermediario_sem_janela` | `subprocess.DETACHED_PROCESS` | atributo inexistente em Linux |
| `test_primeiro_uso_deteccao.py::test_encontra_cli_no_path_com_espacos` | `powershell` | `FileNotFoundError: 'powershell'` |
| `test_primeiro_uso_deteccao.py::test_lmstudio_instalado_e_fechado_e_lms_ausente` | `powershell` | idem |
| `test_primeiro_uso_deteccao.py::test_lms_encontrado_no_caminho_conhecido` | `powershell` | idem |
| `test_primeiro_uso_deteccao.py::test_quatro_clis_e_orca_presentes` | `powershell` | idem |
| `test_primeiro_uso_deteccao.py::test_orca_no_caminho_do_adaptador_sem_versao` | `powershell` | idem |
| `test_primeiro_uso_deteccao.py::test_gpu_nvidia_com_vram_do_nvidia_smi` | `nvidia-smi` | comando Windows-específico |
| `test_runtime_instalado.py::test_hash_incorreto_falha_antes_de_extrair` | `cmd` | `FileNotFoundError: 'cmd'` |
| `test_runtime_instalado.py::test_destino_fora_do_build_e_recusado` | caminho Windows | lógica de unidade |
| `test_runtime_instalado.py::test_segredo_no_destino_falha` | caminho Windows | idem |
| `test_server.py::test_modo_aceita_origens_do_tauri[http://tauri.localhost]` | `powershell` | script de modo jogo |
| `test_server.py::test_modo_aceita_origens_do_tauri[http://localhost:1420]` | `powershell` | idem |
| `test_server.py::test_modo_dispara_script` | `powershell` | idem |
| `test_server.py::test_modo_script_ausente_vira_503` | `powershell` | idem |
| `test_t11_adaptadores.py::TestVardModoAdaptador::*` (3 testes) | `powershell` / supervisor Windows | adaptador de tarefa agendada |
| `test_t11_adaptadores.py::TestTarefaLogonAdaptador::*` (3 testes) | logon task Windows | idem |
| `test_t11_adaptadores.py::test_vard_modo_nao_sobe_a_bandeja_python_com_supervisor` | supervisor Windows | idem |
| `test_t11_adaptadores.py::test_vard_modo_sobe_a_bandeja_python_no_legado` | bandeja Windows | idem |
| `test_trabalhador.py::test_lancar_usa_intermediario_que_sai_para_nao_ser_descendente_do_mcp` | `CREATE_NEW_PROCESS_GROUP` | atributo inexistente em Linux |
| `test_instalaveis.py::test_npm_no_windows_usa_node_sem_cmd` | `cmd` | teste específico de Windows |
| `test_instalaveis.py::test_terminal_real_visivel_so_com_comando_fixo` | `powershell` | idem |
| Voz (`voz/tests/*`) | `monotonic-alignment-search` requer `Python.h` | dependência C do coqui-tts |
| Reunião (`reuniao/tests/*`) | `pyaudiowpatch` sem wheel Linux | pacote exclusivo Windows |
| Cargo (`src-tauri`) | `libclang.so` ausente | bindgen precisa de libclang-dev |

### Defeito a investigar — falha lógica reproduzível em Linux

| Arquivo::teste | Motivo | Evidência |
| --- | --- | --- |
| `test_config.py::test_nome_invalido_recusado[a\\b.toml]` | Barra invertida é válida em nome de arquivo Linux | teste assume separador Windows |
| `test_delegada.py::test_preparar_pasta_remove_juncao_sem_seguir_o_alvo` | Junção NTFS vs symlink POSIX | comportamento diferente em Linux |
| `test_entrada.py::test_porta_ocupada_sai_com_motivo_identificavel` | `errno.WSAEADDRINUSE` | atributo exclusivo do Windows; Linux usa `EADDRINUSE` |
| `test_remoto.py::test_trava_impede_segunda_conversa` | Trava entre threads com `msvcrt` | fallback de trava não funciona igual em Linux |
| `test_tarefas.py::test_trava_entre_processos` | Trava baseada em `msvcrt` | `tarefas.py:13: import msvcrt` condicional, mas lógica difere |

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
- **Núcleo (Python):** 1582 testes passando em Linux; 53 falhas classificadas (48 só Windows, 5 defeitos a investigar). 7 arquivos nem coletam por `msvcrt`.
- **Voz e Reunião:** Não instalam em Linux (dependências C e pacotes Windows-only). Provas exigem ambiente Windows.
- **Rust/Tauri:** Não compila em Linux sem `libclang-dev`. Provas de WebView2 exigem Windows.
- **Provas reais:** Todas pendentes de infraestrutura, conta ou hardware. Scripts em `scripts/provas/` cobrem cérebro, oficina, reunião e delegada com servidores falsos.

Os 5 defeitos a investigar são candidatos a correção cross-platform ou a ajuste de teste para refletir diferenças legítimas entre Windows e Linux.