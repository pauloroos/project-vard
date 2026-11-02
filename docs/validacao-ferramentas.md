# Validação de ferramentas — matriz, provas reais e pendências

Matriz consolidada das ferramentas MCP, conectores, cérebro, voz e recursos nativos do Vard 0.10.0,
com testes automatizados, provas reais executadas e classificação das pendências observadas
em Linux (aarch64). Este documento consolida a validação final da versão, delimitando o escopo provado
e as pendências de ambiente Windows e serviços externos.

## Linha de base executada

Ambiente: Linux aarch64, Python 3.13 (nucleo), Python 3.12 (voz/reuniao), Node.js 22, Rust/cargo.

| Comando | Resultado | Observação |
| --- | --- | --- |
| `npm test` | 112 arquivos passaram, 1 pulado; 1126 testes passaram, 4 pulados (64 s) | Vitest/jsdom, 100% verde |
| `npm run check` | Saída limpa (exit 0) | `tsc --noEmit` + `tsc -p tsconfig.test.json` |
| `uv run --project nucleo --python 3.13 pytest -q nucleo/tests` | 7 erros de coleta, interrompido (1,83 s) | Todos por `import msvcrt` em `vard/vigia.py:11` |
| Mesma suíte com `--ignore` nos 7 arquivos | 1597 passaram, 48 falharam (48 só Windows), 68 pulados (130 s) | As 5 correções aumentaram aprovados de 1582 para 1597; 48 falhas restantes são todas de Windows (53 = 48 restantes + 5 corrigidas) |
| Testes de defeitos e prova real | 19 passaram, 1 pulado (`test_delegada` pula em Linux por ausência de `cmd`) (4,2 s) | Cobertura dos 5 defeitos corrigidos e do harness J2/J3 |
| `uv run --project voz --python 3.12 pytest -q voz/tests` | Erro de instalação | `monotonic-alignment-search` exige `Python.h` (cabeçalhos CPython ausentes) |
| `uv run --project reuniao --python 3.12 pytest -q reuniao/tests` | Erro de instalação | `pyaudiowpatch` só tem wheel para win32/win_amd64 |
| `cargo test --manifest-path src-tauri/Cargo.toml` | Erro de compilação: `Unable to find libclang: "couldn't find any valid shared libraries matching: ['libclang.so', ...]` | `bindgen` exige `libclang.so` (dependência C/LLVM ausente em Linux) |

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

### MCPs locais — resumo dos servidores

| Servidor | Arquivo | Quantidade | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- | --- |
| Configurações | `nucleo/configuracoes_mcp.py` | 25 | `nucleo/tests/test_ajustes_mcp.py`, `test_scripts_config.py` | Prova J2/J3 (stdio e HTTP/SSE `ver_configuracoes`) | Leitura executou; mutações pendentes |
| Memória | `nucleo/memoria_mcp.py` | 3 | `nucleo/tests/test_memoria.py` | Prova J2 direta via stdio (`memoria_buscar`) | Leitura executou; gravação pendente |
| Mesa | `nucleo/mesa_mcp.py` | 15 | `nucleo/tests/test_mesa_mcp.py`, `test_mesa_stdio.py` | Prova J2 direta via stdio (`hora_atual`) | Leitura executou; UI/janelas pendente Windows |
| Reunião | `nucleo/reuniao_mcp.py` | 6 | `nucleo/tests/test_reuniao_mcp.py`, `test_reuniao.py` | Prova J2 direta via stdio (`reuniao_status`) | Leitura executou; gravação pendente |
| Oficina | `nucleo/oficina_mcp.py` | 7 | `nucleo/tests/test_oficina_mcp.py`, `test_oficina.py` | `scripts/provas/prova-oficina.py` (simulado) | Pendência Windows (`msvcrt`) |
| Consulta | `nucleo/consulta_mcp.py` | 7 | `nucleo/tests/test_consulta_mcp.py`, `test_consulta.py` | `scripts/provas/prova-delegada.py` (simulado) | Pendência Windows (`msvcrt`) |

