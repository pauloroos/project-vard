# Tasks: Conversa basica confiavel

## Phase 1: Setup
Sem tarefas.

## Phase 2: Foundational
Sem tarefas.

## Phase 3: User Story 1 (P1) — conversa que sempre termina e lembra
- [ ] T001 [P] [US1] Garantir evento terminal em todos os caminhos do despachante em nucleo/vard/cerebro/pedidos.py, com teste em nucleo/tests/test_cerebro_pedidos_terminal.py (FR-001)
- [ ] T002 [P] [US1] Reconsultar o pedido ao reconectar o SSE e periodicamente, com prazo máximo e erro visível, em src/fala/conversa.ts, com teste em tests/conversa-pedido-terminal.test.ts (FR-002)
- [ ] T003 [P] [US1] Gravar o par pergunta/resposta no histórico da sessão em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/sessoes.py, com teste em nucleo/tests/test_cerebro_historico.py (FR-003)
- [ ] T004 [P] [US1] Interromper cancela a transcrição em andamento em src/main.ts com a lógica num módulo testável src/fala/ciclo-voz.ts, com teste em tests/ciclo-voz-cancelamento.test.ts (FR-004)
- [ ] T005 [US1] Aplicar no widget a troca de microfone e saída salva nas configurações, ou avisar reinício, em src/main.ts e src/config/config.ts, com teste em tests/dispositivos-ao-vivo.test.ts, depends on T004 (FR-005)
- [ ] T006 [P] [US1] Separar parada definitiva de reinício no supervisor em src-tauri/src/servicos.rs e fazer recarregar reiniciar em src-tauri/src/ciclo.rs, com testes Rust no próprio arquivo (FR-006)

## Phase 4: User Stories 2 e 3 (P2) — andamento visível e promessas honestas
- [ ] T007 [US2] Mostrar etapas transcrevendo, pensando e falando e os erros de transcrição, resposta e síntese na interface em src/fala/conversa.ts e src/main.ts, com teste em tests/etapas-visiveis.test.ts (FR-007)
- [ ] T008 [US2] Emitir texto progressivo no núcleo em nucleo/vard/cerebro/laco.py e falar frase por frase em src/fala/conversa.ts, com testes em nucleo/tests/test_cerebro_texto_progressivo.py e tests/fala-por-frase.test.ts, depends on T007 (FR-008)
- [ ] T009 [P] [US3] Corrigir o modo jogo com executor único em src-tauri/src/ciclo.rs (pasta de configuração, contrato de /pedidos, sem sucesso falso, sem chamar /modo do Python), com testes Rust no próprio arquivo (FR-009)
- [ ] T010 [P] [US3] Formato interno único de ferramenta e argumentos acumulados em nucleo/vard/cerebro/provedores.py, com teste em nucleo/tests/test_cerebro_ferramentas_contrato.py (FR-010)

## Phase 5: Polish (P3)
- [ ] T011 [P] [US4] Reescrever README.md e README.en.md com a configuração mínima recomendada e as periféricas congeladas (FR-011)
