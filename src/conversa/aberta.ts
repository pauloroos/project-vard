/**
 * Máquina de estados para conversa aberta contínua (0.6 Painéis, spec T13).
 *
 * Estados: desligado, ouvindo, processando, encerrando.
 * Transições: liga/desliga, fala detectada, silêncio prolongado, reunião/jogo,
 * frase de encerramento, fala curta ignorada.
 *
 * Implementação pura sem efeitos colaterais; timers são representados por
 * callbacks retornados ao chamador.
 */

export type EstadoConversaAberta = "desligado" | "ouvindo" | "processando" | "encerrando";

export interface ConfigConversaAberta {
  /** Tempo de silêncio (ms) após última fala válida antes de encerrar. Padrão 5 min. */
  silencioMs: number;
  /** Mínimo de palavras para considerar uma fala válida. Padrão 2. */
  minPalavras: number;
  /** Tempo máximo de escuta (ms) após ligar sem fala válida. Padrão igual a silencioMs. */
  timeoutMs?: number;
}

export const CONFIG_PADRAO: ConfigConversaAberta = {
  silencioMs: 300_000,
  minPalavras: 2,
};

const FRASES_ENCERRAMENTO = [
  "pode parar de me ouvir",
  "para de me ouvir",
  "não ouvir",
  "parar de ouvir",
  "pode parar",
];

export interface MaquinaConversaAberta {
  estado: EstadoConversaAberta;
  /** Liga o modo conversa aberta. Retorna novo estado. */
  ligar(): EstadoConversaAberta;
  /** Desliga explicitamente. Retorna novo estado. */
  desligar(): EstadoConversaAberta;
  /** Notifica que uma fala foi detectada. Retorna true se aceita, false se ignorada (curta/ruído). */
  falaDetectada(texto: string): boolean;
  /** Notifica que o timer de silêncio expirou. Só tem efeito em 'ouvindo'. */
  silencioExpirou(): EstadoConversaAberta;
  /** Notifica entrada em reunião ou jogo. Desliga automaticamente. */
  contextoMudou(contexto: "reuniao" | "jogo"): EstadoConversaAberta;
  /** Verifica se um texto é frase de encerramento. */
  ehFraseEncerramento(texto: string): boolean;
}

function normalizarTexto(texto: string): string {
  return texto.toLowerCase().replace(/[.,!?;:]/g, "").trim();
}

function contarPalavras(texto: string): number {
  const norm = normalizarTexto(texto);
  if (!norm) return 0;
  return norm.split(/\s+/).length;
}

export function criarMaquinaConversaAberta(cfg: Partial<ConfigConversaAberta> = {}): MaquinaConversaAberta {
  const config: ConfigConversaAberta = {
    ...CONFIG_PADRAO,
    ...cfg,
    timeoutMs: cfg.timeoutMs ?? cfg.silencioMs ?? CONFIG_PADRAO.silencioMs,
  };

  let estado: EstadoConversaAberta = "desligado";

  const maquina: MaquinaConversaAberta = {
    get estado() {
      return estado;
    },

    ligar() {
      if (estado === "desligado") {
        estado = "ouvindo";
      }
      return estado;
    },

    desligar() {
      estado = "desligado";
      return estado;
    },

    falaDetectada(texto: string) {
      if (estado !== "ouvindo") return false;

      // Frase de encerramento → desliga
      if (maquina.ehFraseEncerramento(texto)) {
        estado = "desligado";
        return false;
      }

      // Fala curta → ignora mas mantém ouvindo
      if (contarPalavras(texto) < config.minPalavras) {
        return false;
      }

      // Fala válida → vai para processando
      estado = "processando";
      return true;
    },

    silencioExpirou() {
      if (estado === "ouvindo") {
        estado = "desligado";
      }
      return estado;
    },

    contextoMudou(_contexto: "reuniao" | "jogo") {
      if (estado !== "desligado") {
        estado = "desligado";
      }
      return estado;
    },

    ehFraseEncerramento(texto: string) {
      const norm = normalizarTexto(texto);
      return FRASES_ENCERRAMENTO.some((frase) => norm.includes(frase));
    },
  };

  return maquina;
}

/**
 * Retorna ao estado 'ouvindo' após processamento concluído.
 * Chamado externamente quando a resposta foi entregue.
 */
export function processamentoConcluido(maquina: MaquinaConversaAberta): EstadoConversaAberta {
  if (maquina.estado === "processando") {
    // A máquina é pura e o estado é fechado; usamos desligar()+ligar()
    // para transitar processando → desligado → ouvindo sem efeitos colaterais.
    maquina.desligar();
    maquina.ligar();
  }
  return maquina.estado;
}