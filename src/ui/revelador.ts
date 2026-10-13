/** Compacto: mostra a barra enquanto o mouse está em cima e esconde `atrasoMs` depois que ele sai. */
export class Revelador {
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private atrasoMs: number, private aplicar: (visivel: boolean) => void) {}
  entrou() { this.cancelar(); this.aplicar(true); }
  saiu() {
    this.cancelar();
    this.timer = setTimeout(() => { this.timer = null; this.aplicar(false); }, this.atrasoMs);
  }
  private cancelar() { if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; } }
}
