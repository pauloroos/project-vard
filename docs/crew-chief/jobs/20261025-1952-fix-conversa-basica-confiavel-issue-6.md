# fix: conversa básica confiável (issue #6)

- **Id:** `20261025-1952-fix-conversa-basica-confiavel-issue-6`
- **Created:** 2026-10-25T19:52:36.479330
- **Distributed:** yes
- **Issue:** pauloroos/project-vard#6

## Request

JOB vard-6 — Project Vard, GitHub issue #6 "Conversa básica confiável antes de novas funcionalidades (revisão da 0.9.8)".
Scope: the 7 bugs and the 10 plan items of issue #6, in the issue's priority order (Alta bugs and plan items 1-5 first),
following docs/revisoes/2026-10-24-revisao-codex-0.9.8.md, AGENTS.md and CONTRIBUTING.md. Items that need the Windows
desktop (Tauri runtime, GPU, microphone, audio devices) are implemented as far as the code allows, the logic is tested,
and they are listed in the PR as needing the owner's check on Windows. One branch fix/issue-6-conversa-basica, one PR.

Issue body:
Revisão completa: [docs/revisoes/2026-10-24-revisao-codex-0.9.8.md](../blob/main/docs/revisoes/2026-10-24-revisao-codex-0.9.8.md)

Diagnóstico: o Vard virou três produtos (interface do OpenJarvis, assistente próprio e central de automação) antes de a conversa básica ficar confiável.

## Bugs
- [ ] **Alta:** widget preso em "pensando". Uma falha antes do laço ou durante a queda do SSE não gera evento terminal (`nucleo/vard/cerebro/pedidos.py:245`). Conferido.
- [ ] **Alta:** o histórico perde a pergunta do usuário; só a resposta é gravada (`nucleo/vard/cerebro/laco.py:278`). Conferido.
- [ ] **Alta:** `recarregar` não volta a subir o serviço, porque `parar()` encerra a thread e `repetir()` não a recria (`src-tauri/src/servicos.rs`).
- [ ] **Alta:** o modo jogo declara sucesso sem liberar a GPU. Ele procura a config na pasta errada e o `/modo` fica em laço entre Rust e Python (`src-tauri/src/ciclo.rs`).
- [ ] **Alta:** o contrato das ferramentas está quebrado. Na conversão Anthropic o nome vai vazio, e nos compatíveis os argumentos podem virar `{}` (`nucleo/vard/cerebro/provedores.py`).
- [ ] **Média:** Interromper não cancela a transcrição em andamento (`src/main.ts`).
- [ ] **Média:** trocar o microfone ou a saída nas configurações não muda o widget e nada avisa que precisa reiniciar (`src/ui/aba-voz.ts`).

## Plano (prioridade)
1. [ ] Todo pedido termina com resposta ou erro visível; sem espera infinita.
2. [ ] Corrigir o histórico.
3. [ ] Interromper cancela STT, resposta e fala.
4. [ ] Microfone e saída obedecem à configuração.
5. [ ] Serviços se recuperam sem fechar o app.
6. [ ] Mostrar as etapas (transcrevendo, pensando, falando) e os erros.
7. [ ] Falar frase por frase, sem esperar a resposta inteira.
8. [ ] Corrigir o modo jogo ou esconder a promessa até funcionar.
9. [ ] Tirar as ferramentas do caminho básico até corrigir os contratos.
10. [ ] Congelar as periféricas (Telegram, reunião, CLIs, pesquisa, resumo da manhã) e reescrever o README com uma configuração mínima.

## Teste de aceite de cada versão
Abrir, conversar 10 turnos, interromper, trocar o dispositivo, provocar uma falha e continuar.

## Decision

- Distributed: yes
- Reason: 

## Rulings

