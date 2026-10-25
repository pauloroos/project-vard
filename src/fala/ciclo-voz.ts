/**
 * Gerenciamento do ciclo de voz: captura, transcrição e cancelamento explícito (FR-004).
 */

export interface DepsCicloVoz {
  transcrever(wav: ArrayBuffer, sinal: AbortSignal): Promise<string>;
  aoTexto(texto: string, pushToTalk: boolean): Promise<void>;
  aoMudarOcupado?(ocupado: boolean): void;
  aoInterromper?(): void;
  aoFalharTranscricao?(erro: unknown): Promise<void>;
  estaMudo?(): boolean;
  reuniaoAtiva?(): boolean;
}

export class CicloVoz {
  private idCiclo = 0;
  private controllerAtual: AbortController | null = null;
  private _ocupado = false;
  private _pttPendente = false;

  constructor(private d: DepsCicloVoz) {}

  get ocupado(): boolean {
    return this._ocupado;
  }

  get pttPendente(): boolean {
    return this._pttPendente;
  }

  setPttPendente(valor: boolean): void {
    this._pttPendente = valor;
  }

  private setOcupado(valor: boolean): void {
    if (this._ocupado !== valor) {
      this._ocupado = valor;
      this.d.aoMudarOcupado?.(valor);
    }
  }

  /**
   * Executa a etapa de transcrição e entrega o texto ouvido.
   * Cancela qualquer transcrição anterior antes de começar.
   */
  async executar(wav: ArrayBuffer, pushToTalk: boolean): Promise<void> {
    const ciclo = ++this.idCiclo;
    this.controllerAtual?.abort();
    const ac = new AbortController();
    this.controllerAtual = ac;
    this.setOcupado(true);

    try {
      let texto: string;
      try {
        texto = await this.d.transcrever(wav, ac.signal);
      } catch (erro) {
        if (ciclo !== this.idCiclo || this.d.estaMudo?.() || this.d.reuniaoAtiva?.()) return;
        if (ac.signal.aborted) return;
        await this.d.aoFalharTranscricao?.(erro);
        return;
      }

      if (ciclo !== this.idCiclo || ac.signal.aborted || this.d.estaMudo?.() || this.d.reuniaoAtiva?.()) return;
      await this.d.aoTexto(texto, pushToTalk);
    } finally {
      if (ciclo === this.idCiclo) {
        if (this.controllerAtual === ac) {
          this.controllerAtual = null;
        }
        this.setOcupado(false);
      }
    }
  }

  /**
   * Interrompe imediatamente transcrição em andamento, invalida resultados tardios,
   * reseta push-to-talk pendente e libera ocupado.
   */
  interromper(): void {
    ++this.idCiclo;
    if (this.controllerAtual) {
      this.controllerAtual.abort();
      this.controllerAtual = null;
    }
    this._pttPendente = false;
    this.setOcupado(false);
    this.d.aoInterromper?.();
  }
}
