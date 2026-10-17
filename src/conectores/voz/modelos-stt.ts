// Modelos de transcrição do serviço de voz (/v1/stt/...): catálogo, download, exclusão e troca do ativo.
import type { DispositivoStt } from "../../config/config";

export interface ProgressoStt {
  estado: "parado" | "baixando" | "concluido" | "falhou";
  bytes: number;
  total: number;
  porcentagem: number;
  erro: string | null;
}

export interface ModeloStt {
  id: string;
  nome: string;
  repo: string;
  /** Tamanho aproximado do download, em MB. */
  tamanho_mb: number;
  idioma: "multilingue" | "ingles";
  /** 1 (lento) a 5 (rápido). */
  velocidade: number;
  /** 1 (erra mais) a 5 (mais preciso). */
  precisao: number;
  descricao: string;
  baixado: boolean;
  ativo: boolean;
  progresso: ProgressoStt;
}

export interface EstadoStt {
  modelos: ModeloStt[];
  /** Modelo carregado (id do catálogo, ou o nome vindo da variável). */
  ativo: string;
  /** Escolha atual (auto | cuda | cpu, ou o valor da variável). */
  dispositivo: string;
  /** Dispositivo pedido ao faster-whisper. */
  device: string;
  pronta: boolean;
  carregando: boolean;
  erro: string | null;
}

/** Frases do painel para os códigos de erro do serviço. */
const MENSAGENS: Record<string, string> = {
  modelo_nao_baixado: "Esse modelo ainda não foi baixado: baixe antes de usar.",
  modelo_desconhecido: "O serviço de voz não conhece esse modelo.",
  modelo_em_uso: "Esse modelo está em uso: escolha outro antes de excluir.",
  modelo_baixando: "Esse modelo ainda está baixando.",
  trocando: "Já há uma troca de modelo em andamento.",
  dispositivo_invalido: "Dispositivo inválido.",
  stt_indisponivel: "A transcrição não está instalada no serviço de voz.",
};

export class ClienteModelosStt {
  private base: string;
  private buscar: typeof fetch;

  constructor(url: string, buscar?: typeof fetch) {
    this.base = url.replace(/\/+$/, "");
    this.buscar = buscar ?? ((u, i) => fetch(u, i));
  }

  private async pedir<T>(caminho: string, init: RequestInit = {}): Promise<T> {
    const r = await this.buscar(`${this.base}${caminho}`, init);
    const corpo = await r.json().catch(() => ({})) as Record<string, unknown>;
    if (!r.ok) {
      const codigo = typeof corpo.erro === "string" ? corpo.erro : "";
      throw new Error(MENSAGENS[codigo] ?? `O serviço de voz recusou (${codigo || `HTTP ${r.status}`}).`);
    }
    return corpo as T;
  }

  private postar<T>(caminho: string, corpo?: unknown): Promise<T> {
    return this.pedir<T>(caminho, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo ?? {}),
    });
  }

  listar(): Promise<EstadoStt> { return this.pedir<EstadoStt>("/v1/stt/modelos"); }
  baixar(id: string): Promise<ProgressoStt> { return this.postar(`/v1/stt/modelos/${encodeURIComponent(id)}/baixar`); }
  progresso(id: string): Promise<ProgressoStt> { return this.pedir(`/v1/stt/modelos/${encodeURIComponent(id)}/progresso`); }
  apagar(id: string): Promise<{ ok: boolean }> { return this.postar(`/v1/stt/modelos/${encodeURIComponent(id)}/apagar`); }
  /** Troca o modelo e/ou o dispositivo; a carga corre em segundo plano no serviço. */
  ativar(pedido: { modelo?: string; dispositivo?: DispositivoStt }): Promise<{ ok: boolean; carregando: boolean }> {
    return this.postar("/v1/stt/ativar", pedido);
  }
}