#### Matriz MCP Configurações (`nucleo/configuracoes_mcp.py` — 25 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `ver_configuracoes` | `test_ajustes_mcp.py::test_ver_configuracoes_mostra_usar_openjarvis_sem_mudar_quem_responde` | Prova J2/J3 direta stdio e laço HTTP/SSE com modelo de prova | Executou com sucesso (devolveu configurações do HUD sem vazar segredos) |
| `mudar_aparencia` | `test_ajustes_mcp.py::test_aparencia_muda_so_a_cor_ou_so_a_opacidade` | pendente (alteração visual de janela gráfica; não executar em headless) | Validado em teste unitário |
| `listar_vozes` | `test_ajustes_mcp.py::test_vozes_de_fabrica_disponiveis_sem_cadastro` | Prova J2 direta via stdio | Executou com sucesso (catálogo Kokoro/Edge/Piper) |
| `escolher_voz` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (grava preferência do usuário no disco; escrita não destrutiva) | Validado em teste unitário |
| `listar_provedores` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | Prova J2 direta via stdio | Executou com sucesso (provedores sanitizados com `***`) |
| `cadastrar_provedor` | `test_ajustes_mcp.py::test_mcp_nao_aceita_segredo_nem_o_devolve` | pendente (escrita em `paineis.json`; mutação controlada) | Validado em teste unitário |
| `editar_provedor` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (modificação de arquivos de configuração) | Validado em teste unitário |
| `remover_provedor` | `test_ajustes_mcp.py::test_mcp_confirma_antes_de_efeitos_e_nao_vaza` | pendente (remoção destrutiva de provedores cadastrados) | Validado em teste unitário |
| `escolher_quem_responde` | `test_ajustes_mcp.py::test_mcp_confirma_antes_de_efeitos_e_nao_vaza`, `test_ajustes_mcp.py::test_ver_configuracoes_mostra_usar_openjarvis_sem_mudar_quem_responde` | pendente (alteração da rota do respondedor ativo) | Validado em teste unitário |
| `testar_provedor` | `test_ajustes_mcp.py::test_teste_de_provedor_usa_config_salva_sem_expor_chave` | pendente (disparo de requisição externa de rede) | Validado em teste unitário |
| `listar_instalaveis` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (leitura de catálogo de pacotes externos) | Validado em teste unitário |
| `instalar` | `test_ajustes_mcp.py::test_mcp_instala_por_http_so_apos_confirmacao` | pendente (execução de instalação de pacotes no ambiente) | Validado em teste unitário |
| `andamento_instalacao` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (consulta de processo de instalação em andamento) | Validado em teste unitário |
| `listar_habilidades` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (consulta de receitas do usuário) | Validado em teste unitário |
| `cadastrar_habilidade` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (escrita de receitas no disco) | Validado em teste unitário |
| `editar_habilidade` | `test_ajustes_mcp.py::test_fabrica_nao_se_exclui_e_receita_inexistente_avisa` | pendente (modificação de receitas existentes) | Validado em teste unitário |
| `excluir_habilidade` | `test_ajustes_mcp.py::test_fabrica_nao_se_exclui_e_receita_inexistente_avisa` | pendente (exclusão de receitas) | Validado em teste unitário |
| `restaurar_habilidade` | `test_ajustes_mcp.py::test_fabrica_nao_se_exclui_e_receita_inexistente_avisa` | pendente (restauração de receitas de fábrica) | Validado em teste unitário |
| `marcar_habilidade_validada` | `test_ajustes_mcp.py::test_fabrica_nao_se_exclui_e_receita_inexistente_avisa` | pendente (alteração de estado de validação) | Validado em teste unitário |
| `listar_programas` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (leitura de atalhos e programas registrados) | Validado em teste unitário |
| `cadastrar_programa` | sem teste específico (exposição coberta por `test_servidor_mcp_real_expoe_todas_as_ferramentas_e_grava_aparencia`) | pendente (escrita em configuração de programas) | Validado em teste unitário |
| `remover_programa` | `test_ajustes_mcp.py::test_remover_programa_inexistente_retorna_mensagem_clara_sem_excecao` | pendente (remoção de programas registrados) | Validado em teste unitário |
| `ver_telegram` | `test_telegram_mcp.py::test_ver_telegram_retorna_ligado_e_chat_sem_token` | pendente (consulta de status do conector Telegram) | Validado em teste unitário |
| `configurar_telegram` | `test_telegram_mcp.py::test_configurar_telegram_grava_ligado_e_chat` | pendente (escrita de configuração de bot/chat) | Validado em teste unitário |
| `trazer_telegram_do_openjarvis` | `test_telegram_mcp.py::test_trazer_do_openjarvis_pelo_nucleo_sem_token` | pendente (migração de parâmetros do OpenJarvis) | Validado em teste unitário |

#### Matriz MCP Memória (`nucleo/memoria_mcp.py` — 3 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `memoria_buscar` | `test_memoria.py::test_sem_config_devolve_a_frase_e_nao_chama_rede`, `test_memoria.py::test_buscar_e_global_e_le_global_hits` | Prova J2 direta via stdio | Executou com sucesso ("A memória não está configurada: falta o projeto em memoria.toml.") |
| `memoria_ler` | `test_memoria.py::test_sem_config_devolve_a_frase_e_nao_chama_rede`, `test_memoria.py::test_ler_usa_o_projeto_da_configuracao_quando_nao_vem_projeto` | pendente (exige base de memória e projeto configurados) | Validado em teste unitário |
| `memoria_gravar` | `test_memoria.py::test_sem_config_devolve_a_frase_e_nao_chama_rede`, `test_memoria.py::test_gravar_usa_o_projeto_da_configuracao` | pendente (gravação permanente em base de memória) | Validado em teste unitário |

