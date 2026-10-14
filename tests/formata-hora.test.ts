import { describe, it, expect } from "vitest";
import { formatarHoraAviso } from "../src/avisos/formata-hora";

describe("formata-hora (T15)", () => {
  const ref = new Date(2026, 9, 14, 19, 46, 0); // 14/10/2026 19:46

  it("hoje mesma data retorna hoje HH:mm", () => {
    const iso = new Date(2026, 9, 14, 19, 46).toISOString();
    expect(formatarHoraAviso(iso, ref)).toBe("hoje, 19:46");
  });

  it("ontem retorna ontem HH:mm", () => {
    const iso = new Date(2026, 9, 13, 8, 10).toISOString();
    expect(formatarHoraAviso(iso, ref)).toBe("ontem, 08:10");
  });

  it("mais antigo retorna DD/MM HH:mm", () => {
    const iso = new Date(2026, 9, 12, 14, 40).toISOString();
    expect(formatarHoraAviso(iso, ref)).toBe("12/10, 14:40");
  });

  it("entrada invalida nao quebra e retorna string vazia", () => {
    expect(formatarHoraAviso("", ref)).toBe("");
    expect(formatarHoraAviso("nao-e-data", ref)).toBe("");
    expect(formatarHoraAviso(null as unknown as string, ref)).toBe("");
    expect(formatarHoraAviso(undefined as unknown as string, ref)).toBe("");
  });

  it("fuso horario local respeitado via injecao de agora", () => {
    // Ref fixa em 14/10 19:46; aviso às 23:59 do mesmo dia local deve ser "hoje"
    const iso = new Date(2026, 9, 14, 23, 59).toISOString();
    expect(formatarHoraAviso(iso, ref)).toBe("hoje, 23:59");
    // Aviso às 00:01 do dia seguinte local deve ser "DD/MM" (não ontem)
    const iso2 = new Date(2026, 9, 15, 0, 1).toISOString();
    expect(formatarHoraAviso(iso2, ref)).toBe("15/10, 00:01");
  });

  it("ordenacao por iso inalterada (funcao so formata)", () => {
    const a = new Date(2026, 9, 14, 10, 0).toISOString();
    const b = new Date(2026, 9, 14, 11, 0).toISOString();
    // A função é pura de formatação; ordenação é responsabilidade do consumidor.
    // Aqui validamos apenas que ambas formatam corretamente.
    expect(formatarHoraAviso(a, ref)).toBe("hoje, 10:00");
    expect(formatarHoraAviso(b, ref)).toBe("hoje, 11:00");
  });
});