// Corta a resposta em frases para a voz começar a falar a primeira enquanto as outras são sintetizadas.

/** Pedaços menores que isto vão junto com a frase anterior ("Pronto!" depois de uma frase longa). */
const MINIMO = 12;
/** Teto do serviço de voz por pedido; pedaço maior é partido numa vírgula ou num espaço. */
const MAXIMO = 400;

// Fim de frase: . ! ? … (repetidos ou não), aspas ou parênteses de fechamento, e depois espaço ou o fim.
// "15.30", "1.200,00" e "youtube.com" não cortam porque o ponto vem colado no caractere seguinte.
const FIM_DE_FRASE = /[.!?…]+["'”’»)\]]*(?=\s|$)/g;
// Abreviações que terminam em ponto sem fechar a frase (olha o texto antes do ponto).
const ABREVIACAO = /(?:^|[\s(])(?:dr|dra|sr|sra|srta|prof|profa|etc|p|p\.\s?ex)$/i;

function cortarLinha(linha: string): string[] {
  const partes: string[] = [];
  let inicio = 0;
  for (const m of linha.matchAll(FIM_DE_FRASE)) {
    const pos = m.index ?? 0;
    if (m[0] === "." && ABREVIACAO.test(linha.slice(inicio, pos))) continue;
    const fim = pos + m[0].length;
    partes.push(linha.slice(inicio, fim).trim());
    inicio = fim;
  }
  partes.push(linha.slice(inicio).trim());
  return partes.filter(Boolean);
}

function partirLonga(frase: string): string[] {
  const saida: string[] = [];
  let resto = frase;
  while (resto.length > MAXIMO) {
    const janela = resto.slice(0, MAXIMO + 1);
    let corte = janela.lastIndexOf(", ") + 1; // a vírgula fica no primeiro pedaço
    if (corte <= 0) corte = janela.lastIndexOf(" ");
    if (corte <= 0) corte = MAXIMO;
    saida.push(resto.slice(0, corte).trim());
    resto = resto.slice(corte).trim();
  }
  if (resto) saida.push(resto);
  return saida;
}

/** Corta em . ! ? … e quebras de linha; junta pedaços curtos ao anterior; sem pontuação final vira uma frase. */
export function cortarEmFrases(texto: string): string[] {
  const pedacos = texto.split(/\r?\n+/).flatMap(cortarLinha).flatMap(partirLonga);
  const frases: string[] = [];
  for (const p of pedacos) {
    const anterior = frases[frases.length - 1];
    if (anterior !== undefined && p.length < MINIMO && anterior.length + 1 + p.length <= MAXIMO) frases[frases.length - 1] = `${anterior} ${p}`;
    else frases.push(p);
  }
  return frases;
}