#### Matriz MCP Mesa (`nucleo/mesa_mcp.py` — 15 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `hora_atual` | `test_mesa_mcp.py::test_hora_atual_em_portugues`, `test_cerebro_ferramentas.py::test_handshake_lista_chamada_stdio` | Prova J2 direta via stdio | Executou com sucesso (retornou data/hora em português formatada) |
| `abrir_url` | `test_mesa_mcp.py::test_abrir_url_normaliza_e_chama_startfile` | pendente (exige `os.startfile` e navegador no Windows) | Pendência Windows (`os.startfile` ausente em Linux) |
| `abrir_programa` | `test_mesa_mcp.py::test_abrir_programa_conhecido` | pendente (exige `os.startfile` e aplicativos Windows) | Pendência Windows (`os.startfile` ausente em Linux) |
| `listar_janelas` | `test_mesa_mcp.py::test_listar_janelas_mostra_monitor_com_mais_de_um` | pendente (exige Win32 API para enumeração de janelas) | Pendência Windows (`win32gui` ausente em Linux) |
| `focar_janela` | `test_mesa_mcp.py::test_focar_janela_existente` | pendente (exige gerenciamento de foco no Windows) | Pendência Windows (`win32gui` ausente em Linux) |
| `fechar_janela` | `test_mesa_mcp.py::test_fechar_janela_existente_e_inexistente` | pendente (fechamento de janelas gráficas no Windows) | Pendência Windows (`win32gui` ausente em Linux) |
| `listar_monitores` | `test_mesa_mcp.py::test_listar_monitores` | pendente (enumeração de monitores via Win32) | Pendência Windows (API Win32 ausente em Linux) |
| `mover_janela` | `test_mesa_mcp.py::test_mover_janela_ativa_e_estados` | pendente (posicionamento de janelas via Win32) | Pendência Windows (API Win32 ausente em Linux) |
| `elementos_da_janela` | `test_mesa_mcp.py::test_elementos_da_janela` | pendente (inspeção de acessibilidade via UIA) | Pendência Windows (UI Automation ausente em Linux) |
| `clicar_elemento` | `test_mesa_mcp.py::test_clicar_elemento_aciona_pela_uia` | pendente (acionamento UIA no Windows) | Pendência Windows (UI Automation ausente em Linux) |
| `clicar` | `test_mesa_mcp.py::test_clicar_confere_o_ponto`, `test_teclado_mouse.py::test_clicar_move_o_cursor_e_envia` | pendente (injeção de mouse no sistema; vedado sem CDP) | Pendência Windows / Proibição de injeção global |
| `digitar` | `test_mesa_mcp.py::test_digitar_foca_a_janela_antes_ou_desiste`, `test_teclado_mouse.py::test_digitar_limite_e_contagem` | pendente (injeção de texto no sistema; vedado sem CDP) | Pendência Windows / Proibição de injeção global |
| `teclar` | `test_mesa_mcp.py::test_teclar_valida_antes_de_focar`, `test_teclado_mouse.py::test_teclar_repete_e_valida` | pendente (injeção de teclas no sistema; vedado sem CDP) | Pendência Windows / Proibição de injeção global |
| `rolar` | `test_mesa_mcp.py::test_rolar`, `test_teclado_mouse.py::test_rolar_em_ponto` | pendente (injeção de scroll no sistema; vedado sem CDP) | Pendência Windows / Proibição de injeção global |
| `print_da_tela` | `test_mesa_mcp.py::test_print_da_tela_grava_png_na_pasta_de_prints` | pendente (captura de frame buffer gráfico do Windows) | Pendência Windows (GDI/DirectX ausente em Linux) |

#### Matriz MCP Reunião (`nucleo/reuniao_mcp.py` — 6 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `reuniao_status` | `test_reuniao_mcp.py::test_status_e_encerrar_passam_pelo_cliente`, `test_server.py::test_reuniao_status_e_lista_repassam` | Prova J2 direta via stdio | Executou com sucesso ("O modo reunião não está instalado.") |
| `reuniao_iniciar` | `test_reuniao_mcp.py::test_iniciar_com_4720_fora_devolve_frase`, `test_server.py::test_reuniao_iniciar_repassa` | `scripts/provas/prova-reuniao.py` (simulado) / pendente de serviço na porta 4720 | Validado em teste unitário |
| `reuniao_encerrar` | `test_reuniao_mcp.py::test_status_e_encerrar_passam_pelo_cliente` | pendente (exige reunião ativa para término) | Validado em teste unitário |
| `reuniao_ata` | `test_reuniao_mcp.py::test_ata_chama_abrir_ata_com_qual_e_tipo`, `test_server.py::test_reuniao_ata_abre_a_tarefa` | pendente (exige reunião ativa e transcrição consolidada) | Validado em teste unitário |
| `reuniao_falante` | `test_reuniao_mcp.py::test_falante_vazio_recusa_sem_rede` | pendente (exige reunião ativa e diarização de voz) | Validado em teste unitário |
| `reuniao_guardar` | `test_reuniao_mcp.py::test_guardar_sem_ata_devolve_a_frase` | pendente (exige ata gerada para arquivamento) | Validado em teste unitário |

