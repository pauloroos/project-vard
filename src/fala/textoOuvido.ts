/**
 * Roteamento único de texto ouvido (T14 + T13).
 *
 * Usado pelo caminho real do VAD (encerrar) e pelos ganchos de dev
 * (__vardOuvido / __vardPergunta). A regra de dispensa do nome é:
 * pushToTalk OU conversaAberta ligada (estado !== "desligado").
 *
 * Extraído para ser testável sem depender do main.ts.
 */

export interface FluxoChamadaLike {
  estado: string;
  usuarioRespondeu(texto: string): { tipo: string; texto?: string }[];
}

export interface ConversaLike {
  aoTextoTranscrito(texto: string, pushToTalk: boolean): Promise<void>;
}

export interface TextoOuvidoDeps {
  fluxoChamada: FluxoChamadaLike;
  conversa: ConversaLike;
  executarAcoesChamada(acoes: { tipo: string; texto?: string }[]): void | Promise<void>;
  /** Estado atual da máquina ConversaAberta (puro, lido no momento da chamada). */
  conversaAbertaEstado: () => "desligado" | "ouvindo" | "processando" | "encerrando";
}

/**
 * Processa um texto já transcrito/injetado. Retorna true se foi roteado para
 * o fluxo de chamada (o chamador não deve continuar); false se seguiu para
 * a conversa normal.
 *
 * Regra de nome: pushToTalk dispensa sempre; caso contrário, o nome também
 * é dispensado quando a conversa aberta está ligada (qualquer estado que
 * não seja "desligado"). O gancho __vardOuvido passa pushToTalk=false e
 * depende dessa segunda condição — igualando o comportamento do VAD real.
 */
export async function processarTextoOuvido(
  deps: TextoOuvidoDeps,
  texto: string,
  pushToTalk: boolean,
): Promise<boolean> {
  // T14: fluxo de chamada tem prioridade sobre a conversa normal.
  if (
    deps.fluxoChamada.estado === "aguardando_resposta" ||
    deps.fluxoChamada.estado === "conversando"
  ) {
    const acoes = deps.fluxoChamada.usuarioRespondeu(texto);
    if (acoes.length) {
      await deps.executarAcoesChamada(acoes);
      return true;
    }
  }

  // Regra unificada de dispensa do nome: pushToTalk OU conversa aberta ligada.
  const conversaAbertaLigada = deps.conversaAbertaEstado() !== "desligado";
  const dispensaNome = pushToTalk || conversaAbertaLigada;

  await deps.conversa.aoTextoTranscrito(texto, dispensaNome);
  return false;
}