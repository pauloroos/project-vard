/**
 * Formatação de hora legível para avisos (0.6 Painéis, spec T15).
 *
 * Converte timestamp ISO em texto relativo:
 * - "hoje, HH:mm" para avisos do dia atual
 * - "ontem, HH:mm" para avisos do dia anterior
 * - "DD/MM, HH:mm" para avisos mais antigos
 *
 * Função pura; aceita `agora` injetável para testes determinísticos.
 * Entrada inválida retorna string vazia (fallback seguro).
 */

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function formatarHoraMinutos(data: Date): string {
  return `${pad2(data.getHours())}:${pad2(data.getMinutes())}`;
}

function mesmoDia(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function diaAnterior(referencia: Date): Date {
  const d = new Date(referencia);
  d.setDate(d.getDate() - 1);
  return d;
}

export function formatarHoraAviso(iso: string, agora?: Date): string {
  if (!iso || typeof iso !== "string") return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "";

  const ref = agora ?? new Date();
  const hhmm = formatarHoraMinutos(data);

  if (mesmoDia(data, ref)) {
    return `hoje, ${hhmm}`;
  }
  if (mesmoDia(data, diaAnterior(ref))) {
    return `ontem, ${hhmm}`;
  }

  const dd = pad2(data.getDate());
  const mm = pad2(data.getMonth() + 1);
  return `${dd}/${mm}, ${hhmm}`;
}