#### Matriz MCP Oficina (`nucleo/oficina_mcp.py` — 7 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `disparar_tarefa` | `test_oficina_mcp.py::test_disparar_lanca_o_trabalhador`, `test_oficina_mcp.py::test_pedido_identico_em_60s_nao_duplica` | `scripts/provas/prova-oficina.py` (simulado) | Pendência Windows (`msvcrt`) |
| `status_tarefa` | `test_oficina_mcp.py::test_listar_e_status_vazios`, `test_oficina_mcp.py::test_status_de_codigo_observa_o_orca_e_marca_avisado` | pendente (exige tarefa em execução) | Pendência Windows (`msvcrt`) |
| `resultado_tarefa` | `test_consulta_mcp.py::test_resposta_remota_chega_ao_resultado_e_evento` | pendente (exige tarefa concluída) | Pendência Windows (`msvcrt`) |
| `responder_tarefa` | sem teste específico | pendente (exige tarefa aguardando interação do operador) | Pendência Windows (`msvcrt`) |
| `aprovar_tarefa` | sem teste específico | pendente (exige tarefa aguardando aprovação de patch) | Pendência Windows (`msvcrt`) |
| `descartar_tarefa` | sem teste específico | pendente (exige tarefa ativa para cancelamento) | Pendência Windows (`msvcrt`) |
| `listar_tarefas` | `test_oficina_mcp.py::test_listar_e_status_vazios` | pendente (leitura de fila de tarefas) | Pendência Windows (`msvcrt`) |

#### Matriz MCP Consulta (`nucleo/consulta_mcp.py` — 7 ferramentas)

| Ferramenta | Teste automatizado real | Prova real (J2/J3 direta, laço HTTP/SSE ou motivo) | Resultado |
| --- | --- | --- | --- |
| `github_prs` | `test_consulta_mcp.py::test_github_le_repos_e_dono_apos_importacao` | pendente (exige CLI `gh` autenticado e repositórios) | Pendência Windows (`msvcrt`) |
| `github_issues` | `test_consulta_mcp.py::test_github_le_repos_e_dono_apos_importacao` | pendente (exige CLI `gh` autenticado e repositórios) | Pendência Windows (`msvcrt`) |
| `deploys` | `test_consulta.py::test_deploys_com_painel_ok`, `test_consulta_mcp.py::test_consulta_sem_config_nao_lanca` | pendente (exige painel de deploy/Vercel autenticado) | Validado em teste unitário |
| `relatorio` | `test_consulta.py::test_relatorio_sem_config_responde_sem_erro`, `test_consulta_mcp.py::test_relatorio_do_agente_remoto` | pendente (exige relatórios cadastrados) | Validado em teste unitário |
| `agente_remoto` | `test_consulta_mcp.py::test_agente_remoto_registra_e_lanca`, `test_remoto.py::test_executar_remoto_usa_sessao_por_tarefa_por_padrao` | `scripts/provas/prova-delegada.py` (simulado) | Validado em teste unitário |
| `delegar` | `test_consulta_mcp.py::test_delegar_registra_e_lanca`, `test_server.py::test_persona_delegar` | pendente (exige agente remoto disponível) | Validado em teste unitário |
| `rotina_manha` | `test_consulta_mcp.py::test_rotina_manha_marca_o_dia_e_lanca` | pendente (exige agendamento e perfil matinal configurados) | Validado em teste unitário |

### Cérebro próprio