1. Revisor codex:gpt-6.1-sol indisponível neste contêiner: a revisão da peça 1 respondeu exatamente 'Não consegui ler `.crew-chief-brief.md`: o ambiente bloqueou a execução de leitura com o erro `bwrap: No permissions to create a new namespace`.' — portanto o único revisor permitido é claude:opus, e para manter revisor de modelo diferente do executor as peças de código vão para opencode:omni/agy/gemini-3.8-flash-tiered (executor alternativo autorizado) em vez de claude-ghost:claude-opus-5-5 — custo se errado: executor mais fraco em Rust/TS, compensado pela revisão do opus e pelas correções
2. Spec 001 aceita após 2ª revisão claude:opus, que respondeu 'VEREDITO: APROVADO' e 'Nenhum achado Critical. Nenhum Important que impeça começar.' — os Minor 'P6 e P10 são lacunas parciais' entram nos briefs: T007 inclui o estado de preparação na abertura e T011 registra o primeiro uso mínimo (sala, invisibilidade e personalização avançada fora do primeiro uso) no README — custo se errado: escopo docs um pouco maior
3. Modo jogo sem ponte configurada: a ponte é opcional, então a falta dela só pula o cancelamento de pedidos; o sucesso continua exigindo a liberação feita pelo Rust (descarregar modelos e parar serviços), atendendo ao Minor do revisor 'Sem ponte configurada retorna erro (FR-009) entra em tensão com a ponte ser opcional' — custo se errado: o dono pode preferir erro explícito sem ponte

## Pieces

### 1. Escrever spec, plano e tarefas (specs/001) (docs, risk low)

**Attempts**

- attempt 1: executor `opencode:omni/agy/gemini-3.8-flash-tiered`, role exec, status ok, cost included, 290.3s, 24 steps, 866931 tokens (in 859206 / out 7725), branch `crew/20261025-1952-fix-conversa-basica-confiavel-issue-6-1-1`
  - diffstat: specs/001-conversa-basica-confiavel/plan.md +50 -7, specs/001-conversa-basica-confiavel/spec.md +54 -8, specs/001-conversa-basica-confiavel/tasks.md +17 -9
  - note:
    ```
    A elaboração da especificação, do plano de implementação e das tarefas foi concluída com sucesso.
    
    ### Arquivos atualizados
    - `specs/001-conversa-basica-confiavel/spec.md`: contexto da issue #6, quatro histórias de usuário (US1 a US4) com critérios de aceite Given/When/Then, casos de borda e dúvidas abertas, requisitos funcionais FR-001 a FR-011 e critérios de sucesso SC-001 a SC-003.
    - `specs/001-conversa-basica-confiavel/plan.md`: resumo técnico, contexto de execução (TypeScript, Python 3.13, Rust), estrutura de arquivos mapeada por tarefa e decisões D1 a D11 fundamentadas.
    - `specs/001-conversa-basica-confiavel/tasks.md`: fases com as tarefas T001 a T011 estruturadas exatamente conforme orientado, sem marcadores pendentes de template.
    
    ### Commit
    - Hash: `9d2fa44`
    - Mensagem: `docs(spec): spec, plano e tarefas da conversa básica confiável` (sem menções ou atribuições a IA, com autor GitHub noreply verificado).
    ```
- attempt 2: executor `codex:gpt-6.1-sol`, role review, status ok, cost included, 21.5s, 19970 tokens
  - note:
    ```
    Não consegui ler `.crew-chief-brief.md`: o ambiente bloqueou a execução de leitura com o erro `bwrap: No permissions to create a new namespace`.
    
    Nenhum arquivo foi modificado e nenhum agente foi delegado. A revisão permanece pendente; cole o briefing e os trechos a revisar ou restaure o acesso de leitura ao workspace.
    ```
