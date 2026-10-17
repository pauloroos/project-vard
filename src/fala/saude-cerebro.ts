/**
 * Saúde de quem responde, sondada a cada 5 s pelo widget.
 * Com o OpenJarvis ativo, vale a saúde e a fala dele. Sem ele (cerebro=proprio e toggle desligado),
 * vale o núcleo do Vard: se o /status responde, há conexão. A fala vem da voz própria ou da reserva,
 * que têm sondagem própria; por isso não derruba a tela aqui.
 */
export async function sondarCerebro(
  oj: { saude(): Promise<boolean>; fala(): Promise<boolean> } | null,
  nucleo: { status(): Promise<unknown | null> },
): Promise<{ ok: boolean; falaOk: boolean }> {
  if (oj) {
    const ok = await oj.saude();
    return { ok, falaOk: ok ? await oj.fala() : false };
  }
  const ok = (await nucleo.status()) !== null;
  return { ok, falaOk: ok };
}
