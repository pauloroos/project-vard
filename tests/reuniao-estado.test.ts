import { describe, it, expect, vi } from "vitest";
import { EstadoReuniao } from "../src/reuniao/estado";

function criar() {
  const mudancas: boolean[] = [];
  const e = new EstadoReuniao((ativa) => { mudancas.push(ativa); });
  return { e, mudancas };
}

describe("EstadoReuniao", () => {
  it("comeca_sem_reuniao_e_o_status_da_ponte_decide", () => {
    const { e, mudancas } = criar();
    expect(e.ativa).toBe(false);
    e.atualizarStatus("ativa");
    expect(e.ativa).toBe(true);
    expect(mudancas).toEqual([true]);
    e.atualizarStatus("inativa");
    expect(e.ativa).toBe(false);
    expect(mudancas).toEqual([true, false]);
  });

  it("ausente_e_ponte_fora_contam_como_sem_reuniao", () => {
    const { e, mudancas } = criar();
    e.atualizarStatus("ativa");
    e.atualizarStatus("ausente"); // a reunião caiu (ou o serviço sumiu): desliga
    expect(e.ativa).toBe(false);
    e.atualizarStatus("ativa");
    e.atualizarStatus(null); // ponte fora do ar: não há reunião
    expect(e.ativa).toBe(false);
    expect(mudancas).toEqual([true, false, true, false]);
  });

  it("o_evento_liga_e_desliga_na_hora_sem_esperar_a_sondagem", () => {
    const { e, mudancas } = criar();
    e.aplicarEvento({ tipo: "reuniao", estado: "iniciou", duracao_s: 0, pasta: "2026-10-13_1500", resumo: "" });
    expect(e.ativa).toBe(true);
    e.aplicarEvento({ estado: "encerrou" });
    expect(e.ativa).toBe(false);
    expect(mudancas).toEqual([true, false]);
  });

  it("o_evento_fora_de_ordem_nao_dispara_o_callback", () => {
    const { e, mudancas } = criar();
    e.aplicarEvento({ estado: "encerrou" }); // nunca começou
    e.aplicarEvento({ estado: "iniciou" });
    e.aplicarEvento({ estado: "iniciou" }); // duplicado
    expect(mudancas).toEqual([true]);
    e.aplicarEvento({ estado: "diarizando" });
    e.aplicarEvento({ estado: "ata_pronta" });
    e.aplicarEvento({ estado: "erro" }); // não muda o estado: a sondagem do /status decide
    e.aplicarEvento(null);
    e.aplicarEvento("lixo");
    e.aplicarEvento({});
    expect(e.ativa).toBe(true);
    expect(mudancas).toEqual([true]);
  });

  it("a_sondagem_depois_do_evento_nao_fica_pisca", () => {
    const { e, mudancas } = criar();
    e.aplicarEvento({ estado: "iniciou" });
    e.atualizarStatus("ativa"); // a sondagem atrasada confirma sem avisar de novo
    e.atualizarStatus("ativa");
    expect(mudancas).toEqual([true]);
  });

  it("sem_callback_nao_quebra", () => {
    const e = new EstadoReuniao();
    e.aplicarEvento({ estado: "iniciou" });
    expect(e.ativa).toBe(true);
  });

  it("callback_pode_ser_trocado_depois", () => {
    const e = new EstadoReuniao();
    const f = vi.fn();
    e.aoMudar = f;
    e.aplicarEvento({ estado: "iniciou" });
    expect(f).toHaveBeenCalledWith(true);
  });
});
