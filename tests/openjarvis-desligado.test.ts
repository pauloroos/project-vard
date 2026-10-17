import { afterEach, expect, it, vi } from "vitest";
import { OpenJarvis } from "../src/conectores/openjarvis/cliente";

afterEach(() => vi.unstubAllGlobals());

it("cliente retido bloqueia toda requisição quando o OpenJarvis é desligado ao vivo", async () => {
  let ligado = true;
  const requisicoes: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    requisicoes.push(url);
    return new Response(JSON.stringify({ available: true, data: [{ id: "modelo-ficticio" }] }));
  });
  const oj = new OpenJarvis("http://127.0.0.1:8765", "", () => ligado);
  expect(await oj.saude()).toBe(true);
  ligado = false;
  requisicoes.length = 0;
  expect(await oj.saude()).toBe(false);
  expect(await oj.fala()).toBe(false);
  await expect(oj.modelos()).rejects.toThrow("OpenJarvis desligado");
  await expect(oj.transcrever(new ArrayBuffer(4), "pt")).rejects.toThrow("OpenJarvis desligado");
  await expect(oj.perguntar([{ role: "user", content: "Olá" }])).rejects.toThrow("OpenJarvis desligado");
  await expect(oj.sintetizar("Olá", "voz-ficticia", 1)).rejects.toThrow("OpenJarvis desligado");
  oj.definirModelo("outro-modelo");
  expect(requisicoes).toEqual([]);
  ligado = true;
  expect(await oj.saude()).toBe(true);
});

it("desligar durante a consulta de modelos impede a pergunta subsequente", async () => {
  let ligado = true;
  const requisicoes: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    requisicoes.push(url);
    ligado = false;
    return new Response(JSON.stringify({ data: [{ id: "modelo-ficticio" }] }));
  });
  const oj = new OpenJarvis("http://127.0.0.1:8765", "", () => ligado);
  await expect(oj.perguntar([{ role: "user", content: "Olá" }])).rejects.toThrow("OpenJarvis desligado");
  expect(requisicoes).toEqual(["http://127.0.0.1:8765/v1/models"]);
});
