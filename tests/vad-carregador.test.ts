import { it, expect, vi } from "vitest";
vi.mock("@ricky0123/vad-web", () => ({ MicVAD: { new: vi.fn() } }));
import { MicVAD } from "@ricky0123/vad-web";
import { carregarSilero } from "../src/audio/silero";
it("Silero compartilha AudioContext e stream, usa assets locais e libera só seus nós", async () => {
  const start = vi.fn(async () => {}), destroy = vi.fn(async () => {});
  vi.mocked(MicVAD.new).mockResolvedValue({ start, destroy } as unknown as MicVAD);
  const stream = { getTracks: vi.fn() } as unknown as MediaStream;
  const contexto = { close: vi.fn() } as unknown as AudioContext;
  const quadro = vi.fn(); const modelo = await carregarSilero({ stream, contexto }, quadro);
  const o = vi.mocked(MicVAD.new).mock.calls[0][0]!;
  expect(o.audioContext).toBe(contexto); expect(await o.getStream!()).toBe(stream);
  expect(o.baseAssetPath).toBe("/vad/"); expect(o.onnxWASMBasePath).toBe("/vad/"); expect(o.model).toBe("v5");
  await o.pauseStream!(stream); expect(stream.getTracks).not.toHaveBeenCalled();
  o.onFrameProcessed!({ isSpeech: .94, notSpeech: .06 }, new Float32Array()); expect(quadro).toHaveBeenCalledWith(.94);
  await modelo.destruir(); expect(destroy).toHaveBeenCalledOnce(); expect(contexto.close).not.toHaveBeenCalled();
});
