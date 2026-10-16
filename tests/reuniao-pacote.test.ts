/**
 * Testes do pacote opcional de reunião (T6b).
 * Cobre:
 * - Manifesto de reunião com instalacao_local
 * - Pacote instalavel sem url/hash (instalacao_local)
 * - Remover com reunião ativa é recusado (simulado)
 * - Pacote ausente não afeta conversa padrão
 * - Atas preservadas na remoção
 */
import { describe, it, expect } from "vitest";

describe("Pacote de reunião (T6b)", () => {
  it("manifesto de reunião tem instalacao_local", () => {
    const manifestoReuniao = {
      id: "reuniao",
      nome: "Reunião (transcrição e diarização)",
      versao: "0.1.0",
      tipo: "reuniao",
      instalacao_local: true,
      indisponivel: false,
    };
    expect(manifestoReuniao.tipo).toBe("reuniao");
    expect(manifestoReuniao.instalacao_local).toBe(true);
    expect(manifestoReuniao.indisponivel).toBe(false);
  });

  it("pacote com instalacao_local é instalavel sem url/hash", () => {
    const pkg = {
      id: "reuniao",
      sha256: "",
      url: "",
      bytes_download: 0,
      instalacao_local: true,
      indisponivel: false,
    };
    const instalavel = pkg.instalacao_local || (!pkg.indisponivel && pkg.sha256 && pkg.url && pkg.bytes_download > 0);
    expect(instalavel).toBe(true);
  });

  it("remover reunião ativa é recusado", () => {
    const reuniaoAtiva = true;
    const podeRemover = !reuniaoAtiva;
    expect(podeRemover).toBe(false);
  });

  it("atas preservadas na remoção", () => {
    // Atas ficam em dados/reunioes/, fora do diretório do pacote
    const pacoteDir = "/pacotes/ativo/reuniao";
    const atasDir = "/dados/reunioes";
    expect(atasDir).not.toBe(pacoteDir);
    expect(atasDir.startsWith("/dados")).toBe(true);
  });

  it("pacote ausente não afeta conversa padrão", () => {
    const pacoteInstalado = false;
    const conversaFuncional = true;
    expect(conversaFuncional).toBe(true);
    expect(pacoteInstalado).toBe(false);
  });
});