- attempt 3: executor `claude:opus`, role review, status ok, cost included, 164.6s, 35 steps, 1705700 tokens (in 1690285 / out 15415)
  - reported model: `claude-opus-5-5`
  - note:
    ```
    em conversão em `corpo["tools"]`.
    - O laço manda o formato plano `{name, description, parameters}` (`laco.py:134-141`), e a API OpenAI exige `{"type":"function","function":{...}}`.
    - FR-010 diz "convertido em cada adaptador", mas D10 só cita Anthropic e o acúmulo de argumentos. A tarefa deve cobrir os três adaptadores, incluindo o Gemini em `provedores.py:592`, que já aceita os dois formatos.
    
    **Q4. O laço Rust → Python → Rust também existe em `voltar`.**
    - `executar_voltar` (`ciclo.rs:607`) chama `ponte_modo("voltar")`, com o mesmo efeito.
    - FR-009 e T009 só tratam `jogo`. Corrigir só a ida deixa a volta republicando o pedido e sem recarregar o modelo.
    
    **Q5. D2 e D8 interagem, e o plano não trata isso.**
    - `_emissor` (`pedidos.py:216`) só grava `resposta` no `fim`.
    - A reconciliação (`conversa.ts:355-358`) substitui `textoAcumulado` por `snap.resposta`.
    - Com texto progressivo, uma reconexão no meio do fluxo perde fragmentos, já que o servidor não reproduz eventos. Ou a fala repete frases já ditas quando chega o `fim`.
    - O plano precisa definir uma de duas saídas:
      - o despachante acumula o texto parcial no estado;
      - ou o widget fala só o restante não falado, a partir da `resposta` final.
    
    **Q6. D6 está incompleto no supervisor.**
    - `ServicoHandle` não guarda o `DescritorServico`: o descritor é movido para a thread em `servicos.rs:40-41`.
    - Por isso `repetir` não consegue recriar a thread encerrada sem passar a guardar o descritor no registro. D6 e T006 deveriam dizer isso.
    - Detalhe: com o `pedir_reinicio` atual, `recarregar` funciona sem `parar` antes. Basta retirar o `parar` de `ciclo.rs:442-444`.
    
    **Q7. O prazo fixo de 120 s em D2 pode abortar pedidos legítimos.**
    - Exemplos: modelo local lento, ou até 8 turnos com ferramentas.
    - O prazo deveria contar desde o último progresso (evento ou estado `executando` na consulta periódica).
    - Ao estourar, deveria também cancelar o pedido no servidor.
    
    ## Minor
    
    - **Q8.** T005 lista `main.ts` e `config.ts`, mas reabrir a entrada e mudar a saída passa por `src/audio/microfone.ts` (`definirMicrofonePreferido`), `src/audio/boca.ts` (o `setSinkId` é no `AudioContext`, não num elemento, ao contrário do caso-limite da spec) e possivelmente `src/ui/aba-voz.ts:846`.
    - **Q9.** T009 precisa inverter o teste existente `executar_jogo_sem_ponte_retorna_modo_jogo` (`ciclo.rs:1392`), que hoje garante justamente o sucesso falso.
    - **Q10.** SC-002 usa `npx tsc --noEmit`, mas o contrato do repositório é `npm run check`, que também roda `tsc -p tsconfig.test.json`. Os testes novos ficariam sem checagem de tipos.
    - **Q11.** A spec descreve o ambiente do executor ("servidor Linux ARM64 sem `cargo`, sem GPU") num documento público. Isso não é documentação do produto. Basta dizer "testes Rust validados pelo dono com `cargo test` no Windows".
    - **Q12.** Prioridade: os bugs 4 e 5 (Alta) ficam na fase 4, depois de dois bugs de gravidade Média (6 e 7). Isso segue a numeração do plano da revisão (itens 8 e 9), então é defensável, mas convém declarar a escolha.
    - **Q13.** Os títulos usam "basica" sem acento, e o nível de acentuação está inconsistente com o resto em PT-BR.
    
    **Pontos verificados sem problema:**
    - Todos os caminhos citados existem, exceto `src/fala/ciclo-voz.ts` e os testes novos, que são criados pelas próprias tarefas.
    - Dependências entre tarefas:
      - mesma fase: T005 depende de T004 (`main.ts`) e T008 depende de T007 (`conversa.ts`);
      - fases diferentes: T006 e T009 em `ciclo.rs`, T003 e T008 em `laco.py`.
    - Sem dados pessoais, caminhos absolutos ou menção a IA.
    - Corretas frente ao código:
      - D1: os caminhos sem evento terminal são `pedidos.py:188-192`, `:240-249`, e o `CancelledError` que `laco.py:291` repassa;
      - D3: `laco.py:278` grava só a resposta, e `sessoes.py` conta trocas;
      - D9;
      - D11;
      - a leitura de `/pedidos` como `{"pedidos": [...]}` (`server.py:716` contra `ciclo.rs:545`) e da pasta de configuração (`ciclo.rs:466` contra `pasta_config()` em `:34`).
    
    VEREDITO: CORRIGIR
    ```
