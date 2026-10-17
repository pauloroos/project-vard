/**
 * Aba Transcrição: modelos do faster-whisper do serviço de voz em cards (baixar com progresso, usar, excluir)
 * e o dispositivo onde a transcrição roda. A troca vale na hora (o serviço recarrega em segundo plano) e
 * fica gravada no hud.config.json (stt_modelo, stt_dispositivo), que o serviço lê ao abrir.
 */
import { DISPOSITIVOS_STT, type Config, type DispositivoStt } from "../config/config";
import { ClienteModelosStt, type EstadoStt, type ModeloStt } from "../conectores/voz/modelos-stt";
import { abrirModal, desenharCards, type Card, type TomSelo } from "./componentes";

export interface DepsAbaTranscricao {
  /** Endereço do serviço de voz (cfg.voz_url); vazio = sem serviço. */
  vozUrl: () => string;
  config: Config;
  /** Grava só as chaves dadas no hud.config.json. */
  salvar: (parcial: Partial<Pick<Config, "stt_modelo" | "stt_dispositivo">>) => Promise<void>;
  dizer: (texto: string, ruim?: boolean) => void;
  /** fetch alternativo (testes). */
  fetch?: typeof fetch;
  /** Intervalo da consulta enquanto há download ou troca em andamento. */
  intervaloMs?: number;
}

const ROTULOS_DISPOSITIVO: Record<DispositivoStt, string> = { auto: "Automático", cuda: "GPU (CUDA)", cpu: "CPU" };

/** "●●●○○" para notas de 1 a 5. */
const barras = (n: number) => { const v = Math.max(0, Math.min(5, Math.round(n))); return "●".repeat(v) + "○".repeat(5 - v); };

/** 145 → "145 MB"; 1620 → "1,6 GB". */
export function tamanhoAproximado(mb: number): string {
  return mb >= 1000 ? `${(mb / 1000).toFixed(1).replace(".", ",")} GB` : `${Math.round(mb)} MB`;
}

const rotuloDevice = (d: string) => (ROTULOS_DISPOSITIVO as Record<string, string>)[d] ?? d;
const ehDispositivo = (d: unknown): d is DispositivoStt => (DISPOSITIVOS_STT as readonly unknown[]).includes(d);

export class AbaTranscricao {
  private status!: HTMLElement;
  private seletor!: HTMLSelectElement;
  private cards!: HTMLElement;
  private estado: EstadoStt | null = null;
  private ultimos = new Map<string, string>();
  private ativa = false;
  private relogio: ReturnType<typeof setTimeout> | null = null;

  constructor(private raiz: HTMLElement, private deps: DepsAbaTranscricao) {}

  montar() {
    const nota = document.createElement("p");
    nota.className = "nota";
    nota.textContent = "Modelo que transcreve a sua fala, no serviço de voz do Vard. Modelos maiores erram menos, mas pesam mais; na GPU ficam bem mais rápidos.";
    const linha = document.createElement("label");
    linha.textContent = "Dispositivo";
    this.seletor = document.createElement("select");
    this.seletor.id = "trn-dispositivo";
    for (const d of DISPOSITIVOS_STT) {
      const o = document.createElement("option");
      o.value = d;
      o.textContent = ROTULOS_DISPOSITIVO[d];
      this.seletor.append(o);
    }
    this.seletor.value = this.deps.config.stt_dispositivo || "auto";
    this.seletor.addEventListener("change", () => { void this.trocarDispositivo(); });
    linha.append(this.seletor);
    this.status = document.createElement("p");
    this.status.id = "trn-status";
    this.status.className = "nota";
    this.status.setAttribute("role", "status");
    this.cards = document.createElement("div");
    this.cards.id = "trn-cards";
    this.raiz.append(nota, linha, this.status, this.cards);
  }

  /** Aba aberta: consulta e acompanha downloads/trocas em andamento. */
  ativar() { this.ativa = true; void this.atualizar(); }

  desativar() {
    this.ativa = false;
    if (this.relogio) { clearTimeout(this.relogio); this.relogio = null; }
  }

  private cliente(): ClienteModelosStt | null {
    const url = this.deps.vozUrl().trim();
    return url ? new ClienteModelosStt(url, this.deps.fetch) : null;
  }

  /** Lê o estado do serviço e redesenha (também usado pelos testes para esperar a carga). */
  async atualizar() {
    const cliente = this.cliente();
    if (!cliente) { this.foraDoAr("Sem endereço do serviço de voz: configure na aba Voz."); return; }
    try {
      this.estado = await cliente.listar();
    } catch {
      this.foraDoAr("O serviço de voz não respondeu; os modelos aparecem quando ele estiver no ar.");
      return;
    }
    if (!this.deps.config.stt_dispositivo && ehDispositivo(this.estado.dispositivo)) this.seletor.value = this.estado.dispositivo;
    this.avisarConcluidos(this.estado.modelos);
    this.desenhar();
    this.agendar();
  }

  private foraDoAr(texto: string) {
    this.estado = null;
    this.status.textContent = texto;
    this.cards.innerHTML = "";
  }

  /** Download que terminou desde a última leitura vira recado no rodapé. */
  private avisarConcluidos(modelos: ModeloStt[]) {
    for (const m of modelos) {
      const antes = this.ultimos.get(m.id);
      if (antes === "baixando" && m.progresso.estado === "concluido") this.deps.dizer(`${m.nome} baixado.`);
      if (antes === "baixando" && m.progresso.estado === "falhou") this.deps.dizer(`Falha ao baixar ${m.nome}: ${m.progresso.erro ?? "erro desconhecido"}`, true);
      this.ultimos.set(m.id, m.progresso.estado);
    }
  }

