import { DetectorDeVoz, type EventoVad } from "./vad";
import type { Microfone } from "./microfone";

type Opcoes = ConstructorParameters<typeof DetectorDeVoz>[0];
export type CarregarSilero = (mic: Pick<Microfone, "contexto" | "stream">, quadro: (probabilidade: number) => void) => Promise<{ destruir(): Promise<void> }>;

/** Mantém energia como reserva; scores do Silero comandam início, fim e teto. */
export class DetectorSelecionavel {
  private energia: DetectorDeVoz;
  private silero: DetectorDeVoz;
  private modelo: Awaited<ReturnType<CarregarSilero>> | null = null;
  private probabilidade = 0;
  private atualizado = -Infinity;
  private geracao = 0;
  constructor(private tipo: "energia" | "silero", o: Opcoes, private carregar: CarregarSilero) {
    this.energia = new DetectorDeVoz(o);
    this.silero = new DetectorDeVoz({ ...o, limiar: .8 });
  }
  async iniciar(mic: Pick<Microfone, "contexto" | "stream">): Promise<void> {
    const g = ++this.geracao;
    if (this.tipo !== "silero") return;
    try {
      const modelo = await this.carregar(mic, p => {
        if (g !== this.geracao) return;
        this.probabilidade = p; this.atualizado = performance.now();
      });
      if (g !== this.geracao) { await modelo.destruir(); return; }
      this.modelo = modelo; this.reset();
    } catch {
      if (g === this.geracao) console.warn("Silero indisponível; usando detector de energia.");
    }
  }
  alimentar(rms: number, agora: number): EventoVad {
    if (!this.modelo) return this.energia.alimentar(rms, agora);
    // Inferência parada não pode manter uma captura aberta indefinidamente.
    const p = performance.now() - this.atualizado < 1000 ? this.probabilidade : 0;
    return this.silero.alimentar(p, agora);
  }
  reset(): void { this.energia.reset(); this.silero.reset(); }
  fechar(): void {
    ++this.geracao;
    const modelo = this.modelo; this.modelo = null; this.reset();
    void modelo?.destruir().catch(() => {});
  }
}

export interface ContextoEscuta {
  falando: boolean; ocupado: boolean; mudo: boolean; reuniao: boolean; jogo: boolean; ptt: boolean; eco: boolean;
}
/** Política compartilhada pelo laço real e pelos testes, antes de alimentar o detector. */
export class ControleCapturaVoz {
  constructor(private interromperAoFalar: boolean, private acoes: { interromper(): void; capturar(): void; encerrar(): void }) {}
  bloqueado(c: ContextoEscuta): boolean {
    return c.mudo || c.reuniao || c.jogo || c.ptt || c.eco || ((c.falando || c.ocupado) && !this.interromperAoFalar);
  }
  processar(ev: EventoVad, c: ContextoEscuta): void {
    if (this.bloqueado(c)) return;
    if (ev === "inicio") {
      if (c.falando || c.ocupado) this.acoes.interromper();
      this.acoes.capturar();
    } else if (ev === "fim" || ev === "teto") this.acoes.encerrar();
  }
}

/** AEC do navegador + filtro conservador de nível/correlação contra ~300 ms da saída. */
export function pareceEco(entrada: Float32Array, referencias: readonly Float32Array[]): boolean {
  const energia = (a: Float32Array) => a.reduce((s, x) => s + x * x, 0);
  const e = energia(entrada);
  if (e < 1e-8) return true;
  for (const saida of referencias) {
    const r = energia(saida);
    if (r < 1e-8) continue;
    // Correlação normalizada: também cobre eco amplificado e inversão de fase.
    let produto = 0;
    for (let i = 0; i < Math.min(entrada.length, saida.length); i++) produto += entrada[i] * saida[i];
    const correlacao = Math.abs(produto) / Math.sqrt(e * r);
    if (correlacao > .75 || (e < r * .36 && correlacao > .3)) return true;
  }
  return false;
}