- attempt 4: executor `opencode:omni/agy/gemini-3.8-flash-tiered`, role exec, status ok, cost included, 447.5s, 34 steps, 2351470 tokens (in 2309160 / out 42310), branch `crew/20261025-1952-fix-conversa-basica-confiavel-issue-6-1-4`, from `crew/20261025-1952-fix-conversa-basica-confiavel-issue-6-1-1` (attempt 1)
  - diffstat: specs/001-conversa-basica-confiavel/plan.md +19 -15, specs/001-conversa-basica-confiavel/spec.md +17 -17, specs/001-conversa-basica-confiavel/tasks.md +7 -7
  - note:
    ```
    Os ajustes da revisão da spec 001 foram aplicados com sucesso em `specs/001-conversa-basica-confiavel/spec.md`, `plan.md` e `tasks.md`:
    
    1. **Acentuação**: Título corrigido para "Conversa básica confiável" nos três arquivos e revisão de acentuação em PT-BR.
    2. **FR-010, D10 e T010**: Especificada a conversão nos três adaptadores (compatível OpenAI → `{"type":"function","function":{name,description,parameters}}`, Anthropic → `{name, description, input_schema}`, Gemini aceitando o formato interno), com acúmulo de argumentos por índice no compatível.
    3. **FR-009, D7 e T009**: Incluída a volta (`executar_voltar`) sem chamar `/modo` do Python na ida nem na volta, religamento de núcleo, OpenJarvis e fotografia via reinício de serviços, carregamento sob demanda do provedor e inversão do teste de sucesso falso.
    4. **D2/D8 e T008**: Acúmulo do texto parcial no estado do pedido em `pedidos.py` e controle de texto no widget para síntese frase por frase sem repetição na reconciliação.
    5. **D6 e T006**: Cópia de `DescritorServico` no handle para `repetir` recriar threads concluídas, `recarregar` chamando apenas `repetir` e remoção do registro na parada definitiva.
    6. **D2 e FR-002**: Prazo de 90 s sem progresso cancelando o pedido no servidor e exibindo o erro na interface.
    7. **T005 e D5**: Troca de microfone via `src/audio/microfone.ts` (`definirMicrofonePreferido`) e saída via `src/audio/boca.ts` (`setSinkId` do `AudioContext`, não de elemento).
    8. **SC-002**: Referência atualizada para `npm run check` (tipos de src e dos testes).
    9. **Ambiente**: Removida a descrição de ambiente executor (ARM64/cargo/GPU), mantendo os testes Rust validados pelo dono com `cargo test` no Windows e o teste de aceite como checklist do dono no Windows.
    10. **Prioridade no plano**: Declarada a alocação dos bugs Alta 4 e 5 na Fase 4 conforme a numeração da issue.
    
    Commit realizado: `docs(spec): ajustes da revisão na spec 001`.
    ```
