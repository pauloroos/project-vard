// ÚNICA tabela de falas fixas do Vard. Nada fora daqui vai para a boca sem passar pelo modelo.
export const FALAS = {
  saudacao: "Oi, usuário.",
  pensando: "Um momento.",
  telaNaoCompartilhada: "A tela não está compartilhada.",
  telaAindaCarregando: "A tela ainda está carregando, senhor. Pergunte de novo.",
  erroModelo: "Não consegui falar com o cérebro.",
  erros: {   // a ponte devolve só o código; nunca texto técnico para a boca
    modelo_fora: "O cérebro não está no ar.",
    visao_fora: "Não consigo ver a tela: o LM Studio está desligado.",
    modelo_demorou: "O cérebro demorou demais.",
    modelo_http: "O cérebro recusou o pedido.",
    modelo_vazio: "O cérebro não chegou a responder.",
    rede: "Falha de rede ao falar com o cérebro.",
    nao_json: "O cérebro respondeu algo que não entendi.",
    segredos: "Falta o arquivo de segredos.",
    modo_script: "Não achei o script do modo.",
    modo_falhou: "O modo não respondeu.",
    origem_recusada: "Pedido de origem estranha recusado.",
  },
  erroOuvido: "Meu ouvido reiniciou.",
  modoJogoConfirmar: "Ativo o modo jogo? Diga sim.",
  modoJogoAtivado: "Modo jogo ativado. Até já.",
};
