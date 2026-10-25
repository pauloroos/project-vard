# Revisão do Vard 0.9.8 (Codex, gpt-6.1-sol high)

Feita em 24/10/2026 sobre a main `903f049`, só leitura. Os achados 1 e 2 foram conferidos no código depois. Os demais vêm da leitura do Codex, que reproduziu quatro deles em memória.

**O Vard 0.9.8 expandiu o escopo antes de tornar confiável a conversa básica.** Há problemas concretos de continuidade, cancelamento e recuperação que justificam a experiência ruim descrita.

Revisei a `main`, commit `903f049`, com foco no fluxo de voz e suas dependências. Não alterei arquivos. Além da leitura, reproduzi quatro defeitos em memória, com escrita e acesso externo bloqueados. Não executei o aplicativo, serviços reais ou a suíte completa.

**1. Direção do produto**

Hoje coexistem três produtos:

- Uma interface de voz para OpenJarvis.
- Um assistente próprio, com provedores, sessões, ferramentas e agentes de linha de comando.
- Uma central de automação: reunião, Telegram, pesquisa, resumo da manhã, controle de programas e agentes remotos.

Isso aparece na própria apresentação: o [README.md:34](../../README.md) exige OpenJarvis, enquanto o [CHANGELOG.md:50](../../CHANGELOG.md) afirma que ele deixou de ser necessário. O padrão do código continua sendo OpenJarvis em [src/config/cerebro.ts:3](../../src/config/cerebro.ts).

**O núcleo mínimo deveria ser:** abrir, mostrar se está pronto, captar pelo microfone escolhido, transcrever, responder pelo provedor escolhido, falar na saída escolhida e interromper imediatamente. A segunda pergunta precisa preservar o contexto da primeira. Qualquer falha precisa terminar com uma explicação visível e permitir tentar novamente.

Eu congelaria novas funcionalidades de Telegram, reunião, agentes CLI/remotos, pesquisa e resumo da manhã. Tiraria sala, invisibilidade e personalização avançada do primeiro uso. Manteria OpenJarvis como integração avançada, sem exigir que o usuário entenda a coexistência entre “ponte”, “núcleo”, “cérebro” e “conector”.

O holograma pode continuar como identidade visual. Ele não deve carregar a responsabilidade de explicar sozinho o estado do produto.

**2. O fluxo básico no código**

| Etapa | Comportamento encontrado | Consequência |
|---|---|---|
| Abrir | O Rust inicia serviços; durante migração pode aguardar saúde por até 60 s em [lib.rs:494](../../src-tauri/src/lib.rs). | A abertura precisa explicar preparação e falhas; “ligado” não demonstra que toda a conversa está disponível. |
| Microfone | O microfone começa fechado. Push-to-talk é ignorado enquanto não for aberto em [main.ts:704](../../src/main.ts). | Um usuário que começa pelo atalho pode perceber que nada acontece. |
| Transcrição | Usa a voz própria e, quando habilitado, OpenJarvis como reserva em [main.ts:187](../../src/main.ts). Cada tentativa admite 30 s em [cliente.ts:51](../../src/conectores/openjarvis/cliente.ts). | Pode haver duas esperas consecutivas; o cancelamento dessa etapa está incompleto. |
| Resposta | O núcleo consome os fragmentos do modelo, mas só emite o texto após terminar em [laco.py:155](../../nucleo/vard/cerebro/laco.py) e [laco.py:267](../../nucleo/vard/cerebro/laco.py). | O streaming do provedor não reduz o tempo até o usuário receber a resposta. |
| Fala | A síntese começa após a resposta completa, em [conversa.ts:432](../../src/fala/conversa.ts). Falhas de síntese/reprodução podem ficar apenas no console em [conversa.ts:215](../../src/fala/conversa.ts). | O usuário recebe silêncio sem uma explicação equivalente na interface. |

A latência é estruturalmente somada: silêncio do detector — padrão de 900 ms —, transcrição, geração completa e primeiro áudio. Não medi tempos reais de hardware.

**3. Bugs confirmados, por gravidade**

**1 — Alta · Frontend/backend: um pedido pode terminar no núcleo e deixar o widget preso em “pensando”.**

Referências: [pedidos.py:245](../../nucleo/vard/cerebro/pedidos.py), [conversa.ts:353](../../src/fala/conversa.ts), [cliente.ts:274](../../src/conectores/ponte/cliente.ts).

O despachante captura exceções anteriores ao laço, grava `falhou`, mas não emite evento terminal. O frontend consulta o estado uma vez e depois espera eventos sem prazo. A reconexão do SSE também não reconcilia o pedido.

