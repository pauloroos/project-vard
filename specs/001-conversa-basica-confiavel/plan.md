# Implementation Plan: Conversa básica confiável

**Spec**: spec.md

## Summary

Implementação de correções pontuais nos componentes do frontend, núcleo Python e supervisor Rust para solucionar os 7 bugs confirmados e cumprir os 10 itens do plano de prioridade da issue #6, assegurando término determinístico de pedidos, histórico confiável, cancelamento ágil de voz, aplicação de dispositivos de áudio, recuperação de serviços e streaming frase por frase, sem adicionar infraestrutura ou serviços extras. Os bugs de gravidade Alta 4 (modo jogo) e Alta 5 (ferramentas) ficam na fase 4 porque seguem a numeração do plano da issue (itens 8 e 9).

## Technical Context

- **Language/Version**: TypeScript (Node.js 22+, Vite, Vitest + jsdom) em `src/`; Python 3.13 (FastAPI, pytest, AnyIO) em `nucleo/`; Rust (Tauri 2) em `src-tauri/`.
- **Dependencies**: Vitest, `@tauri-apps/api`, FastAPI, httpx, uvicorn, pytest, tokio, reqwest.
- **Storage**: Armazenamento local de configuração (`hud.config.json`) e histórico de sessões em arquivos JSON no disco.
- **Testing**: Vitest (`npm test`, `npm run check` para tipos de src e dos testes), pytest (`pytest nucleo/tests/...`) e `#[cfg(test)]` no Rust. Os testes Rust são validados pelo dono com `cargo test` no Windows e o teste de aceite com microfone e áudio reais é checklist do dono no Windows. Para Python, testes com dependências exclusivas do Windows (`msvcrt`) são isolados, avaliando-se os testes tocados em relação às falhas pré-existentes.

## Project Structure

```text
src/
├── audio/
│   ├── boca.ts                             # FR-005 / T005: aplicação de dispositivo de saída via setSinkId do AudioContext
│   └── microfone.ts                        # FR-005 / T005: atualização do microfone com definirMicrofonePreferido
├── config/
│   └── config.ts                           # FR-005 / T005: notificação de dispositivos salvos e sinalização de reinício
├── fala/
│   ├── ciclo-voz.ts                        # FR-004 / T004: isolamento e cancelamento do ciclo de voz com AbortController
│   └── conversa.ts                         # FR-002, FR-007, FR-008 / T002, T007, T008: polling, etapas visuais e fala frase por frase sem repetição
└── main.ts                                 # FR-004, FR-005, FR-007 / T004, T005, T007: integração do ciclo de voz, dispositivos e UI

nucleo/
├── vard/
│   └── cerebro/
│       ├── laco.py                         # FR-003, FR-008 / T003, T008: histórico de pergunta/resposta e streaming de texto
│       ├── pedidos.py                      # FR-001, FR-008 / T001, T008: garantia de eventos terminais e acúmulo de texto parcial
│       ├── provedores.py                   # FR-010 / T010: contrato de ferramentas nos três adaptadores e acúmulo de argumentos
│       └── sessoes.py                      # FR-003 / T003: persistência confirmada do par pergunta/resposta
tests/
├── ciclo-voz-cancelamento.test.ts          # T004: teste de cancelamento de transcrição e liberação de ocupado
├── conversa-pedido-terminal.test.ts        # T002: teste de reconexão SSE, timeout e consulta periódica
├── dispositivos-ao-vivo.test.ts            # T005: teste de aplicação ao vivo de microfone e saída
├── etapas-visiveis.test.ts                 # T007: teste de transição de etapas e exibição de erros
└── fala-por-frase.test.ts                  # T008: teste de síntese e reprodução frase a frase

nucleo/tests/
├── test_cerebro_ferramentas_contrato.py    # T010: teste de conversão Anthropic, OpenAI compatível e Gemini, e acúmulo de argumentos
├── test_cerebro_historico.py               # T003: teste de persistência do par pergunta/resposta e descarte em falhas
├── test_cerebro_pedidos_terminal.py        # T001: teste de garantia de evento terminal em erro, exceção e cancelamento
└── test_cerebro_texto_progressivo.py       # T008: teste de emissão progressiva de fragmentos de texto e acúmulo parcial

src-tauri/src/
├── ciclo.rs                                # FR-006, FR-009 / T006, T009: recarregar e modo jogo/volta com liberação real de GPU
└── servicos.rs                             # FR-006 / T006: separação de parada definitiva e reinício de serviços

README.md                                   # FR-011 / T011: documentação com configuração mínima e periféricas congeladas (PT-BR)
README.en.md                                # FR-011 / T011: documentação com configuração mínima e periféricas congeladas (EN)
```

## Decisions

