import { describe, it, expect, vi, beforeEach } from "vitest";
import { AbaSistemaTelegram } from "../src/ui/aba-sistema";

describe("AbaSistemaTelegram", () => {
  let raiz: HTMLElement;
  let deps: import("../src/ui/aba-sistema").DepsAbaSistemaTelegram & {
    verTelegram: ReturnType<typeof vi.fn>;
    configurarTelegram: ReturnType<typeof vi.fn>;
    descobrirChat: ReturnType<typeof vi.fn>;
    enviarTeste: ReturnType<typeof vi.fn>;
    gravarToken: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    raiz = document.createElement("div");
    const verTelegram = vi.fn().mockResolvedValue({ ligado: false, chat_permitido: "" });
    const configurarTelegram = vi.fn().mockResolvedValue({ ok: true });
    const descobrirChat = vi.fn().mockResolvedValue({ ok: false });
    const enviarTeste = vi.fn().mockResolvedValue({ ok: true });
    const gravarToken = vi.fn().mockResolvedValue({ ok: true });
    deps = {
      verTelegram,
      configurarTelegram,
      descobrirChat,
      enviarTeste,
      gravarToken,
    } as typeof deps;
  });

  it("renderiza_campos_da_secao_telegram", async () => {
    const secao = new AbaSistemaTelegram(raiz, deps);
    await secao.montar();

    // Toggle ligado/desligado
    const toggle = raiz.querySelector("#tg-ligado") as HTMLInputElement | null;
    expect(toggle).not.toBeNull();
    expect(toggle?.type).toBe("checkbox");

    // Campo token (senha)
    const token = raiz.querySelector("#tg-token") as HTMLInputElement | null;
    expect(token).not.toBeNull();
    expect(token?.type).toBe("password");

    // Campo chat permitido
    const chat = raiz.querySelector("#tg-chat") as HTMLInputElement | null;
    expect(chat).not.toBeNull();
    expect(chat?.type).toBe("text");

    // Botão descobrir chat
    const btnDescobrir = raiz.querySelector("#tg-descobrir") as HTMLButtonElement | null;
    expect(btnDescobrir).not.toBeNull();

    // Botão enviar teste
    const btnTeste = raiz.querySelector("#tg-testar") as HTMLButtonElement | null;
    expect(btnTeste).not.toBeNull();
  });

  it("toggle_chama_configurar_telegram", async () => {
    deps.verTelegram.mockResolvedValue({ ligado: false, chat_permitido: "" });
    const secao = new AbaSistemaTelegram(raiz, deps);
    await secao.montar();

    const toggle = raiz.querySelector("#tg-ligado") as HTMLInputElement;
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));

    // Aguarda microtask
    await new Promise((r) => setTimeout(r, 10));
    expect(deps.configurarTelegram).toHaveBeenCalledWith(true, "");
  });

  it("descobrir_chat_preenche_campo_chat", async () => {
    deps.descobrirChat.mockResolvedValue({ ok: true, chat_id: "999888777" });
    const secao = new AbaSistemaTelegram(raiz, deps);
    await secao.montar();

    const btnDescobrir = raiz.querySelector("#tg-descobrir") as HTMLButtonElement;
    btnDescobrir.click();

    await new Promise((r) => setTimeout(r, 10));
    const chat = raiz.querySelector("#tg-chat") as HTMLInputElement;
    expect(chat.value).toBe("999888777");
  });

  it("enviar_teste_chama_endpoint", async () => {
    const secao = new AbaSistemaTelegram(raiz, deps);
    await secao.montar();

    const btnTeste = raiz.querySelector("#tg-testar") as HTMLButtonElement;
    btnTeste.click();

    await new Promise((r) => setTimeout(r, 10));
    expect(deps.enviarTeste).toHaveBeenCalled();
  });

  it("token_nunca_aparece_em_texto_visivel", async () => {
    deps.verTelegram.mockResolvedValue({ ligado: true, chat_permitido: "123" });
    const secao = new AbaSistemaTelegram(raiz, deps);
    await secao.montar();

    // O texto visível da seção não deve conter nenhum token
    const textoVisivel = raiz.textContent || "";
    expect(textoVisivel).not.toContain("TOKEN");
    expect(textoVisivel).not.toContain("token");
  });
});