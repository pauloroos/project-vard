import type { Estado } from "../fala/conversa";

/**
 * Modo invisível: o widget só aparece enquanto há motivo (conversa em curso (pensando ou falando), canal do modo conversa aberto ou
 * revelado à mão) e some `atrasoMs` depois que o último motivo acaba. Com o modo desligado, sempre visível.
 */
export class Invisibilidade {
  private modo = false;
  private estado: Estado = "repouso";
  private canal = false;
  private revelado = false;
  private mostrado = true;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private aplicar: (visivel: boolean) => void, private atrasoMs = 1500) {}

  visivel(): boolean { return this.mostrado; }
  definirModo(ligado: boolean) { this.modo = ligado; if (!ligado) this.revelado = false; this.decidir(); }
  definirEstado(estado: Estado) { this.estado = estado; this.decidir(); }
  definirCanal(aberto: boolean) { this.canal = aberto; this.decidir(); }
  /** Ctrl+Alt+V ou "Mostrar/ocultar" da bandeja com o modo ligado: revela ou esconde na hora. */
  alternarRevelacao() { this.revelado = !this.revelado; this.decidir(this.revelado ? undefined : 0); }

  /** "ouvindo" não conta (o VAD dispara com qualquer ruído, antes de saber se foi chamado), nem "jogo", "erro" e "fora". "transcrevendo" conta pois a fala já começou. */
  private motivo(): boolean { return !this.modo || this.estado === "transcrevendo" || this.estado === "pensando" || this.estado === "falando" || this.canal || this.revelado; }

  private decidir(atraso = this.atrasoMs) {
    if (this.motivo()) { this.cancelar(); this.mudar(true); return; }
    if (!this.mostrado || this.timer !== null) return;
    if (atraso === 0) { this.mudar(false); return; }
    this.timer = setTimeout(() => { this.timer = null; if (!this.motivo()) this.mudar(false); }, atraso);
  }
  private mudar(v: boolean) { if (this.mostrado !== v) { this.mostrado = v; this.aplicar(v); } }
  private cancelar() { if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; } }
}
