import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErroPonte, Ponte } from "../src/conectores/ponte/cliente";

describe("Ponte: Telegram", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const ponte = new Ponte("http://127.0.0.1:4700/");

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("estado_por_get", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ligado: true, chat_permitido: "111", openjarvis: { pode_trazer: false } }) });
    const e = await ponte.telegramEstado();
    expect(e.chat_permitido).toBe("111");
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:4700/telegram");
    expect(fetchMock.mock.calls[0][1].method).toBeUndefined();
  });

  it("trazer_do_openjarvis_manda_so_substituir", async () => {
    await ponte.telegramTrazerOpenJarvis(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:4700/telegram/trazer_openjarvis");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ substituir: true });
  });

  it("configurar_e_sincronizar_por_post", async () => {
    await ponte.telegramConfigurar(false, "111");
    await ponte.telegramSincronizar();
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:4700/telegram/configurar");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ ligado: false, chat: "111" });
    expect(fetchMock.mock.calls[1][0]).toBe("http://127.0.0.1:4700/telegram/sincronizar");
  });

  it("rede_fora_e_http_de_erro_viram_ErroPonte", async () => {
    fetchMock.mockRejectedValueOnce(new Error("sem rede"));
    await expect(ponte.telegramEstado()).rejects.toBeInstanceOf(ErroPonte);
    fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({ erro: "origem_recusada" }) });
    await expect(ponte.telegramEstado()).rejects.toMatchObject({ codigo: "origem_recusada" });
  });

  it("sem_ponte_nao_chama_fetch", async () => {
    await expect(new Ponte("").telegramEstado()).rejects.toMatchObject({ codigo: "sem_ponte" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