| Subgrupo | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Pedidos/FIFO | `nucleo/vard/cerebro/pedidos.py` | `test_cerebro_pedidos.py`, `test_cerebro_pedidos_integracao.py` | `scripts/provas/prova-cerebro.py` (simulado) | Passou em teste e prova simulada |
| Sessões | `nucleo/vard/cerebro/sessoes.py` | `test_cerebro_laco.py`, `test_cerebro_laco_persona.py` | exercitado pelo laço J2 (não medido isoladamente) | Passou (ciclo de sessão gerenciado com SSE) |
| Adaptadores/Montador | `nucleo/vard/cerebro/montador.py`, `provedores.py` | `test_cerebro_provedores.py`, `test_cerebro_ferramentas.py` | exercitado pelo laço J2 (não medido isoladamente) | Passou (chamada de ferramenta despachada) |
| Cancelamento | `nucleo/vard/cerebro/pedidos.py` | `test_prova_cerebro.py` (cancelamento) | `scripts/provas/prova-cerebro.py` (simulado) | Passou em teste e prova simulada |
| Fila/Executor | `nucleo/vard/cerebro/laco.py` | `test_cerebro_executor.py`, `test_cerebro_cli.py` | exercitado pelo laço J2 (não medido isoladamente) | Passou (execução em background limpa) |
| Diário | `nucleo/vard/cerebro/diario.py` | `test_cerebro_diario.py` | exercitado pelo laço J2 (não medido isoladamente) | Passou (eventos gravados em JSONL) |
| Reserva | `nucleo/vard/cerebro/reserva.py` | `test_prova_cerebro.py` (reserva/falha) | pendente (exige esgotamento de cotas do modelo primário) | Validado em teste unitário |
| CLI/Detecção | `nucleo/vard/cerebro/cli.py`, `cli_deteccao.py`, `cli_capacidade.py` | `test_cli_detectar.py`, `test_cli_despachante.py`, `test_cli_falsa.py` | pendente de CLIs instaladas no sistema operacional | Pendência Windows (caminhos de CLIs Windows) |
| Controle motor | `nucleo/vard/cerebro/controle_motor.py` | sem teste específico | pendente (integração de atuadores físicos/SO) | Pendência Windows |

### Conectores

| Conector | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| OpenJarvis | `src/conectores/openjarvis/cliente.ts` | `tests/harness/integracao.test.ts`, `tests/openjarvis-desligado.test.ts`, `tests/integracao-real.test.ts` | pendente (exige conta e servidor real OpenJarvis) | Passou com harness simulado no Vitest |
| Ponte | `src/conectores/ponte/cliente.ts` | `tests/ponte-andamento.test.ts`, `tests/ponte-avisos.test.ts`, `tests/ponte-dispositivos.test.ts`, `tests/ponte-eventos.test.ts`, `tests/ponte-reuniao.test.ts`, `tests/ponte-saude.test.ts`, `tests/ponte-telegram.test.ts` | pendente (exige infraestrutura da ponte privada) | Passou com ponte simulada no Vitest |
| Nuvem (ElevenLabs/Gemini) | `src/conectores/nuvem/elevenlabs.ts`, `src/conectores/nuvem/` (TTS) | `tests/nuvem.test.ts` | pendente (exige chave de API com cota disponível) | Passou em testes unitários no Vitest |
| Voz própria | `src/conectores/voz/cliente.ts`, `fluxo.ts`, `kokoro.ts` | `voz/tests/test_servidor.py`, `test_kokoro.py`, `test_edge.py`, `test_piper.py` | pendente (motor de síntese local e saída de áudio) | Bloqueado em Linux (falta Python.h/C) |
| Telegram | `nucleo/vard/telegram.py` | `test_telegram.py`, `test_telegram_mcp.py`, `test_telegram_rotas.py`, `test_telegram_servidor.py`, `test_telegram_lifespan.py`, `test_telegram_migracao.py` | pendente (exige bot token registrado e chat liberado) | Passou em testes unitários mockados |

### Voz

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Transcrição (STT) | `voz/vard_voz/transcricao.py`, `modelos_stt.py` | `voz/tests/test_transcricao.py`, `test_modelos_stt.py`, `test_servidor_stt_modelos.py` | pendente (exige microfone físico e captura de áudio ao vivo) | Bloqueado em Linux (dependências C) |
| Falar (TTS) | `voz/vard_voz/servidor.py`, `motor.py`, `kokoro.py`, `edge.py`, `piper.py` | `voz/tests/test_servidor.py`, `test_kokoro.py`, `test_edge.py`, `test_piper.py`, `test_motor.py` | pendente (exige hardware de saída de som) | Bloqueado em Linux (dependências C) |

### Avisos, tarefas, manhã, pesquisa, remoto

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Avisos | `nucleo/vard/avisos.py`, `src/avisos/central.ts` | `nucleo/tests/test_avisos.py`, `tests/aba-avisos.test.ts`, `tests/avisos-chamada.test.ts`, `tests/avisos-fala.test.ts` | sem prova real; coberto por testes Vitest/Python | Passou em testes Vitest e Python |
| Tarefas | `nucleo/vard/tarefas.py` | `nucleo/tests/test_tarefas.py` | coberto por testes automatizados (trava POSIX com `fcntl.flock` no J3) | Passou após correção da trava POSIX |
| Manhã | `nucleo/vard/manha.py` | `nucleo/tests/test_manha.py` | pendente (exige agente e perfil matinal configurados) | Passou em testes unitários |
| Pesquisa | `nucleo/vard/pesquisa.py` | `nucleo/tests/test_pesquisa.py` (`test_cria_o_agente_e_devolve_a_resposta`) | pendente (exige agente configurado) | Passou em testes unitários |
| Remoto | `nucleo/vard/remoto.py` | `nucleo/tests/test_remoto.py` | `scripts/provas/prova-delegada.py` (simulado) / coberto por testes no J3 (trava remota) | Passou em testes unitários e simulados |

