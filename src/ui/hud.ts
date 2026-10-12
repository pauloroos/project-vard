import { invoke } from "@tauri-apps/api/core";
import type { Config } from "../config/config";
import { salvarConfig } from "../config/config";
import type { Estado } from "../fala/conversa";

const ROTULO: Record<Estado, string> = {
  repouso: "pronto", ouvindo: "ouvindo", pensando: "pensando", falando: "falando",
  jogo: "modo jogo", erro: "atenção", fora: "OpenJarvis fora",
};

/** Linha de estado, última fala ouvida, última resposta e botões. Só DOM, sem regra de negócio. */
export class Hud {
  private estado: Estado = "repouso";
  private detalhe = "";
  private ouvido = "";
  private resposta = "";

  constructor(private cfg: Config, private linha: HTMLElement, private botoes: HTMLElement) {
    this.botoes.append(
      this.botao("Texto", "abrir a interface de texto do OpenJarvis", () => { void invoke("abrir_url", { url: cfg.gui_url }); }),
      this.botaoTopo(),
    );
    this.pintar();
  }

  private botao(rotulo: string, dica: string, aoClicar: () => void): HTMLButtonElement {
    const b = document.createElement("button");
    b.textContent = rotulo; b.title = dica;
    b.addEventListener("click", aoClicar);
    return b;
  }

  private botaoTopo(): HTMLButtonElement {
    const b = this.botao("", "sempre no topo", () => { void this.alternarTopo(b); });
    this.rotuloTopo(b);
    return b;
  }

  private rotuloTopo(b: HTMLElement) { b.textContent = this.cfg.sempre_no_topo ? "Topo: sim" : "Topo: não"; }

  private async alternarTopo(b: HTMLElement) {
    const novo = !this.cfg.sempre_no_topo;
    try {
      await invoke("definir_sempre_no_topo", { ligado: novo });
      this.cfg.sempre_no_topo = novo;
      await salvarConfig(this.cfg);
      this.rotuloTopo(b);
    } catch (erro) { console.warn("não consegui alternar o topo", erro); }
  }

  setEstado(e: Estado, detalhe = "") { this.estado = e; this.detalhe = detalhe; this.pintar(); }
  setOuvido(t: string) { this.ouvido = t; this.pintar(); }
  setResposta(t: string) { this.resposta = t; this.pintar(); }
  dica(t: string) { this.linha.textContent = t; }

  private pintar() {
    const base = this.detalhe || ROTULO[this.estado];
    this.linha.textContent = this.ouvido && this.estado !== "fora" && this.estado !== "erro" ? `${base} | ${this.ouvido}` : base;
    this.linha.title = [this.ouvido && `Ouvi: ${this.ouvido}`, this.resposta && `Resposta: ${this.resposta}`].filter(Boolean).join("\n");
  }
}