- **D1 (Evento terminal no despachante)**: Garantir a emissão de evento terminal (`erro` e/ou `fim`) diretamente em `pedidos.py` (bloco `try...finally`/`except`), pois o despachante é o único componente que enxerga todos os caminhos de execução, inclusive exceções anteriores à criação ou execução do laço de inferência.
- **D2 (Resiliência do widget a desconexões e progresso)**: O widget adota consulta periódica de estado (a cada ~2 s) enquanto houver pedido em andamento e dispara reconsulta imediata no evento `onopen` do SSE. O despachante acumula o texto parcial no estado do pedido a cada evento `texto` (o campo `resposta` da consulta cresce durante o pedido); o widget mantém registro de quanto texto já recebeu para que, ao reconciliar, acrescente somente o restante sem repetir frases já faladas. O prazo de espera conta desde o último progresso (evento recebido ou mudança de `ultimo_seq`/estado na consulta periódica), tolerando até 90 s sem progresso antes de cancelar o pedido no servidor e exibir o erro.
- **D3 (Confirmação estrita de histórico completo)**: O histórico da sessão só é confirmado e gravado no encerramento com sucesso do ciclo, contendo tanto a pergunta do usuário quanto a resposta do assistente como par atômico. Pedidos cancelados ou que resultarem em falha não gravam mensagens incompletas no histórico.
- **D4 (Cancelamento explícito do ciclo de voz)**: Utilização de uma instância dedicada de `AbortController` por ciclo de captura e transcrição em `src/fala/ciclo-voz.ts`. Ao chamar `interromper`, o sinal aborta a requisição de rede do STT, invalida o identificador do ciclo ativo para ignorar respostas tardias e restaura imediatamente o estado livre sem push-to-talk pendente.
- **D5 (Atualização ao vivo de dispositivos de áudio)**: O widget escuta o evento `config-salva`. A troca de dispositivos passa por `src/audio/microfone.ts` (`definirMicrofonePreferido`) e `src/audio/boca.ts` (`setSinkId` do `AudioContext`, não de um elemento de áudio), reabrindo a entrada em limite seguro e reatribuindo a saída; caso a aplicação ao vivo não seja suportada pelo ambiente, exibe-se aviso textual visível informando a necessidade de reiniciar o aplicativo.
- **D6 (Ciclo de vida no supervisor Rust)**: Distinguir parada definitiva de reinício em `servicos.rs`. O registro passa a guardar uma cópia do `DescritorServico` no handle, permitindo que `repetir` recrie a thread de supervisão que já terminou. Em `ciclo.rs`, `recarregar` deixa de chamar `parar` e chama apenas `repetir`. A rotina de parada definitiva remove o registro após o término da thread, permitindo `iniciar` de novo.
- **D7 (Executor único para modo jogo e volta)**: O Rust atua como executor exclusivo do modo jogo e da volta (`executar_voltar`) em `ciclo.rs`. Ele localiza o `hud.config.json` na pasta de configuração do aplicativo, cancela pedidos em andamento lendo o contrato `{"pedidos": [...]}`, finaliza eventuais reuniões ativas, descarrega modelos da memória e desativa os serviços consumidores de GPU (OpenJarvis, voz própria, reunião). Sem ponte configurada ou sem arquivo de configuração, retorna erro explícito em vez de sucesso falso (invertendo o teste existente `executar_jogo_sem_ponte_retorna_modo_jogo`). Na volta, religa núcleo, OpenJarvis e os serviços da fotografia utilizando o mecanismo de reinício de D6, sem chamar `/modo` do Python na ida nem na volta, mantendo o carregamento do modelo sob demanda do provedor (nenhum carregador novo).
- **D8 (Fala imediata frase por frase e reconciliação incremental)**: Fragmentos parciais de texto emitidos pelo núcleo são divididos em frases completas pelo frontend usando a rotina existente de quebra de pontuação, enviando imediatamente cada frase para a fila de síntese e fala sem aguardar o fim da geração da resposta completa. O despachante em `pedidos.py` acumula o texto parcial no estado do pedido a cada evento `texto` (a `resposta` da consulta cresce durante o pedido); o widget guarda quanto texto já recebeu e, ao reconciliar, acrescenta apenas o restante, sem repetir frases já faladas.
- **D9 (Saneamento do contrato de ferramentas)**: Em vez de desabilitar o suporte a ferramentas no caminho básico, o contrato de schemas e argumentos é corrigido e coberto por testes automatizados (D10), eliminando riscos de regressão para a conversa essencial.
- **D10 (Formato interno canônico de ferramentas nos três adaptadores)**: O formato interno único `{name, description, parameters}` é convertido nos três adaptadores de `nucleo/vard/cerebro/provedores.py`: compatível OpenAI → `{"type":"function","function":{name,description,parameters}}` acumulando os argumentos por índice até o fim da chamada (`finish_reason`), impedindo a emissão precoce de `{}` vazio; Anthropic → `{name, description, input_schema}`; Gemini continua aceitando o formato interno diretamente.
- **D11 (Congelamento de funcionalidades periféricas)**: O congelamento de integrações secundárias (Telegram, reuniões, CLIs de agentes, pesquisa web e resumo matinal) é formalizado na documentação (`README.md` e `README.en.md`), mantendo o código existente intacto mas deixando claro o foco na conversa básica confiável.
- **D12 (Escolha de prioridade das fases)**: Os bugs de gravidade Alta 4 (modo jogo / FR-009) e 5 (ferramentas / FR-010) estão alocados na Phase 4 porque seguem a numeração do plano da issue #6 (itens 8 e 9 do plano de prioridades), vindo após a estabilização da conversa principal e recuperação imediata de serviços (itens 1 a 6 da issue na Phase 3).