- attempt 5: executor `claude:opus`, role review, status ok, cost included, 63.0s, 19 steps, 604959 tokens (in 598967 / out 5992)
  - reported model: `claude-opus-5-5`
  - note:
    ```
    HEAD confirmado: `b2bdfa3`, ref `crew/20261025-1952-fix-conversa-basica-confiavel-issue-6-1-4`. Sem Bash nesta sessão, conferi pelo arquivo do ref, não por `git rev-parse`.
    
    **Spec: bugs**
    - B1 pedido preso em "pensando": done (FR-001, FR-002, T001/T002; 90 s sem progresso e cancelamento no servidor)
    - B2 histórico perde a pergunta: done (FR-003/T003; falhos e cancelados não gravam)
    - B3 parar impede retomada: done (FR-006/T006; descritor no handle, `recarregar` só chama `repetir`)
    - B4 modo jogo com sucesso falso: done (FR-009/T009; pasta de config, `{"pedidos": [...]}`, sem `/modo` na ida nem na volta, teste invertido)
    - B5 contrato de ferramentas: done (FR-010/T010; compatível, Anthropic e Gemini, argumentos acumulados por índice)
    - B6 Interromper não cancela STT: done (FR-004/T004; `AbortController`, resultados tardios descartados, push-to-talk liberado)
    - B7 troca de dispositivo: done (FR-005/T005; os arquivos de áudio estão na lista, com aviso de reinício)
    
    **Spec: plano**
    - P1 término e recuperação: done
    - P2 histórico: done
    - P3 Interromper: done
    - P4 microfone e saída: done
    - P5 recuperar serviços: done
    - P6 estados separados: parcial. FR-007 cobre transcrevendo, pensando e falando, mas não o estado de **preparação** na abertura que a revisão pede ("abrir… mostrar se está pronto").
    - P7 texto progressivo e fala por frase: done (parcial acumulado em `resposta`, reconciliação sem repetir)
    - P8 modo jogo: done
    - P9 ferramentas: done por outro caminho. A revisão pedia suspender; D9 corrige o contrato em vez disso, e a escolha está declarada.
    - P10 README e primeiro uso: parcial. FR-011 cobre só o README; o **primeiro uso** (tirar sala, invisibilidade e personalização avançada) ficou de fora sem justificativa.
    
    Os pedidos da revisão anterior foram todos atendidos: T010 nos três adaptadores; T009 com `voltar` sem `/modo` e o teste invertido; T008 com acúmulo e reconciliação; T006 com descritor e `repetir`; T002 com 90 s e cancelamento; arquivos de áudio em T005; `npm run check` no SC-002; a escolha de prioridade em D12. A nota de ambiente (cargo e aceite pelo dono no Windows) é sobre quem verifica, não descreve o ambiente do executor.
    
    **Quality**
    Nenhum achado Critical. Nenhum Important que impeça começar.
    
    Conferi os nomes citados contra o código e todos existem:
    - `definirMicrofonePreferido` em `src/audio/microfone.ts:66`
    - `aplicarSaidaNoContexto` com `setSinkId` no `AudioContext` em `src/audio/boca.ts:5`
    - `config-salva` em `src/main.ts:845`
    - `executar_jogo_sem_ponte_retorna_modo_jogo` em `src-tauri/src/ciclo.rs:1392`
    - `ultimo_seq` e `resposta` em `pedidos.py:90`
    - o Gemini já aceita o formato interno em `provedores.py:597`
    
    Minor:
    - P6 e P10 são lacunas parciais. Ou entram em FR-007 e FR-011, ou ficam registradas como adiadas, por exemplo para a 0.8 (primeiro uso).
    - "Sem ponte configurada retorna erro" (FR-009) entra em tensão com a ponte ser opcional. A spec também não diz o que acontece com `executar_voltar_sem_ponte_retorna_ligado` (`ciclo.rs:1411`).
    - `src/audio/dispositivos.ts:106` (`aplicarSaida`, em elemento de áudio) continua sendo um segundo caminho de saída; vale deixar claro que T005 não usa esse caminho.
    
    VEREDITO: APROVADO
    ```

**Corrections**

- revisão claude:opus pediu ajustes Q3-Q13 (adaptadores, voltar, texto progressivo x reconexão, descritor no registro, prazo por progresso, arquivos de T005, npm run check, ambiente fora do doc) by `opencode:omni/agy/gemini-3.8-flash-tiered` (2026-10-25T20:08:07.781115+00:00)

**Escalations**

- _none_

**Grades**

- `opencode:omni/agy/gemini-3.8-flash-tiered`: score 85 — adherence 3/3 → 100; 1 correction −15; 0 extra; penalties none → 85