**Reprodução:** perder a conexão de eventos depois da consulta inicial e concluir o pedido durante a desconexão. O servidor não reproduz eventos antigos; o widget continua esperando. Uma falha anterior ao laço produz o mesmo efeito quando ocorre depois da consulta inicial.

**Correção:** garantir evento terminal em todos os caminhos; consultar novamente ao reconectar e usar consulta periódica enquanto houver pedido ativo. Falha e cancelamento devem liberar a captura e mostrar o motivo.

**Prova em memória:** uma exceção anterior ao laço terminou com estado `falhou` e **zero eventos**.

**2 — Alta · Backend: a conversa esquece o que o usuário disse.**

Referências: [laco.py:82](../../nucleo/vard/cerebro/laco.py), [laco.py:278](../../nucleo/vard/cerebro/laco.py).

A pergunta entra na lista temporária enviada ao modelo. Na persistência, somente a resposta do assistente é adicionada ao histórico.

**Reprodução:** dizer “meu código fictício é AZUL” e depois “qual código eu disse?”. A segunda inferência recebe a resposta anterior, mas não a informação fornecida pelo usuário.

**Correção:** confirmar o par pergunta/resposta no histórico, preservando o limite por trocas completas e uma regra explícita para pedidos cancelados.

**Prova em memória:** a segunda inferência recebeu apenas `assistant: Entendido.` e a nova pergunta.

**3 — Alta · Rust: parar um serviço impede sua retomada pelo mesmo registro.**

Referências: [servicos.rs:181](../../src-tauri/src/servicos.rs), [servicos.rs:282](../../src-tauri/src/servicos.rs), [servicos.rs:24](../../src-tauri/src/servicos.rs), [ciclo.rs:440](../../src-tauri/src/ciclo.rs).

`parar()` deixa o sinal de parada ligado e a thread termina. O registro permanece. `repetir()` apenas sinaliza essa thread, e `iniciar()` recusa um serviço já registrado.

**Reprodução:** executar `recarregar`: ele chama `parar`, espera 500 ms e chama `repetir`. O mecanismo não recria a thread encerrada. Parar e iniciar novamente encontra o mesmo problema de registro.

**Correção:** separar parada definitiva de reinício. `recarregar` deve usar reinício diretamente; uma parada definitiva deve permitir remover e recriar o registro.

**4 — Alta · Rust/backend: modo jogo pode declarar sucesso sem liberar os recursos.**

Referências: [ciclo.rs:464](../../src-tauri/src/ciclo.rs), [ciclo.rs:574](../../src-tauri/src/ciclo.rs), [server.py:778](../../nucleo/server.py), [modo.py:90](../../nucleo/vard/modo.py).

Há dois problemas confirmados:

- O ciclo procura `hud.config.json` na pasta de dados; o comando normal usa a pasta de configuração do aplicativo. Sem encontrar a URL, o código aceita modo jogo como sucesso.
- Quando encontra a URL, Rust chama `/modo`; Python publica o mesmo pedido na caixa IPC para Rust. O percurso volta à fila, sem executar a descarga dos modelos.

Além disso, o cancelamento lê `/pedidos` como um array em [ciclo.rs:545](../../src-tauri/src/ciclo.rs), mas a rota devolve `{"pedidos": [...]}` em [server.py:716](../../nucleo/server.py).

**Reprodução:** ativar modo jogo com supervisor ativo e modelo carregado. O estado pode mudar sem a operação correspondente.

**Correção:** um único executor deve cancelar pedidos e liberar recursos; só publicar `jogo` após confirmação. Corrigir a resolução da configuração e o contrato da listagem.

**5 — Alta · Backend: o contrato das ferramentas perde informações na ida e na volta.**

Referências: [laco.py:134](../../nucleo/vard/cerebro/laco.py), [provedores.py:372](../../nucleo/vard/cerebro/provedores.py), [provedores.py:219](../../nucleo/vard/cerebro/provedores.py).

O laço fornece ferramentas com `name/description/parameters` diretamente. A conversão Anthropic procura esses campos dentro de `function`, gerando nomes vazios.

Separadamente, o adaptador compatível emite uma chamada assim que os argumentos são JSON válido. Uma string inicialmente vazia vira `{}` e a chamada é marcada como emitida; os argumentos posteriores são descartados.

**Reprodução:** receber primeiro nome/ID da ferramenta com argumentos vazios e depois `{"valor":42}`. A chamada emitida contém `{}`.

