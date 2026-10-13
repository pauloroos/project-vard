/** Junta pedidos seguidos (arrastar dispara dezenas de "moved") numa ação só, `ms` depois do último. */
export class Adiador {
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private ms: number, private acao: () => void) {}
  pedir() { this.cancelar(); this.timer = setTimeout(() => { this.timer = null; this.acao(); }, this.ms); }
  cancelar() { if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; } }
}
