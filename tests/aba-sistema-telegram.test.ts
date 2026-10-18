import { describe, it, expect, vi, beforeEach } from "vitest";
import { AbaSistemaTelegram, depsTelegramDaPonte } from "../src/ui/aba-sistema";

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
describe("AbaSistemaTelegram: trazer do OpenJarvis", () => {
  const esperar = () => new Promise((r) => setTimeout(r, 10));
  const comOj = (pode_trazer: boolean) => ({
    ligado: false, chat_permitido: "", token_configurado: false,
    openjarvis: { disponivel: true, vard_configurado: !pode_trazer, ja_migrado: false, pode_trazer, fonte: "openjarvis", chats: 1, ligado: true },
  });

  function montarDeps(estado: unknown) {
    return {
      verTelegram: vi.fn().mockResolvedValue(estado),
      configurarTelegram: vi.fn().mockResolvedValue({ ok: true }),
      descobrirChat: vi.fn().mockResolvedValue({ ok: false }),
      enviarTeste: vi.fn().mockResolvedValue({ ok: true }),
      gravarToken: vi.fn().mockResolvedValue({ ok: true }),
      sincronizar: vi.fn().mockResolvedValue({ ok: true, rodando: true }),
      trazerDoOpenJarvis: vi.fn().mockResolvedValue({ ok: true, mudou: true, detalhe: "Telegram trazido do OpenJarvis.", rodando: true }),
    };
  }

  it("botao_aparece_so_com_openjarvis_a_trazer_e_vard_vazio", async () => {
    const raiz = document.createElement("div");
    await new AbaSistemaTelegram(raiz, montarDeps(comOj(true))).montar();
    const b = raiz.querySelector("#tg-trazer") as HTMLButtonElement;
    expect(b).not.toBeNull();
    expect(b.hidden).toBe(false);
    expect(b.textContent).toBe("Trazer do OpenJarvis");

    const outra = document.createElement("div");
    await new AbaSistemaTelegram(outra, montarDeps(comOj(false))).montar();
    expect((outra.querySelector("#tg-trazer") as HTMLButtonElement).hidden).toBe(true);

    const sem = document.createElement("div");
    await new AbaSistemaTelegram(sem, montarDeps({ ligado: false, chat_permitido: "" })).montar();
    expect((sem.querySelector("#tg-trazer") as HTMLButtonElement).hidden).toBe(true);
  });

  it("trazer_chama_o_nucleo_recarrega_e_esconde_o_botao", async () => {
    const raiz = document.createElement("div");
    const deps = montarDeps(comOj(true));
    await new AbaSistemaTelegram(raiz, deps).montar();
    deps.verTelegram.mockResolvedValue({ ligado: true, chat_permitido: "111", token_configurado: true,
      openjarvis: { disponivel: true, vard_configurado: true, ja_migrado: true, pode_trazer: false } });
    (raiz.querySelector("#tg-trazer") as HTMLButtonElement).click();
    await esperar();
    expect(deps.trazerDoOpenJarvis).toHaveBeenCalledWith(false);
    expect(deps.verTelegram).toHaveBeenCalledTimes(2);
    expect((raiz.querySelector("#tg-trazer") as HTMLButtonElement).hidden).toBe(true);
    expect((raiz.querySelector("#tg-ligado") as HTMLInputElement).checked).toBe(true);
    expect((raiz.querySelector("#tg-chat") as HTMLInputElement).value).toBe("111");
    expect(raiz.querySelector("#tg-msg")?.textContent).toContain("Telegram trazido do OpenJarvis.");
  });

  it("aviso_do_openjarvis_ligado_aparece", async () => {
    const raiz = document.createElement("div");
    const deps = montarDeps(comOj(true));
    deps.trazerDoOpenJarvis.mockResolvedValue({ ok: true, mudou: true, detalhe: "Telegram trazido do OpenJarvis.", aviso: "Desligue o OpenJarvis." });
    await new AbaSistemaTelegram(raiz, deps).montar();
    (raiz.querySelector("#tg-trazer") as HTMLButtonElement).click();
    await esperar();
    expect(raiz.querySelector("#tg-msg")?.textContent).toContain("Desligue o OpenJarvis.");
  });

  it("vard_ja_configurado_pede_confirmacao_antes_de_substituir", async () => {
    const raiz = document.createElement("div");
    const deps = montarDeps(comOj(true));
    deps.trazerDoOpenJarvis.mockResolvedValueOnce({ ok: false, motivo: "ja_configurado", detalhe: "O Vard já tem um Telegram configurado." });
    await new AbaSistemaTelegram(raiz, deps).montar();
    const b = raiz.querySelector("#tg-trazer") as HTMLButtonElement;
    b.click();
    await esperar();
    expect(b.textContent).toBe("Confirmar substituição");
    b.click();
    await esperar();
    expect(deps.trazerDoOpenJarvis).toHaveBeenNthCalledWith(1, false);
    expect(deps.trazerDoOpenJarvis).toHaveBeenNthCalledWith(2, true);
  });

  it("gravar_token_avisa_o_nucleo_e_limpa_o_campo", async () => {
    const raiz = document.createElement("div");
    const deps = montarDeps({ ligado: true, chat_permitido: "111" });
    await new AbaSistemaTelegram(raiz, deps).montar();
    const campo = raiz.querySelector("#tg-token") as HTMLInputElement;
    campo.value = "123:ficticio";
    campo.dispatchEvent(new Event("change"));
    await esperar();
    expect(deps.gravarToken).toHaveBeenCalledWith("123:ficticio");
    expect(deps.sincronizar).toHaveBeenCalled();
    expect(campo.value).toBe("");
  });

  it("token_guardado_muda_o_placeholder", async () => {
    const raiz = document.createElement("div");
    await new AbaSistemaTelegram(raiz, montarDeps({ ligado: true, chat_permitido: "111", token_configurado: true })).montar();
    expect((raiz.querySelector("#tg-token") as HTMLInputElement).placeholder).toContain("guardado no cofre");
  });
});

describe("depsTelegramDaPonte", () => {
  it("liga_a_secao_ao_nucleo_e_o_token_ao_cofre", async () => {
    const ponte = {
      telegramEstado: vi.fn().mockResolvedValue({ ligado: false, chat_permitido: "" }),
      telegramConfigurar: vi.fn().mockResolvedValue({ ok: true }),
      telegramDescobrirChat: vi.fn().mockResolvedValue({ ok: false }),
      telegramTestar: vi.fn().mockResolvedValue({ ok: true }),
      telegramSincronizar: vi.fn().mockResolvedValue({ ok: true }),
      telegramTrazerOpenJarvis: vi.fn().mockResolvedValue({ ok: true }),
    };
    const cofre = vi.fn().mockResolvedValue(undefined);
    const deps = depsTelegramDaPonte(() => ponte, cofre);
    await deps.verTelegram();
    await deps.configurarTelegram(true, "111");
    await deps.trazerDoOpenJarvis!(true);
    expect(await deps.gravarToken("123:ficticio")).toEqual({ ok: true });
    expect(cofre).toHaveBeenCalledWith("123:ficticio");
    expect(ponte.telegramConfigurar).toHaveBeenCalledWith(true, "111");
    expect(ponte.telegramTrazerOpenJarvis).toHaveBeenCalledWith(true);
  });
});