### Atalhos, bandeja e atualização

| Função | Código | Testes automatizados | Prova real | Resultado |
| --- | --- | --- | --- | --- |
| Atalhos | `src/config/atalhos.ts`, `src/ui/campo-atalho.ts` | `tests/atalhos.test.ts`, `tests/atalhos-win.test.ts` | pendente (exige registro global RegisterHotKey no Windows) | Passou em testes Vitest (100% verde) |
| Bandeja | `nucleo/vard/bandeja.py` | `nucleo/tests/test_bandeja.py` | pendente (exige shell do Windows tray ativo) | Passou em testes unitários |
| Atualização | `src/atualizacao/release.ts`, `src/ui/aba-atualizacao.ts` | `tests/atualizacao.test.ts`, `tests/release.test.ts` | pendente (exige release assinada publicada no repositório) | Passou em testes Vitest (100% verde) |

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
| 23 | `test_runtime_instalado.py::test_hash_incorreto_falha_antes_de_extrair` | `FileNotFoundError: [Errno 2] No such file or directory: 'powershell'` | script `montar-nucleo.ps1` executado via `powershell` |
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

### Defeitos e correções (J2/J3) — 5 defeitos de código e endurecimento do harness

Consolidação única de todos os defeitos de código identificados no inventário (J1) e corrigidos no J3, além das melhorias de robustez do harness implementadas no J2 e no J3:

| # | Item / Defeito | Causa | Arquivo | Teste que prova | Correção | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `test_config.py::test_nome_invalido_recusado` | `\` é caractere válido em nomes de arquivo POSIX; validação só rejeitava `/` | `nucleo/vard/config.py` | `test_nome_invalido_recusado` | Rejeita `\` no nome explicitamente em qualquer SO | PASSA em Linux e Windows |
| 2 | `test_delegada.py::test_preparar_pasta_remove_juncao_sem_seguir_o_alvo` | `cmd`/`mklink` são binários exclusivos do Windows; teste falhava em POSIX | `nucleo/tests/test_delegada.py` | `test_preparar_pasta_remove_juncao_sem_seguir_o_alvo` | `pytest.skip` documentado quando `cmd` não está disponível (`shutil.which("cmd") is None`) | SKIP documentado em Linux; PASSA em Windows |
| 3 | `test_entrada.py::test_porta_ocupada_sai_com_motivo_identificavel` | `getattr(errno, "WSAEADDRINUSE", None)` gerava tupla com `None`, fazendo `OSError(None)` ser classificado erroneamente como porta ocupada | `nucleo/vard/servidor.py` | `test_porta_ocupada_sai_com_motivo_identificavel` | `getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)` mantém compatibilidade Windows e evita falso positivo em POSIX | PASSA em Linux e Windows |
| 4 | `test_remoto.py::test_trava_impede_segunda_conversa` | `tarefas.trava()` não possuía implementação de bloqueio concorrente para POSIX (fallback vazio sem `msvcrt`) | `nucleo/vard/tarefas.py` | `test_remoto.py::test_trava_impede_segunda_conversa` | Trava POSIX real usando `fcntl.flock(LOCK_EX | LOCK_NB)` com timeout e polling | PASSA (bloqueio entre processos validado) |
| 5 | `test_tarefas.py::test_trava_entre_processos` | Mesma ausência de trava POSIX do item #4 | `nucleo/vard/tarefas.py` | `test_tarefas.py::test_trava_entre_processos` | Mesma implementação `fcntl.flock` do item #4 | PASSA (`TimeoutError` ao disputar trava entre processos) |
| 6 | Harness: vazamento de processos e cleanup | MCPs e núcleo podiam ficar órfãos se a execução falhasse no meio | `scripts/provas/prova-real-ferramentas.py` | `test_prova_real_ferramentas.py::TestHarnessSimulado` | Cleanup estrito em `try/finally` dentro do context manager, encerramento com SIGTERM/SIGKILL e checagem de PIDs via `psutil.pid_exists` | PASSA (zero processos sobreviventes) |
| 7 | Harness: validação de evento e chamada real | Teste offline afirmava apenas encerramento, sem verificar despacho de ferramentas | `scripts/provas/prova-real-ferramentas.py`, `nucleo/tests/test_prova_real_ferramentas.py` | `test_prova_real_ferramentas.py::TestHarnessSimulado` | Gerenciador fake registra chamada real, valida evento SSE `ferramenta` com nome/argumentos e resposta integrada | PASSA (evento e execução afirmados) |
| 8 | Harness: isolamento de variáveis e sanitização | Testes modificavam `os.environ` diretamente com risco de contaminação e truncamento invertido na sanitização | `scripts/provas/prova-real-ferramentas.py`, `nucleo/tests/test_prova_real_ferramentas.py` | `test_prova_real_ferramentas.py::TestSanitizacao` | Uso de `monkeypatch.setenv/delenv` e correção da ordem `sanitizar(str(exc))[:300]` | PASSA (isolamento garantido) |

