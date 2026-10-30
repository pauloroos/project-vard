# Histórico de mudanças

Este arquivo segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) em português do Brasil.
Os instaladores de cada versão ficam na página de [releases](https://github.com/pauloroos/project-vard/releases).

## [Unreleased]

### Corrigido

- `recarregar` volta a subir o serviço: após `parar()` + `repetir()`, a thread supervisora é recriada com novo PID (`servicos.rs`).
- Modo jogo desativado nesta versão: comando e menu da bandeja recusam com mensagem clara "modo jogo indisponível nesta versão"; endpoint `/modo` retorna 503 para `jogo` e sucesso imediato para `voltar` sem tocar na ponte. Pendente para frentes 3/4: liberação real de GPU, caminho correto de config e quebra do laço Rust↔Python.

## [0.9.8] — 2026-10-24

### Corrigido

- Ao abrir, a voz era reiniciada no meio do carregamento do modelo na GPU (uma falha isolada da checagem de saúde
  derrubava o serviço). Agora só duas falhas seguidas reiniciam.
- Depois de Sair, o Vard reabria preso no estado "saindo": a aba Sistema desativava o Modo jogo e os pedidos de
  modo do núcleo não chegavam ao app. Agora a abertura registra a sessão e grava o estado ligado.

## [0.9.7] — 2026-10-17

### Adicionado/Feito

- Configurações reorganizadas: "Voz e áudio" (Voz, Transcrição), "Configurações" (Núcleo, Oficina, Ferramentas,
  Atalhos) e "Sistema". "Quem responde" passa a se chamar Núcleo.
- Aba Transcrição: modelos de transcrição em cards (tamanho, idioma, velocidade e precisão), com baixar, usar e
  excluir, e escolha do dispositivo. A troca acontece em segundo plano, sem derrubar o serviço de voz.
- Núcleo em blocos: quem responde agora, provedores cadastrados, o que falta instalar e opções avançadas recolhidas.
- Voz: escolher uma voz que precisa de chave abre o cadastro da chave na hora; escolher uma voz não instalada
  pergunta se quer instalar e já deixa a voz em uso ao terminar.
- Kokoro sem OpenJarvis: o Kokoro passa a ser motor do serviço de voz do Vard (kokoro-onnx, CPU ou GPU), instalável
  pela aba Voz ("Instalar e usar" baixa o modelo e instala a biblioteca no serviço de voz, sem reiniciar); as vozes
  vêm do serviço. Quem usava o Kokoro pelo OpenJarvis passa ao do serviço de voz quando ele
  estiver instalado.
- Oficina: as habilidades de fábrica podem ser editadas e restauradas ao padrão.
- Telegram: "Trazer do OpenJarvis" na aba Sistema (e pelo assistente) copia o bot e os chats permitidos
  do OpenJarvis para o Vard, com o token direto no cofre, sem mexer no OpenJarvis e sem substituir um
  Telegram já configurado sem confirmação. Com o Telegram no Vard, o OpenJarvis fica desligado.

### Corrigido

- Sem o OpenJarvis, o widget mostrava "sem conexão com o núcleo" com o núcleo no ar.
- O LM Studio cadastrado como provedor ainda aparecia como sugestão de instalação.
- Desligar Resumo da manhã, Pesquisa ou Agente remoto gravava um arquivo de habilidades que não era aceito.
- A seção Telegram da aba Sistema não aparecia na tela; o token digitado agora vai de fato para o cofre e
  o bot liga, religa ou desliga na hora, sem reiniciar o núcleo.

## [0.9.6] — 2026-10-17

### Adicionado/Feito

- Um único aplicativo: o Vard cuida dos serviços sozinho e a bandeja do Windows tem tudo — modo jogo, voltar,
  gravar/encerrar reunião, ouvir/falar, sala, configurações e log. A instalação existente migra sozinha, com
  backup e volta possível.
- O OpenJarvis deixa de ser necessário: só sobe se for quem responde ou se a opção "Manter o OpenJarvis ligado"
  estiver marcada. A transcrição da voz passa a ser feita pelo serviço de voz do Vard.
- Telegram em uma tela simples (Sistema): ligar, token guardado no cofre, "Descobrir meu chat" e "Enviar teste";
  também configurável pelo assistente, sem o token passar por ele.
- Oficina: Resumo da manhã, Pesquisa e Agente remoto como habilidades de fábrica, com o que falta para funcionar.
- Conversa aberta volta a ouvir sozinha depois de cada resposta.

### Corrigido

- Um pedido cancelado deixava a resposta na fila da ferramenta de linha de comando e ela saía no pedido seguinte.
- O encerramento da bandeja antiga confere PID e horário de início antes de agir.

## [0.9.5] — 2026-10-17

### Adicionado/Feito

- O assistente configura o Vard a pedido: novo MCP de configurações com aparência, voz, provedores (cadastrar,
  editar, remover, testar e escolher quem responde), instalação, habilidades e programas. O que instala, apaga ou
  troca quem responde pede confirmação; chaves nunca passam por ele.
- Os MCPs locais passam a funcionar com o cérebro próprio: ferramentas de linha de comando e provedores de API
  também recebem as ferramentas.
- Mudanças feitas pelo assistente aparecem na tela de Configurações e no widget sem reiniciar.
- Oficina (antes "O que eu sei fazer"): habilidades em cards — Capaz (de fábrica), Treinada (cadastrada) e
  Validada (já deu certo) —, com cadastro e edição em modal, exclusão com confirmação, busca e filtro.
- Instalação rápida em "Quem responde": LM Studio, Ollama, Claude Code, Codex e OpenCode com confirmação e
  andamento; Gemini CLI e Antigravity com instruções; o cadastro do provedor abre preenchido ao concluir.
- Voz: escolha de quem fala no topo da seção, com o motor ativo em destaque e o estado de cada motor.
- Aparência: opção "Personalizada" com nome, ao lado das cores prontas.
- Histórico de mudanças (este arquivo).

### Corrigido

- A cor escolhida passa a pintar o holograma e os botões do widget e vale desde a abertura.
- O número da versão volta a acompanhar o código.
- "Quem responde" reconsulta os serviços ao ser aberta, sem precisar recarregar a janela.
- Barra de rolagem dos modais no tema escuro.
- Antigravity como quem responde: o modelo era gravado com o nome de exibição junto e a ferramenta recusava o pedido.

## [0.9.4] — 2026-10-16

### Adicionado/Feito

- Aparência na aba Geral: cor e opacidade do widget.
- Idioma e atualização passaram para a aba Geral; a aba Perfil recebeu os dados da chamada e perfis prontos para escolher.
- Voz: listas de voz principal e reserva, com troca automática quando a principal falha.
- Vard mais leve: o motor de voz é descarregado quando fica ocioso, a reunião só carrega quando é usada, as ferramentas deixam de exigir ambiente Python e há um monitor de uso de recursos.

### Corrigido

- A resposta do cérebro próprio volta a chegar ao widget.
- Pedido natural para ver a tela passa a usar a visão.
- A CLI responde com o nome e a persona que você configurou.
- O botão Testar funciona em todos os provedores, inclusive os que usam chave guardada.
- As chaves guardadas no Windows chegam aos provedores do núcleo.
- A lista de vozes é preenchida já na abertura, com o motor de reserva respeitado.

## [0.9.3] — 2026-10-16

### Adicionado/Feito

- Configurações em cards, com cadastro em janela que abre por cima.
- "Quem responde" reúne os provedores num só lugar, com o que está ativo em destaque.
- Voz: lista de vozes em cards, separada por motor, com cadastro em janela.
- Ferramentas: cards, cadastro em janela e aviso quando o serviço está desligado.
- Detecção das ferramentas de linha de comando instaladas no computador ao cadastrar um provedor.

### Corrigido

- Os provedores passam a ser gravados na pasta que o núcleo lê.
- O serviço de voz sobe e carrega o XTTS mesmo sem o núcleo no ar.
- A lista de vozes fica no topo da seção Voz e mostra o motor no cadastro.
- Campos de busca e do cadastro legíveis no tema escuro.

## [0.9.2] — 2026-10-16

### Adicionado/Feito

- A janela de Configurações passou a ter tamanho fixo, com menu lateral.

### Corrigido

- O cérebro próprio executa os pedidos.
- A CLI e as ferramentas leem linhas grandes (acima de 64 KB).
- A segunda pergunta da mesma sessão reaproveita o leitor da CLI.
- O provedor compatível com OpenAI aceita endereço terminando em `/v1`.
- Arquivos de configuração gravados com BOM deixam de ser ignorados.
- Cancelar um pedido encerra a CLI que ainda estava respondendo.

## [0.9.1] — 2026-10-16

### Adicionado/Feito

- Assistente de primeiro uso também na janela de Configurações.

### Corrigido

- Nada nesta versão.

## [0.9.0] — 2026-10-16

### Adicionado/Feito

- Voz própria com mais motores: Kokoro, Edge e Piper, com reserva local quando o OpenJarvis não está no ar.
- Escolha do motor de fala na aba Voz.
- Transcrição (STT) própria no serviço de voz, com reserva no OpenJarvis.
- Detecção de fala com Silero (opcional) e interrupção falando por cima da resposta.
- Assistente de primeiro uso: tela com os pontos a montar, teste de microfone e voz e conexão do cérebro, com o estado guardado entre aberturas.
- Importação de uma instalação anterior, com prévia, aplicar e reverter.
- Instalador de pacotes opcionais (vozes e reunião) com progresso e ativação quando o serviço responde.
- Reunião como pacote opcional, com tela de instalação e remoção.

### Corrigido

- Nada registrado nesta versão.

## [0.8.0] — 2026-10-16

### Adicionado/Feito

- Escolha do cérebro que responde (conector, modelos locais ou uma ferramenta de linha de comando instalada).
- Supervisor dos processos das ferramentas: cancelar, encerrar e reabrir quando o programa fica enxuto.
- Telegram próprio do cérebro, desligado por padrão.
- Cadastro das ferramentas de linha de comando detectadas no painel de provedores.
- Provedores de API (modelos locais, OpenAI-compatíveis, Anthropic e Google) podem ser usados como cérebro, com a credencial vinda do cofre.
- Resumo da manhã, pesquisa e agente remoto sem depender do OpenJarvis (caminho opcional).
- O OpenJarvis deixou de ser obrigatório.
- Os testes deixam de tocar o computador real.

### Corrigido

- O provedor ativo é lido pelo identificador, aceitando também o formato antigo.
- Erros de tipo que impediam a verificação e a geração do instalador.
- Sessões de linha de comando não deixam processos órfãos.

## [0.7.0] — 2026-10-15

### Adicionado/Feito

- Aplicativo único: o Python e o Vard viajam juntos no instalador, e o núcleo sobe junto com o aplicativo.
- Supervisor de serviços, com prazo, cancelamento e encerramento garantido dos processos.
- Aba Diagnóstico com checagens somente de leitura e uma verificação prévia em texto.
- Bandeja nativa unificada e menu que muda conforme o estado dos serviços.
- Ciclo nativo: ligar, modo jogo e voltar, restaurando microfone, fala e dispositivos.
- Fila de pedidos com caixa de comunicação entre a tela e o núcleo.
- Escolha do microfone e da saída de som no widget, na aba Voz e na reunião.
- Perfil do agente (nome, usuário, tom, personalidade e instruções) com aba e prévia.
- Cérebro próprio: sessões, pedidos em fila, ferramentas, laço com diário de intenção e resultado, e reserva de modelos.
- A persona configurada passa a valer no laço da conversa.
- Rota de saúde, ponto de entrada por linha de comando e verificação da instalação.
- Prova real do aplicativo único em desenvolvimento.

### Corrigido

- Os avisos deixaram de ser falados duas vezes e não mostram mais estados intermediários.
- O texto ouvido e o encerramento da conversa aberta foram unificados.
- O estado dos serviços responde sem travar, com as sondagens em paralelo.

## [0.6.1] — 2026-10-14

### Adicionado/Feito

- Botão Testar na aba Atalhos: confere se o Windows aceitou a combinação.
- Hora legível nos avisos ("hoje, 14:30", "ontem, 09:05").
- Conversa aberta contínua no widget: atalho para ligar e desligar, frase de ativação e encerramento por silêncio, reunião ou jogo.
- Chamada proativa quando algo fica pronto, com opção na aba Avisos.

### Corrigido

- Os atalhos internos foram alinhados aos novos padrões com a tecla Win.
- A chamada proativa funciona também pelo caminho real do microfone, com o prazo da conversa e a opção guardada.

## [0.6.0] — 2026-10-14

### Adicionado/Feito

- Cadastro de provedores, vozes, ferramentas e agentes no painel de Configurações.
- Cofre por tipo e identificador: a credencial é usada sem ser exibida, e voz e ferramentas passam a ler dela.
- Conversa aberta contínua e chamada proativa quando algo fica pronto (base do fluxo).
- Hora legível nos avisos.
- Atalhos migrados para teclas Win, sem conflito com o AltGr do teclado ABNT2.

### Corrigido

- Nada nesta versão.

## [0.5.0] — 2026-10-14

### Adicionado/Feito

- Núcleo em Python dentro do repositório: ponte, ferramentas, oficina, consulta, memória, reunião e agente remoto.
- Serviço de voz opcional e serviço de reunião opcional.
- Scripts de ciclo de vida, instalação do OpenJarvis, provas e troca de instalação com retorno.
- A configuração e os dados do usuário passam a ficar fora do repositório.
- Busca por vazamento de dados no índice e numa lista privada.

### Corrigido

- O script de configuração encontra o patch do OpenJarvis onde ele estiver, e a troca de instalação aceita o caminho informado.
- Fim de linha preservado nos patches.

## [0.4.0] — 2026-10-13

### Adicionado/Feito

- Ouvir e falar separados: dá para desligar só o microfone ou só a voz (`Ctrl+Alt+N`).
- Central de avisos no painel, com contador de não lidos no widget e o resultado das tarefas.
- Avisos falados opcionais.
- Reunião no widget: botão de mudo, marca na tela e aba Reunião no painel.
- Indicador de tarefas em andamento no widget e na bandeja.
- Idioma do reconhecimento em lista e aba "O que eu sei fazer".
- Instância única: abrir o Vard de novo traz a janela para a frente.

### Corrigido

- A captura é descartada durante a reunião, e o painel acompanha o não ouvir e o não falar.
- O aviso é revalidado antes de ser falado.
- A segunda abertura no modo invisível foi corrigida.

## [0.3.0] — 2026-10-13

### Adicionado/Feito

- Aba Sistema: estado da ponte e os botões Ligar, Modo jogo e Desligar, com confirmação em dois cliques.
- Modo conversa: o canal fica aberto por 20 s, sem repetir o nome, e frases de encerramento mutam o microfone.
- Provedores de voz: voz própria (XTTS, com a lista de vozes), a voz do OpenJarvis (Kokoro), ElevenLabs e Gemini, com botão Ouvir.
- A barra de botões abre do lado oposto à borda do monitor.
- Modo invisível: o widget só aparece durante a conversa.
- Aba Atualização: consulta e instala a release do GitHub quando você pede.

### Corrigido

- O atalho do modo invisível mostra a janela escondida antes de revelar.
- O canal não pisca mais durante respostas longas, e zerar o tempo da conversa fecha o canal.
- O download da atualização é limitado, sem arquivo parcial e apenas do GitHub, com o hash conferido quando informado.
- Ajustes no painel (campos de chave e voz) e no fluxo do ElevenLabs.

## [0.2.2] — 2026-10-12

### Adicionado/Feito

- O widget some enquanto a sala (tela cheia) está aberta e volta ao fechar, na mesma posição.

### Corrigido

- Nada nesta versão.

## [0.2.1] — 2026-10-12

### Adicionado/Feito

- Aviso na aba Atalhos quando a combinação escolhida rouba uma tecla do teclado ABNT2.

### Corrigido

- Padrões de atalho sem conflito com o AltGr do ABNT2 (painel `Ctrl+Alt+P`, escuta `Ctrl+Alt+L`).
- Os botões do widget não sobrescrevem mais o que foi salvo no painel; o tamanho tem limite e os avisos aparecem também no modo compacto.

## [0.2.0] — 2026-10-12

### Adicionado/Feito

- Atalhos globais editáveis, com captura pelo teclado, recusa de repetidos e aviso do que o Windows não registrou.
- Modo compacto (só o holograma) e tamanho do widget configurável.
- Painel de configurações em janela própria, com abas e aplicação imediata.
- Escolha do modelo, com reserva informada pela ponte e botão Testar com o tempo.
- Sala em tela cheia num monitor à escolha.
- README em português e inglês.

### Corrigido

- Os dados trocados entre as janelas são validados e o tamanho só muda quando é alterado.
- A aba Modelos avisa do segundo modelo na GPU e a lista deixou de se perder no cache.

## [0.1.0] — 2026-10-12

### Adicionado/Feito

- Primeira versão: widget transparente com bandeja, atalhos, configuração e captura de tela.
- Microfone com detecção de voz e núcleo animado pelo espectro.
- Conversa: ouvir, transcrever, pensar e falar com o OpenJarvis, com falas fixas em cache.
- Núcleo visual com anéis, FFT radial e esfera.
- Ponte opcional: olhos na tela, modo jogo e eventos.
- Fala frase a frase por um serviço de voz local, com reserva no OpenJarvis.
- Painel de configurações, início com o Windows, instalador e README.
- Projeto renomeado para Vard, com o OpenJarvis como primeiro conector.

### Corrigido

- Duplo clique fora do núcleo deixou de maximizar a janela.
- A ponte corrigiu o indicador ao interromper, o microfone e a confirmação que expirava.
- Voz: frase cortada vai para a reserva, falas fixas esperam 2 s e o aquecimento acontece uma vez.
- O nome do usuário ficou configurável e o painel limpa campos opcionais.
