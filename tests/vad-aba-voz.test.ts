import { it, expect, vi } from "vitest";
import { AbaVoz } from "../src/ui/aba-voz";
import { CONFIG_PADRAO, salvarConfig } from "../src/config/config";
import { invoke } from "@tauri-apps/api/core";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => null) }));
vi.mock("../src/audio/dispositivos", () => ({ listarDispositivos: vi.fn(async () => ({ entradas: [], saidas: [] })), definirPreferencia: vi.fn(), obterPreferencia: () => ({}) }));
vi.mock("../src/conectores/voz/cliente", () => ({ Voz: class { async vozes() { return { vozes: [], atual: "" }; } } }));
it("opções da aba Voz gravam detector e interrupção na config", async () => {
  const raiz = document.createElement("div");
  const aba = new AbaVoz(raiz, { ...CONFIG_PADRAO }, { criarOj: vi.fn(), velocidade: () => 1, dizer: vi.fn() });
  aba.montar();
  const detector = raiz.querySelector<HTMLSelectElement>("#cfg-vad");
  expect(detector).not.toBeNull();
  expect(detector!.value).toBe("energia");
  detector!.value = "silero";
  raiz.querySelector<HTMLInputElement>("#cfg-interromper_ao_falar")!.checked = true;
  await salvarConfig({ ...CONFIG_PADRAO, ...aba.ler() });
  expect(invoke).toHaveBeenCalledWith("gravar_config", { config: expect.objectContaining({ vad: "silero", interromper_ao_falar: true }) });
});