### 2. T001 Garantir evento terminal em todos os caminhos do despachante em nucleo/vard/cerebro/pedidos.py, com teste em nucleo/tests/test_cerebro_pedidos_terminal.py (FR-001) (tests, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 3. T002 Reconsultar o pedido ao reconectar o SSE e periodicamente, com prazo de 90 s sem progresso, cancelando no servidor e exibindo erro visível, em src/fala/conversa.ts, com teste em tests/conversa-pedido-terminal.test.ts (FR-002) (tests, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 4. T003 Gravar o par pergunta/resposta no histórico da sessão em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/sessoes.py, com teste em nucleo/tests/test_cerebro_historico.py (FR-003) (tests, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 5. T004 Interromper cancela a transcrição em andamento em src/main.ts com a lógica num módulo testável src/fala/ciclo-voz.ts, com teste em tests/ciclo-voz-cancelamento.test.ts (FR-004) (tests, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 6. T005 Aplicar no widget a troca de microfone e saída salva nas configurações, ou avisar reinício, em src/main.ts, src/config/config.ts, src/audio/microfone.ts e src/audio/boca.ts, com teste em tests/dispositivos-ao-vivo.test.ts, depends on T004 (FR-005) (tests, risk medium)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 7. T006 Separar parada definitiva de reinício no supervisor em src-tauri/src/servicos.rs (cópia de DescritorServico no handle, repetir recria thread, parada definitiva remove registro) e fazer recarregar chamar só repetir em src-tauri/src/ciclo.rs, com testes Rust no próprio arquivo (FR-006) (code, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 8. T007 Mostrar etapas transcrevendo, pensando e falando e os erros de transcrição, resposta e síntese na interface em src/fala/conversa.ts e src/main.ts, com teste em tests/etapas-visiveis.test.ts (FR-007) (tests, risk medium)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 9. T008 Emitir texto progressivo no núcleo e acumular o parcial no estado do pedido em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/pedidos.py, e falar frase por frase sem repetir na reconciliação em src/fala/conversa.ts, com testes em nucleo/tests/test_cerebro_texto_progressivo.py e tests/fala-por-frase.test.ts, depends on T007 (FR-008) (tests, risk medium)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 10. T009 Corrigir modo jogo e volta com executor único em src-tauri/src/ciclo.rs (pasta de configuração, contrato de /pedidos, sem sucesso falso, sem chamar /modo do Python na ida nem na volta, invertendo o teste executar_jogo_sem_ponte_retorna_modo_jogo), com testes Rust no próprio arquivo (FR-009) (code, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 11. T010 Formato interno único de ferramenta convertido nos adaptadores compatível, Anthropic e Gemini, e argumentos acumulados até o fim da chamada, em nucleo/vard/cerebro/provedores.py, com teste em nucleo/tests/test_cerebro_ferramentas_contrato.py (FR-010) (tests, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

### 12. T011 Reescrever README.md e README.en.md com a configuração mínima recomendada e as periféricas congeladas (FR-011) (docs, risk low)

**Attempts**

- _none_

**Corrections**

- _none_

**Escalations**

- _none_

**Grades**

- _not graded_

## Economy

free work: 0% of pieces, 0% of recorded tokens · coordinator: not recorded · 2.0 attempts/piece · mean score 85 · included 100%

- Tokens: free 0, paid exec 0, coordinator 0
- Time: 24 min

## Commit message

```
fix: conversa básica confiável (issue #6)

- Escrever spec, plano e tarefas (specs/001) — opencode:omni/agy/gemini-3.8-flash-tiered, score 85
- T001 Garantir evento terminal em todos os caminhos do despachante em nucleo/vard/cerebro/pedidos.py, com teste em nucleo/tests/test_cerebro_pedidos_terminal.py (FR-001) — unassigned, score -
- T002 Reconsultar o pedido ao reconectar o SSE e periodicamente, com prazo de 90 s sem progresso, cancelando no servidor e exibindo erro visível, em src/fala/conversa.ts, com teste em tests/conversa-pedido-terminal.test.ts (FR-002) — unassigned, score -
- T003 Gravar o par pergunta/resposta no histórico da sessão em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/sessoes.py, com teste em nucleo/tests/test_cerebro_historico.py (FR-003) — unassigned, score -
- T004 Interromper cancela a transcrição em andamento em src/main.ts com a lógica num módulo testável src/fala/ciclo-voz.ts, com teste em tests/ciclo-voz-cancelamento.test.ts (FR-004) — unassigned, score -
- T005 Aplicar no widget a troca de microfone e saída salva nas configurações, ou avisar reinício, em src/main.ts, src/config/config.ts, src/audio/microfone.ts e src/audio/boca.ts, com teste em tests/dispositivos-ao-vivo.test.ts, depends on T004 (FR-005) — unassigned, score -
- T006 Separar parada definitiva de reinício no supervisor em src-tauri/src/servicos.rs (cópia de DescritorServico no handle, repetir recria thread, parada definitiva remove registro) e fazer recarregar chamar só repetir em src-tauri/src/ciclo.rs, com testes Rust no próprio arquivo (FR-006) — unassigned, score -
- T007 Mostrar etapas transcrevendo, pensando e falando e os erros de transcrição, resposta e síntese na interface em src/fala/conversa.ts e src/main.ts, com teste em tests/etapas-visiveis.test.ts (FR-007) — unassigned, score -
- T008 Emitir texto progressivo no núcleo e acumular o parcial no estado do pedido em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/pedidos.py, e falar frase por frase sem repetir na reconciliação em src/fala/conversa.ts, com testes em nucleo/tests/test_cerebro_texto_progressivo.py e tests/fala-por-frase.test.ts, depends on T007 (FR-008) — unassigned, score -
- T009 Corrigir modo jogo e volta com executor único em src-tauri/src/ciclo.rs (pasta de configuração, contrato de /pedidos, sem sucesso falso, sem chamar /modo do Python na ida nem na volta, invertendo o teste executar_jogo_sem_ponte_retorna_modo_jogo), com testes Rust no próprio arquivo (FR-009) — unassigned, score -
- T010 Formato interno único de ferramenta convertido nos adaptadores compatível, Anthropic e Gemini, e argumentos acumulados até o fim da chamada, em nucleo/vard/cerebro/provedores.py, com teste em nucleo/tests/test_cerebro_ferramentas_contrato.py (FR-010) — unassigned, score -
- T011 Reescrever README.md e README.en.md com a configuração mínima recomendada e as periféricas congeladas (FR-011) — unassigned, score -
```

