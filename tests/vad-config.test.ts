import { describe, it, expect, vi } from "vitest";
import { CONFIG_PADRAO, carregarConfig } from "../src/config/config";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
import { invoke } from "@tauri-apps/api/core";

describe("preferências de detecção de voz", () => {
  it("padrão energia e interrupção desligada preservam instalação existente", () => {
    expect(CONFIG_PADRAO).toMatchObject({ vad: "energia", interromper_ao_falar: false });
  });
  it("carrega Silero e interrupção explicitamente escolhidos", async () => {
    vi.mocked(invoke).mockResolvedValue({ vad: "silero", interromper_ao_falar: true });
    expect(await carregarConfig()).toMatchObject({ vad: "silero", interromper_ao_falar: true });
  });
  it("descarta detector inválido salvo manualmente", async () => {
    vi.mocked(invoke).mockResolvedValue({ vad: "outro", interromper_ao_falar: "sim" });
    expect(await carregarConfig()).toMatchObject({ vad: "energia", interromper_ao_falar: false });
  });
});
