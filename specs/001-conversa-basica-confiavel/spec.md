# Conversa basica confiavel

**Created**: 2026-10-25  
**Status**: Draft

## What the user wants

O Vard 0.9.8 expandiu o escopo antes de tornar a conversa básica confiável, apresentando problemas de continuidade, cancelamento, recuperação de serviços e perda de contexto. Esta entrega implementa as correções para os 7 bugs confirmados e os 10 itens do plano de prioridade da issue #6, priorizando os defeitos de gravidade alta e a estabilidade da experiência essencial de voz e texto.

## Stories

### User Story 1 - Conversa que sempre termina e lembra (Priority: P1)

Como usuário do Vard, quero fazer perguntas ao assistente com a certeza de que todo pedido terá uma resposta ou um erro visível, que perguntas subsequentes lembrarão do contexto dito anteriormente, que o comando Interromper cancelará imediatamente transcrição, resposta e fala, que a troca de dispositivos de áudio será respeitada e que serviços parados possam ser retomados sem precisar reiniciar o aplicativo.

**Acceptance Scenarios**:

1. **Given** um pedido em andamento no cérebro próprio, **When** a conexão SSE cair ou ocorrer uma falha antes ou durante o laço de inferência, **Then** o despachante garante a emissão de evento terminal (`erro` e/ou `fim`) e o widget consulta o estado para liberar a captura com motivo visível na interface em vez de travar em "pensando".
2. **Given** um pedido enviado ao núcleo, **When** o despachante captura uma exceção anterior ao laço ou executor não configurado, **Then** o núcleo emite evento terminal e o frontend encerra o ciclo liberando o estado ocupado.
3. **Given** uma conversa recém-iniciada, **When** o usuário disser "meu código fictício é AZUL" e em seguida perguntar "qual código eu disse?", **Then** o histórico persiste o par pergunta/resposta completo e a segunda inferência lembra e responde com o código fornecido.
4. **Given** uma captura de áudio com transcrição lenta em andamento, **When** o usuário acionar o comando Interromper, **Then** a transcrição é abortada imediatamente, resultados tardios são descartados, o estado `ocupado` é liberado e nenhum push-to-talk permanece pendente.
5. **Given** o widget capturando áudio pelo microfone A, **When** o usuário selecionar e salvar o microfone B (ou dispositivo de saída) nas configurações, **Then** o widget aplica a alteração de dispositivo ao vivo reabrindo a entrada em limite seguro e ajustando a saída, ou exibe aviso claro de que é necessário reiniciar quando a reabertura não for suportada.
6. **Given** um serviço gerenciado pelo supervisor Rust que foi parado, **When** o usuário acionar `recarregar`, **Then** o supervisor executa reinício real recriando a thread encerrada em vez de falhar por registro pré-existente ou sinal inativo.

### User Story 2 - Ver e ouvir o andamento (Priority: P2)

Como usuário do Vard, quero acompanhar visualmente cada etapa do processamento (transcrevendo, pensando, falando), ser informado de erros de transcrição, resposta ou síntese diretamente na interface, e ouvir a resposta sendo falada progressivamente frase por frase sem ter que esperar a geração do texto inteiro.

**Acceptance Scenarios**:

1. **Given** uma interação por voz ou texto, **When** o pedido passa pelas fases de reconhecimento, inferência e síntese, **Then** o widget exibe os estados explícitos "transcrevendo", "pensando" e "falando", e se ocorrer qualquer falha em uma dessas etapas, o erro detalhado é exibido visualmente no widget e não apenas no console.
2. **Given** uma resposta longa sendo gerada pelo núcleo, **When** os primeiros fragmentos chegam completando uma frase pontuada, **Then** o núcleo emite eventos `texto` progressivamente e o widget inicia a síntese e reprodução de voz frase por frase sem aguardar a conclusão de todo o texto.

### User Story 3 - Promessas honestas (Priority: P2)

Como usuário do Vard, quero que recursos pesados como GPU sejam liberados de verdade ao ativar o modo jogo antes de qualquer confirmação de sucesso, e que o uso de ferramentas pelo modelo siga um contrato rigoroso que não interfira nem quebre a conversa básica.

**Acceptance Scenarios**:

1. **Given** o sistema em execução com supervisor ativo e serviços ou modelos ocupando a GPU, **When** o modo jogo for solicitado, **Then** o executor único em Rust cancela pedidos pendentes lendo `/pedidos` no contrato correto (`{"pedidos": [...]}`), descarrega os modelos, para os serviços que usam GPU e só então publica o estado `jogo`, reportando erro se a configuração não for encontrada ou a ponte não estiver configurada, sem criar laço de chamada cruzada com o Python.
2. **Given** chamadas de ferramentas pelo modelo, **When** ferramentas forem disponibilizadas e invocadas tanto para Anthropic quanto para provedores compatíveis, **Then** o formato interno único (`name`, `description`, `parameters`) é convertido corretamente com esquemas preservados e argumentos acumulados por índice até o encerramento do fluxo, sem emitir `{}` prematuro nem corromper chamadas subsequentes da conversa.