**Correção:** definir um formato interno único e convertê-lo em cada adaptador. Acumular os argumentos até o encerramento da chamada.

**Provas em memória:** confirmei tanto o nome vazio na conversão quanto os argumentos `{}`.

**6 — Média · Frontend: Interromper não cancela a transcrição em andamento.**

Referências: [main.ts:543](../../src/main.ts), [main.ts:508](../../src/main.ts), [conversa.ts:508](../../src/fala/conversa.ts).

O caminho real chama `transcreverFala(wav)` sem sinal de cancelamento. O botão interrompe a `Conversa`, mas não invalida `cicloVoz` nem cancela esse pedido de transcrição.

**Reprodução:** falar, interromper durante uma transcrição lenta e esperar. O texto ainda pode chegar e iniciar uma resposta. O push-to-talk durante essa espera também fica pendente.

**Correção:** um cancelamento deve cobrir captura, STT, pedido e TTS, invalidando resultados tardios e liberando `ocupado`.

**7 — Média · Frontend: salvar outro dispositivo não muda o áudio do widget nem pede reinício.**

Referências: [aba-voz.ts:846](../../src/ui/aba-voz.ts), [config.ts:200](../../src/config/config.ts), [config.ts:212](../../src/config/config.ts), [main.ts:818](../../src/main.ts).

A preferência é atualizada na memória da janela de configurações. O widget não copia os dispositivos pelo evento de configuração salva. Eles também não aparecem na lista de mudanças que exigem reinício.

**Reprodução:** abrir o microfone A, selecionar B nas configurações e salvar. A captura existente continua em A. Mutar e desmutar não reabre a captura.

**Correção:** aplicar a preferência no widget, reabrindo a entrada em um limite seguro e atualizando a saída; enquanto isso não existir, informar claramente a necessidade de reinício.

**4. Arquitetura: o que simplificar**

**Manteria o supervisor**, porque iniciar e encerrar os próprios processos é responsabilidade legítima de um aplicativo Windows. Simplificaria o controle ao redor dele:

- **Um dono do ciclo de vida:** Rust executa iniciar, parar, reiniciar e liberar recursos. Python pode solicitar essas ações, sem receber de volta uma chamada que apenas republica o mesmo pedido.
- **Um caminho de conversa:** hoje existem conversa direta com OpenJarvis, `/ask` com histórico global e `/pedidos` com sessões persistentes. O `/ask` inclusive preserva pares corretamente em [server.py:437](../../nucleo/server.py), enquanto o caminho novo perde perguntas. Essa duplicação já produz comportamentos diferentes.
- **Um estado operacional confiável:** `ligado` deveria refletir a operação concluída. Há caminhos que retornam `Ligado` após apenas registrar avisos ou sinalizar ações.
- **Legado limitado à migração:** o fallback automático de [modo.py:103](../../nucleo/vard/modo.py) mantém PowerShell como executor alternativo durante o uso normal. Isso dificulta saber quem controla os serviços.
- **Ferramentas fora da conversa mínima:** diário de efeitos, múltiplas CLIs e automação têm custo justificável para executar ações. Não precisam ser requisito para uma pergunta comum responder por voz.

Também há implementação de reserva em [reserva.py:140](../../nucleo/vard/cerebro/reserva.py), mas o executor principal chama o laço diretamente em [server.py:226](../../nucleo/server.py). Eu retiraria da interface qualquer promessa de reserva automática até ligar e validar esse percurso.

**5. Plano de prioridade**

1. Garantir término, erro e recuperação de todo pedido; eliminar espera infinita.
2. Corrigir histórico para a segunda pergunta funcionar.
3. Fazer Interromper cancelar STT, resposta e fala imediatamente.
4. Corrigir seleção de microfone e saída.
5. Recuperar serviços sem exigir fechar e abrir o aplicativo.
6. Mostrar estados separados de preparação, transcrição, geração e fala, com erros visíveis.
7. Entregar texto progressivamente e iniciar voz por frases completas, sem esperar a resposta inteira.
8. Corrigir modo jogo ou retirar temporariamente a promessa de liberar recursos.
9. Suspender ferramentas no caminho básico até corrigir os contratos.
10. Reescrever README e primeiro uso em torno de uma configuração mínima recomendada; congelar as funcionalidades periféricas.

A próxima versão deveria ser julgada por uma sequência curta: abrir, conversar por dez turnos, interromper, trocar dispositivo, recuperar uma falha e continuar. Hoje o código ainda não sustenta essa experiência com consistência.