# Vard 0.10.0 — revisão para uso diário

## Objetivo

Modernizar as três telas com uma linguagem futurista leve, validar as ferramentas do agente com testes e evidências reais e reduzir o consumo de memória sem remover funcionalidades.

## Requisitos

- Preservar comportamento, dados, atalhos ABNT2, instância única e acessibilidade; respeitar movimento reduzido e cessar animações quando a janela não estiver visível.
- Documentar e medir processos, incluindo núcleo, MCPs, voz e WebView; estabelecer metas distinguindo medidas de estimativas e fornecer medição por PID no Windows nos quatro cenários solicitados.
- Inventariar ferramentas, conectores, cérebro, voz e recursos nativos; registrar teste, prova real, resultado e limitações por item. Provas reais devem registrar evento de ferramenta e resposta, sem segredos ou dados pessoais.
- Criar tokens visuais, atualizar widget, sala e configurações sem framework novo, com capturas fictícias antes e depois.
- Atualizar versão para 0.10.0, documentação bilíngue, histórico e roteiro Windows; executar verificações disponíveis, revisar as mudanças e integrar por um único PR.

## Suposições e limites

- A main atual de 0.9.9 é a base. Um provedor e um modelo configurados pelo ambiente são usados apenas em provas, sem nomes ou endereços privados nesta documentação.
- Resultados em Linux não comprovam WebView2, instalador, atalhos globais ou áudio físico no Windows. As medições Windows são metas até serem realizadas no PC.
- Ausência de conta, hardware ou serviço para uma ferramenta deve ser registrada como pendente, nunca como prova real aprovada. Testes automatizados e simulados são identificados separadamente.
- Configuração e dados de prova ficam em diretórios temporários externos ao repositório; cada processo iniciado nas provas deve ser encerrado pelo responsável.
- Uma falha na suíte exigida ou conflito de integração impede o merge. Limitações intrínsecas do ambiente são descritas com o comando e erro exatos e encaminhadas para validação no PC.

## Aceitação

Todos os requisitos acima devem ter evidência verificável. Segurança, privacidade e preservação de dados prevalecem sobre mudanças especulativas de desempenho. Uma prova incompleta não deve ser apresentada como concluída.