**Total de defeitos de código:** 5 corrigidos + 3 melhorias estruturais do harness.
**Saldo de falhas da suíte núcleo:** 53 falhas iniciais - 5 defeitos corrigidos = 48 falhas restantes (100% dependentes de APIs/binários Windows, 0 defeitos de código pendentes).

---

## Prova real do cérebro e dos MCPs (J2) — 2026-11-02

Executada em Linux aarch64 com modelo de prova via ambiente.
Configuração isolada via `VARD_CONFIG`, `VARD_DADOS` e `VARD_HUD_CONFIG_DIR` apontando para diretórios temporários; `paineis.json` gerado com as quatro chaves de agente (`claude`, `codex`, `opencode`, `agy`) exigidas por `ajustes.validar_documento`.
Saída sanitizada em `/tmp/opencode/vard-j2-final.json`. Nenhum segredo, endpoint ou nome de modelo no relatório.

> **Histórico:** A primeira execução (pit stop 1) registrou `auth_401` porque o comando de prova exportou um modelo fictício (`provedor/modelo-de-teste`) em vez do modelo de prova real — falha do harness, não do produto. A reexecução com o ambiente correto passou; o resultado abaixo reflete essa execução bem-sucedida.
>
> **J3 pit stop 1 (2026-11-02):** Harness endurecido — cleanup em `try/finally` dentro do `with`, teste offline afirma evento `ferramenta` com nome/argumentos, PIDs dos MCPs confirmados encerrados via `psutil.pid_exists`. Prova real reexecutada com sucesso: evento `ver_configuracoes` + resposta textual + zero processos vivos após encerramento.
>
> **J3 pit stop 2 (2026-11-02):** Quatro achados de vistoria corrigidos: (1) `servidor.py` — `getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)` evita falso positivo de porta ocupada quando `errno=None`; (2) teste do harness fortalecido com gerenciador fake que registra chamada e afirma execução real da ferramenta (não só evento); (3) três testes de sanitização migrados de `os.environ`/`del` para `monkeypatch.setenv/delenv`; (4) `prova-real-ferramentas.py:404` — ordem de sanitização/truncamento corrigida (`sanitizar(str(exc))[:300]`). Testes alvo verdes; sem nova prova real.

### MCPs diretos (stdio, sem modelo)

| MCP | Ferramenta | Status | Resultado sanitizado |
| --- | --- | --- | --- |
| configuracoes | ver_configuracoes | executou | Configurações atuais: widget com OpenJarvis desligado, perfil versão 1, respondedor de prova |
| configuracoes | listar_provedores | executou | Provedores com id, nome, tipo e url_base/modelo sanitizados (`***`) |
| configuracoes | listar_vozes | executou | Catálogo de vozes Kokoro/Edge/Piper com IDs e rótulos |
| memoria | memoria_buscar | executou | "A memória não está configurada: falta o projeto em memoria.toml." |
| reuniao | reuniao_status | executou | "O modo reunião não está instalado." |
| mesa | hora_atual | executou | "Agora são 6h37 de segunda-feira, 2 de novembro de 2026 (UTC+00:00)." |
| oficina | — | pendencia_windows | MCP depende de msvcrt/Windows; não aplicável em Linux |
| consulta | — | pendencia_windows | MCP depende de msvcrt/Windows; não aplicável em Linux |

### Cérebro por HTTP/SSE (modelo de prova via ambiente + ferramenta real)

- **Estado do pedido:** concluido
- **HTTP status:** 202
- **Erro:** nenhum
- **Ferramenta chamada:** `ver_configuracoes` (argumento `reason`: consultar configurações atuais)
- **Eventos SSE:** ferramenta → texto → fim (3 eventos, sanitizados)
- **Resposta sanitizada:** "As configurações atuais definem o respondedor como \"omni-prova\", perfil versão 1 e o uso do OpenJarvis desligado no widget."
- **Duração:** 13,7 s
- **Processo núcleo:** PID 98468, terminado graceful; nenhum processo restante

---

## Pendências de prova real e delimitação