## Issue comment

- 1. Escrever spec, plano e tarefas (specs/001) — opencode:omni/agy/gemini-3.8-flash-tiered, score 85
- 2. T001 Garantir evento terminal em todos os caminhos do despachante em nucleo/vard/cerebro/pedidos.py, com teste em nucleo/tests/test_cerebro_pedidos_terminal.py (FR-001) — unassigned, score -
- 3. T002 Reconsultar o pedido ao reconectar o SSE e periodicamente, com prazo de 90 s sem progresso, cancelando no servidor e exibindo erro visível, em src/fala/conversa.ts, com teste em tests/conversa-pedido-terminal.test.ts (FR-002) — unassigned, score -
- 4. T003 Gravar o par pergunta/resposta no histórico da sessão em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/sessoes.py, com teste em nucleo/tests/test_cerebro_historico.py (FR-003) — unassigned, score -
- 5. T004 Interromper cancela a transcrição em andamento em src/main.ts com a lógica num módulo testável src/fala/ciclo-voz.ts, com teste em tests/ciclo-voz-cancelamento.test.ts (FR-004) — unassigned, score -
- 6. T005 Aplicar no widget a troca de microfone e saída salva nas configurações, ou avisar reinício, em src/main.ts, src/config/config.ts, src/audio/microfone.ts e src/audio/boca.ts, com teste em tests/dispositivos-ao-vivo.test.ts, depends on T004 (FR-005) — unassigned, score -
- 7. T006 Separar parada definitiva de reinício no supervisor em src-tauri/src/servicos.rs (cópia de DescritorServico no handle, repetir recria thread, parada definitiva remove registro) e fazer recarregar chamar só repetir em src-tauri/src/ciclo.rs, com testes Rust no próprio arquivo (FR-006) — unassigned, score -
- 8. T007 Mostrar etapas transcrevendo, pensando e falando e os erros de transcrição, resposta e síntese na interface em src/fala/conversa.ts e src/main.ts, com teste em tests/etapas-visiveis.test.ts (FR-007) — unassigned, score -
- 9. T008 Emitir texto progressivo no núcleo e acumular o parcial no estado do pedido em nucleo/vard/cerebro/laco.py e nucleo/vard/cerebro/pedidos.py, e falar frase por frase sem repetir na reconciliação em src/fala/conversa.ts, com testes em nucleo/tests/test_cerebro_texto_progressivo.py e tests/fala-por-frase.test.ts, depends on T007 (FR-008) — unassigned, score -
- 10. T009 Corrigir modo jogo e volta com executor único em src-tauri/src/ciclo.rs (pasta de configuração, contrato de /pedidos, sem sucesso falso, sem chamar /modo do Python na ida nem na volta, invertendo o teste executar_jogo_sem_ponte_retorna_modo_jogo), com testes Rust no próprio arquivo (FR-009) — unassigned, score -
- 11. T010 Formato interno único de ferramenta convertido nos adaptadores compatível, Anthropic e Gemini, e argumentos acumulados até o fim da chamada, em nucleo/vard/cerebro/provedores.py, com teste em nucleo/tests/test_cerebro_ferramentas_contrato.py (FR-010) — unassigned, score -
- 12. T011 Reescrever README.md e README.en.md com a configuração mínima recomendada e as periféricas congeladas (FR-011) — unassigned, score -

Record: docs/crew-chief/jobs/20261025-1952-fix-conversa-basica-confiavel-issue-6.md
