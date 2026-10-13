import { ErroVoz } from "./cliente";

/**
 * Embrulha um corpo em fluxo com prazo por pedaço: se a próxima leitura demorar mais que `prazoMs`, o fluxo erra com
 * ErroVoz("a voz passou do prazo", true) e a fonte é cancelada (uma queda no meio não pendura o "falando").
 */
export function comPrazoEntrePedacos(corpo: ReadableStream<Uint8Array>, prazoMs: number): ReadableStream<Uint8Array> {
  const leitor = corpo.getReader();
  return new ReadableStream<Uint8Array>({
    pull: async (ctrl) => {
      let relogio: ReturnType<typeof setTimeout> | undefined;
      const estouro = new Promise<never>((_, rej) => {
        relogio = setTimeout(() => rej(new ErroVoz("a voz passou do prazo", true)), prazoMs);
      });
      try {
        // Repete até ter bytes: um pull que volta sem enfileirar nada deixaria a leitura pendurada.
        for (;;) {
          const { done, value } = await Promise.race([leitor.read(), estouro]);
          if (done) { ctrl.close(); return; }
          if (value?.length) { ctrl.enqueue(value); return; }
        }
      } catch (erro) {
        void leitor.cancel().catch(() => {});
        ctrl.error(erro instanceof ErroVoz ? erro : new ErroVoz(`sem conexão com a voz: ${String(erro)}`, true));
      } finally { clearTimeout(relogio); }
    },
    cancel: async () => { await leitor.cancel().catch(() => {}); },
  });
}