### User Story 4 - Primeiro uso mínimo (Priority: P3)

Como novo usuário ou desenvolvedor do Vard, quero consultar uma documentação clara em português e inglês com uma configuração mínima recomendada para conversa básica funcional e com funcionalidades periféricas marcadas como congeladas, alinhada ao estado real do produto.

**Acceptance Scenarios**:

1. **Given** o leitor acessando o `README.md` ou `README.en.md`, **When** buscar como configurar o assistente pela primeira vez, **Then** encontra a recomendação mínima de voz própria e um provedor funcional, a indicação de que o OpenJarvis é opcional, e o aviso explícito de que integrações periféricas (Telegram, reunião, CLIs de agentes, pesquisa, resumo da manhã) estão congeladas.

### Open questions and edge cases

- **Pedidos cancelados ou falhos no histórico**: pedidos cancelados ou que terminarem em erro não gravam entradas parciais no histórico da sessão; apenas trocas pergunta/resposta concluídas com sucesso são confirmadas.
- **Troca de dispositivo durante fala em andamento**: se o usuário alterar o dispositivo de saída enquanto uma frase estiver sendo reproduzida, a nova saída passa a valer para a próxima frase da fila ou aplica-se via `setSinkId` no elemento atual se suportado.
- **Modo jogo sem ponte configurada**: a ativação do modo jogo sem ponte/configuração válida deve retornar erro explícito e manter o estado anterior, em vez de retornar sucesso falso.
- **Ambiente de execução e verificações**: neste servidor Linux ARM64 sem `cargo`, hardware de áudio, display Tauri ou GPU, os testes unitários e de lógica para frontend (Vitest) e Python (pytest) são executados localmente; testes Rust são entregues como `#[cfg(test)]` e o teste manual de aceite do fluxo completo de 10 turnos com hardware real fica listado como checklist de validação do dono em ambiente Windows.

## Requirements

- **FR-001**: Todo pedido do cérebro próprio emite evento terminal (`erro` e/ou `fim`) em todos os caminhos, inclusive exceção antes do laço, executor não configurado e cancelamento.
- **FR-002**: O widget nunca espera um pedido para sempre: reconsulta o estado ao reconectar o SSE e periodicamente enquanto houver pedido ativo, com prazo máximo; falha ou cancelamento libera a captura e mostra o motivo.
- **FR-003**: O histórico da sessão grava o par pergunta/resposta de cada troca concluída; pedidos cancelados ou que falharam não gravam nada; o limite continua contado por trocas completas.
- **FR-004**: Interromper cancela a transcrição em andamento, invalida resultados tardios, libera `ocupado` e não deixa o push-to-talk pendente; resposta e fala também são canceladas.
- **FR-005**: Salvar outro microfone ou outra saída nas configurações é aplicado no widget (entrada reaberta num limite seguro, saída atualizada); quando não puder aplicar ao vivo, o widget avisa que precisa reiniciar.
- **FR-006**: Parar um serviço não impede sua retomada: `recarregar` reinicia de fato núcleo e OpenJarvis; uma parada definitiva permite remover e recriar o registro; `repetir` de um serviço cuja thread terminou recria a thread.
- **FR-007**: O widget mostra as etapas transcrevendo, pensando e falando, e mostra na interface os erros de transcrição, de resposta e de síntese/reprodução (não só no console).
- **FR-008**: O núcleo emite o texto progressivamente (eventos `texto` por fragmento) e o widget começa a falar cada frase completa assim que ela chega, sem esperar a resposta inteira.
- **FR-009**: O modo jogo só publica `jogo` depois de cancelar os pedidos e liberar os recursos; a configuração é lida da pasta de configuração correta; sem ponte configurada é erro; a listagem `/pedidos` é lida como `{"pedidos": [...]}`; Rust não chama de volta o `/modo` do Python (sem laço Rust → Python → Rust).
- **FR-010**: Formato interno único de ferramenta (`name`, `description`, `parameters`) convertido em cada adaptador: a conversão Anthropic leva o nome e o esquema corretos; o adaptador compatível acumula os argumentos até o fim da chamada e nunca emite `{}` antes de os argumentos chegarem. Com o contrato corrigido e testado, as ferramentas deixam de ameaçar o caminho básico (item 9 do plano).
- **FR-011**: README.md e README.en.md descrevem uma configuração mínima recomendada (voz e um provedor), coerente com o CHANGELOG sobre o OpenJarvis ser opcional, e declaram congeladas as funcionalidades periféricas.

## Done when

- **SC-001**: Cada FR de código tem um teste que falha antes da correção e passa depois (ou, quando a pilha não permite — Rust sem `cargo` neste servidor, layout, hardware —, o motivo e a verificação mais próxima estão documentados na tarefa).
- **SC-002**: `npm test`, `npx tsc --noEmit` e os testes do núcleo tocados passam; os testes Rust são entregues e listados para o dono rodar `cargo test` no Windows.
- **SC-003**: O teste de aceite da issue (abrir, conversar 10 turnos, interromper, trocar dispositivo, provocar uma falha e continuar) está no PR como checklist do dono no Windows.