  private agendar() {
    if (this.relogio) { clearTimeout(this.relogio); this.relogio = null; }
    const e = this.estado;
    const andamento = !!e && (e.carregando || e.modelos.some((m) => m.progresso.estado === "baixando"));
    if (!this.ativa || !andamento) return;
    this.relogio = setTimeout(() => { this.relogio = null; void this.atualizar(); }, this.deps.intervaloMs ?? 1000);
  }

  private desenhar() {
    const e = this.estado!;
    const ativo = e.modelos.find((m) => m.ativo)?.nome ?? (e.ativo || "nenhum");
    let texto = `Em uso: ${ativo} · ${rotuloDevice(e.device)}`;
    if (e.carregando) texto += " · Carregando o modelo em segundo plano; a próxima fala espera a carga terminar.";
    else if (!e.pronta) texto += " · ainda carregando.";
    if (e.erro) texto += ` · A última troca falhou (${e.erro}); continua o anterior.`;
    this.status.textContent = texto;
    desenharCards(this.cards, e.modelos.map((m) => this.card(m)), { vazio: "O serviço de voz não listou nenhum modelo.", buscaAPartirDe: 99 });
  }

  private card(m: ModeloStt): Card {
    const selos: { texto: string; tom: TomSelo }[] = [];
    const p = m.progresso;
    if (m.ativo) selos.push({ texto: "Em uso", tom: "ativo" });
    else if (p.estado === "baixando") selos.push({ texto: `Baixando ${p.porcentagem}%`, tom: "aviso" });
    else if (m.baixado) selos.push({ texto: "Baixado", tom: "ok" });
    else if (p.estado === "falhou") selos.push({ texto: "Falhou", tom: "aviso" });
    const detalhes = [
      `≈ ${tamanhoAproximado(m.tamanho_mb)}`,
      `Velocidade ${barras(m.velocidade)} · Precisão ${barras(m.precisao)}`,
      m.descricao,
    ];
    if (p.estado === "falhou" && p.erro) detalhes.push(`Erro: ${p.erro}`);
    const acoes: Card["acoes"] = [];
    if (p.estado !== "baixando" && !m.ativo) {
      if (m.baixado) {
        acoes.push({ rotulo: "Usar", primaria: true, aoClicar: () => void this.usar(m) });
        acoes.push({ rotulo: "Excluir", perigo: true, aoClicar: () => this.confirmarExclusao(m) });
      } else {
        acoes.push({ rotulo: p.estado === "falhou" ? "Tentar de novo" : "Baixar", primaria: true, aoClicar: () => void this.baixar(m) });
      }
    }
    return {
      id: m.id,
      titulo: m.nome,
      etiqueta: m.idioma === "ingles" ? "Só inglês" : "Multilíngue",
      selos,
      detalhes,
      acoes,
      ...(p.estado === "baixando" ? { progresso: p.porcentagem } : {}),
    };
  }

  private async baixar(m: ModeloStt) {
    try {
      await this.cliente()!.baixar(m.id);
      this.ultimos.set(m.id, "baixando");
      this.deps.dizer(`Baixando ${m.nome} (≈ ${tamanhoAproximado(m.tamanho_mb)})…`);
    } catch (erro) {
      this.deps.dizer(erro instanceof Error ? erro.message : String(erro), true);
    }
    await this.atualizar();
  }

  private async usar(m: ModeloStt) {
    const dispositivo = this.seletor.value as DispositivoStt;
    try {
      await this.cliente()!.ativar({ modelo: m.id, dispositivo });
    } catch (erro) {
      this.deps.dizer(erro instanceof Error ? erro.message : String(erro), true);
      return;
    }
    this.deps.config.stt_modelo = m.id;
    this.deps.config.stt_dispositivo = dispositivo;
    try {
      await this.deps.salvar({ stt_modelo: m.id, stt_dispositivo: dispositivo });
      this.deps.dizer(`Carregando ${m.nome} em segundo plano.`);
    } catch (erro) {
      this.deps.dizer(`O serviço trocou, mas não consegui salvar a escolha: ${erro instanceof Error ? erro.message : String(erro)}`, true);
    }
    await this.atualizar();
  }

  private confirmarExclusao(m: ModeloStt) {
    const corpo = document.createElement("p");
    corpo.textContent = `Excluir ${m.nome}? Os arquivos (≈ ${tamanhoAproximado(m.tamanho_mb)}) saem do disco; dá para baixar de novo depois.`;
    abrirModal({
      titulo: "Excluir modelo",
      corpo,
      acoes: [
        { rotulo: "Cancelar" },
        { rotulo: "Excluir", primaria: true, aoClicar: () => { void this.excluir(m); } },
      ],
    });
  }

  private async excluir(m: ModeloStt) {
    try {
      await this.cliente()!.apagar(m.id);
      this.deps.dizer(`${m.nome} excluído.`);
    } catch (erro) {
      this.deps.dizer(erro instanceof Error ? erro.message : String(erro), true);
    }
    await this.atualizar();
  }

  private async trocarDispositivo() {
    const dispositivo = this.seletor.value as DispositivoStt;
    const cliente = this.cliente();
    if (!cliente) return;
    try {
      await cliente.ativar({ dispositivo });
    } catch (erro) {
      this.deps.dizer(erro instanceof Error ? erro.message : String(erro), true);
      return;
    }
    this.deps.config.stt_dispositivo = dispositivo;
    try {
      await this.deps.salvar({ stt_dispositivo: dispositivo });
      this.deps.dizer(`Transcrição passando para ${ROTULOS_DISPOSITIVO[dispositivo]}; o modelo recarrega em segundo plano.`);
    } catch (erro) {
      this.deps.dizer(`O serviço trocou, mas não consegui salvar a escolha: ${erro instanceof Error ? erro.message : String(erro)}`, true);
    }
    await this.atualizar();
  }
}
