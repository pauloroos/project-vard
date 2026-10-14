/**
 * Seleção de modelo por agente (0.6 Painéis, spec D6).
 *
 * Cada agente tem um modelo padrão e uma lista de modelos disponíveis.
 * Pedido explícito prevalece; sem pedido, usa o padrão ou sugere se houver opções.
 * Modelo desconhecido não despacha; erro claro.
 */
import type { Agente, PaineisConfig } from "../config/paineis";

export interface ResultadoEscolha {
  modelo: string;
  aviso?: string;
}

/** Escolhe o modelo para um agente conforme spec D6. */
export function escolherModelo(
  agente: Agente,
  cfg: PaineisConfig,
  pedido?: string,
): ResultadoEscolha {
  const escolha = cfg.agentes[agente];
  if (!escolha) {
    throw new Error(`agente desconhecido: ${agente}`);
  }

  // Pedido explícito: valida contra a lista de modelos disponíveis
  if (pedido !== undefined && pedido !== "") {
    if (!escolha.modelos.includes(pedido)) {
      throw new Error(
        `modelo "${pedido}" não está na lista do agente ${agente}. Disponíveis: ${escolha.modelos.join(", ") || "(nenhum)"}`,
      );
    }
    return { modelo: pedido };
  }

  // Sem pedido: usa o padrão
  if (escolha.padrao) {
    return { modelo: escolha.padrao };
  }

  // Padrão vazio: verifica a lista
  if (escolha.modelos.length === 0) {
    throw new Error(`nenhum modelo configurado para o agente ${agente}`);
  }

  if (escolha.modelos.length === 1) {
    return { modelo: escolha.modelos[0] };
  }

  // Vários modelos e sem padrão: sugere o primeiro
  return {
    modelo: escolha.modelos[0],
    aviso: `nenhum modelo padrão definido para ${agente}; usando ${escolha.modelos[0]} como sugestão`,
  };
}

/** Valida se um modelo está disponível para o agente. */
export function validarModeloAgente(
  agente: Agente,
  modelo: string,
  cfg: PaineisConfig,
): boolean {
  const escolha = cfg.agentes[agente];
  if (!escolha) return false;
  return escolha.padrao === modelo || escolha.modelos.includes(modelo);
}