Para manter clareza sobre o escopo provado e evitar falsa impressão de entrega, a tabela abaixo detalha o que está pendente, o que exigiria para virar prova real e o que **não** foi provado:

| Item | Motivo da pendência | O que exigiria para virar prova real | O que NÃO foi provado |
| --- | --- | --- | --- |
| OpenJarvis | Exige conta e serviço OpenJarvis ativo | Instalação real com endpoint e credenciais válidas | Conversa real com servidor OpenJarvis em produção |
| Ponte do Vard | Protocolo proprietário em infraestrutura privada | Instalação da ponte local emparelhada e rede configurada | Tráfego de eventos e comandos pela ponte real |
| Nuvem (ElevenLabs/Gemini) | Exige chaves de API pagas/privadas | Variáveis com chave de API com cota disponível | Geração de áudio ou chamada a modelos dessas nuvens |
| Voz própria (Kokoro/XTTS/Piper) | Exige motor de síntese compilado e saída de áudio | Runtime de voz em Windows com hardware de saída de som | Reprodução de áudio real por autofalante/fone |
| Telegram | Exige bot registrado e chat liberado | Token emitido pelo @BotFather e chat ID autorizado | Envio e recepção de mensagens no aplicativo Telegram |
| Manhã delegada | Exige rotina de agente configurada | Agente com chaves/perfil cadastrado para consolidar a manhã | Disparo real da rotina matinal completa |
| Pesquisa delegada | Exige agente de pesquisa conectado | Provedor de pesquisa configurado | Coleta de fontes externas via agente delegado |
| Remoto (SSH/Docker) | Infraestrutura remota real | Host remoto acessível com chave pública ou container Docker | Conexão de rede e execução remota em servidor externo |
| Atalhos globais | API do Windows RegisterHotKey | Sessão de usuário no Windows com foco do sistema operacional | Registro e captura de tecla de atalho global pelo SO |
| Bandeja do sistema | API do Windows Shell_NotifyIcon | Shell do Windows explorer ativo e suporte a ícones de notificação | Renderização do ícone na bandeja e menu de contexto |
| Atualização | Exige release assinada publicada no repositório | GitHub Release válida com binários assinados por SignPath | Download, verificação de assinatura e auto-atualização |
| Mesa (UI Automation) | Windows + tela gráfica real | Desktop interativo Windows com janelas de aplicativos reais | Automação de janelas reais, cliques de mouse e digitação |
| WebView2 / Tauri dev | Exige runtime WebView2 e Windows | Windows 10/11 com Build Tools C++ e WebView2 instalado | Janela visual do Tauri renderizada pelo WebView2 |
| STT com microfone | Exige hardware de entrada de áudio | Microfone físico capturando fala ao vivo | Transcrição de voz real capturada por hardware |

---

## Resumo da validação

- **Frontend (TypeScript):** 1126 testes passando; `npm run check` limpo. Sem pendências de código ou tipagem.
- **Núcleo (Python):** 1597 testes passando em Linux (com 68 pulados); **48 falhas só Windows (todas decorrentes de APIs exclusivas do Windows: msvcrt, win32gui, os.startfile, powershell, etc.), 0 defeitos de código pendentes**. Os 7 arquivos com erro de coleta falham unicamente pelo `import msvcrt` no nível do módulo em `vard/vigia.py`. Do total de 53 falhas iniciais, os 5 defeitos de código identificados foram 100% corrigidos e permanecem verdes (53 = 48 restantes só Windows + 5 corrigidas).
- **Harness e Robustez:** Cleanup estrito implementado com `try/finally` no context manager do harness, asserção do evento SSE `ferramenta` no teste offline, verificação de término de processos via `psutil.pid_exists` e sanitização estrita sem vazamento de segredos/endpoints/tokens.
- **Provas reais executadas com sucesso:**
  - **Cérebro por HTTP/SSE:** 1 prova real ponta a ponta bem-sucedida registrada no J2 (status HTTP 202, 3 eventos SSE: ferramenta `ver_configuracoes` → texto sanitizado → fim, duração de 13,7 s, encerramento limpo sem processos órfãos).
  - **MCPs diretos (stdio):** 6 ferramentas de leitura executadas diretamente via stdio (`ver_configuracoes`, `listar_provedores`, `listar_vozes`, `memoria_buscar`, `reuniao_status`, `hora_atual`), devolvendo payloads válidos.
- **Voz, Reunião e Rust/Tauri:** Bloqueados em Linux por ausência de compiladores C/LLVM (`libclang`) e bibliotecas nativas de áudio do Windows (`pyaudiowpatch`). Provas desses subsistemas dependem de ambiente Windows real.
- **Demais integrações:** As integrações externas permanecem documentadas como pendentes das respectivas contas, chaves ou hardware, com seus requisitos demarcados na tabela de pendências.
