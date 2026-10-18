/**
 * Saúde de quem responde, sondada a cada 5 s pelo widget.
 * Com o OpenJarvis ativo, vale a saúde e a fala dele. Sem ele (cerebro=proprio e toggle desligado),
 * vale o núcleo do Vard pela /saude (rápida, não consulta LM Studio nem OpenJarvis como o /status).
 * A fala vem da voz própria ou da reserva, que têm sondagem própria; por isso não derruba a tela aqui.
 */

/** Sondagens seguidas sem resposta do núcleo antes de declarar "sem conexão". */
export const FALHAS_PARA_CAIR = 2;

/** Lembra entre sondagens se o núcleo já respondeu e quantas falhas seguidas houve. */
export interface MemoriaSaude { noAr: boolean; falhasSeguidas: number }

export function criarMemoriaSaude(): MemoriaSaude {
  return { noAr: false, falhasSeguidas: 0 };
}

export async function sondarCerebro(
  oj: { saude(): Promise<boolean>; fala(): Promise<boolean> } | null,
  nucleo: { saude(): Promise<boolean> },
  memoria: MemoriaSaude = criarMemoriaSaude(),
): Promise<{ ok: boolean; falaOk: boolean }> {
  if (oj) {
    const ok = await oj.saude();
    return { ok, falaOk: ok ? await oj.fala() : false };
  }
  if (await nucleo.saude()) {
    memoria.noAr = true;
    memoria.falhasSeguidas = 0;
    return { ok: true, falaOk: true };
  }
  // Uma falha isolada (núcleo ocupado por um instante) não derruba quem já estava no ar.
  memoria.falhasSeguidas += 1;
  if (memoria.noAr && memoria.falhasSeguidas < FALHAS_PARA_CAIR) return { ok: true, falaOk: true };
  memoria.noAr = false;
  return { ok: false, falaOk: false };
}
