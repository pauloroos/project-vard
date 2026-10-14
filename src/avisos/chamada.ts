/**
 * Fluxo de chamada proativa da Aurora quando um aviso chega (0.6 Painéis, spec T14).
 *
 * Estados: inativo, chamando, aguardando_resposta, lendo_aviso, conversando.
 * Transições: aviso_recebido, usuario_respondeu, timeout, fala_detectada, conversa_encerrada.
 *
 * Implementação pura sem efeitos colaterais; ações (sintetizar, abrir_escuta) são
 * retornadas ao chamador para execução externa.
 */

export type EstadoChamada = "inativo" | "chamando" | "aguardando_resposta" | "lendo_aviso" | "conversando";

export interface ConfigChamada {
  /** Se a chamada proativa está habilitada. Padrão true. */
  habilitada: boolean;
  /** Tempo de escuta (ms) após chamar o usuário. Padrão 30000. */
  timeoutMs: number;
  /** Tempo de conversa (ms) após confirmação de presença. Padrão 15000. */
  conversaMs: number;
}

export const CONFIG_CHAMADA_PADRAO: ConfigChamada = {
  habilitada: true,
  timeoutMs: 30_000,
  conversaMs: 15_000,
};

const RESPOSTAS_PRESENCA = [
  "estou aqui",
  "pode falar",
  "fala",
  "oi",
  "diga",
  "pode dizer",
  "sim",
];

export interface AvisoPendente {
  id: string;
  resumo: string;
}

export interface AcaoChamada {
  tipo: "sintetizar" | "abrir_escuta" | "fechar_escuta";
  texto?: string;
}

export interface FluxoChamada {
  estado: EstadoChamada;
  avisosPendentes: AvisoPendente[];
  /** Notifica que um aviso chegou. Retorna ações a executar. */
  avisoRecebido(aviso: AvisoPendente, contexto: { falarLiberado: boolean; emReuniao: boolean }): AcaoChamada[];
  /** Notifica que o usuário respondeu com presença. Retorna ações a executar. */
  usuarioRespondeu(texto: string): AcaoChamada[];
  /** Notifica que o timeout de espera expirou. Retorna ações a executar. */
  timeoutEspera(): AcaoChamada[];
  /** Notifica que a leitura do aviso foi concluída. Retorna ações a executar. */
  leituraConcluida(): AcaoChamada[];
  /** Notifica que o tempo de conversa encerrou. Retorna ações a executar. */
  conversaEncerrada(): AcaoChamada[];
  /** Verifica se um texto é resposta de presença. */
  ehRespostaPresenca(texto: string): boolean;
}

function normalizarTexto(texto: string): string {
  return texto.toLowerCase().replace(/[.,!?;:]/g, "").trim();
}

export function criarFluxoChamada(cfg: Partial<ConfigChamada> = {}): FluxoChamada {
  const config: ConfigChamada = { ...CONFIG_CHAMADA_PADRAO, ...cfg };
  let estado: EstadoChamada = "inativo";
  let avisosPendentes: AvisoPendente[] = [];

  const fluxo: FluxoChamada = {
    get estado() { return estado; },
    get avisosPendentes() { return [...avisosPendentes]; },

    avisoRecebido(aviso, contexto) {
      const acoes: AcaoChamada[] = [];

      // Se não pode falar ou está em reunião, apenas enfileira
      if (!contexto.falarLiberado || contexto.emReuniao || !config.habilitada) {
        avisosPendentes.push(aviso);
        return acoes;
      }

      // Enfileira o aviso
      avisosPendentes.push(aviso);

      // Se já estava chamando ou aguardando, não reinicia
      if (estado !== "inativo") return acoes;

      // Inicia fluxo de chamada
      estado = "chamando";
      const qtd = avisosPendentes.length;
      const texto = qtd > 1 ? `tenho ${qtd} avisos` : undefined;
      if (texto) acoes.push({ tipo: "sintetizar", texto });
      acoes.push({ tipo: "sintetizar", texto: undefined }); // placeholder para nome do usuário
      acoes.push({ tipo: "abrir_escuta" });
      estado = "aguardando_resposta";
      return acoes;
    },

    usuarioRespondeu(texto) {
      const acoes: AcaoChamada[] = [];
      if (estado !== "aguardando_resposta") return acoes;

      if (!fluxo.ehRespostaPresenca(texto)) return acoes;

      // Usuário confirmou presença → lê o primeiro aviso
      estado = "lendo_aviso";
      const aviso = avisosPendentes.shift();
      if (aviso) {
        acoes.push({ tipo: "sintetizar", texto: aviso.resumo });
      }
      return acoes;
    },

    timeoutEspera() {
      const acoes: AcaoChamada[] = [];
      if (estado !== "aguardando_resposta") return acoes;

      // Sem resposta → volta para inativo, avisos ficam na central
      estado = "inativo";
      acoes.push({ tipo: "fechar_escuta" });
      return acoes;
    },

    leituraConcluida() {
      const acoes: AcaoChamada[] = [];
      if (estado !== "lendo_aviso") return acoes;

      // Abre conversa por alguns segundos
      estado = "conversando";
      acoes.push({ tipo: "abrir_escuta" });
      return acoes;
    },

    conversaEncerrada() {
      const acoes: AcaoChamada[] = [];
      if (estado !== "conversando") return acoes;

      estado = "inativo";
      acoes.push({ tipo: "fechar_escuta" });

      // Se há mais avisos pendentes, poderia reiniciar, mas spec diz "lê em ordem"
      // dentro da mesma sessão; aqui voltamos ao inativo e o próximo aviso dispara novo fluxo.
      return acoes;
    },

    ehRespostaPresenca(texto) {
      const norm = normalizarTexto(texto);
      return RESPOSTAS_PRESENCA.some((r) => norm.includes(r));
    },
  };

  return fluxo;
}