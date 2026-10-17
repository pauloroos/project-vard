import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InstalaveisProvedores, type Instalavel } from "../src/ui/instalaveis-provedores";

const ollama: Instalavel = {
  id: "ollama", nome: "Ollama", descricao: "Servidor local de modelos.",
  comando: ["winget", "install", "--id", "Ollama.Ollama", "-e"],
  fonte: "https://docs.ollama.com/windows", tipo_provedor: "ollama",
  url_base: "http://127.0.0.1:11434/v1", tamanho_mb: null, manual: false,
  instalado: false, login: "dispensado", estado: "aguardando", linhas: [],
};

function botao(raiz: HTMLElement, texto: string): HTMLButtonElement {
  const el = [...raiz.querySelectorAll("button")].find(b => b.textContent === texto);
  expect(el, `Botão ${texto}`).toBeTruthy();
  return el!;
}

describe("Instaláveis no Núcleo", () => {
  let raiz: HTMLElement;
  let chamadas: { url: string; corpo?: string }[];
  let item: Instalavel;
  let estado: string;
  beforeEach(() => {
    raiz = document.createElement("div"); document.body.append(raiz);
    chamadas = []; item = { ...ollama }; estado = "instalando";
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url: String(url), corpo: init?.body as string | undefined });
      if (String(url).endsWith("/instalaveis")) return new Response(JSON.stringify({ itens: [item] }));
      if (String(url).endsWith("/andamento")) return new Response(JSON.stringify({ id: item.id, estado, linhas: ["Baixando pacote"] }));
      return new Response(JSON.stringify({ id: item.id, estado: "instalando", linhas: [] }));
    }));
  });
  afterEach(() => { document.body.innerHTML = ""; vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("exige confirmação e informa comando e tamanho antes de instalar", async () => {
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn()).carregar();
    botao(raiz, "Instalar").click();
    expect(raiz.textContent).toContain("winget install --id Ollama.Ollama -e");
    expect(raiz.textContent).toContain("Tamanho não informado pelo fornecedor");
    expect(chamadas.some(c => c.url.endsWith("/instalar"))).toBe(false);
    botao(raiz, "Cancelar").click();
    expect(chamadas.some(c => c.url.endsWith("/instalar"))).toBe(false);
  });

  it("mostra progresso e abre cadastro após concluir uma única vez", async () => {
    vi.useFakeTimers();
    const cadastrar = vi.fn();
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", cadastrar).carregar();
    botao(raiz, "Instalar").click(); botao(raiz, "Confirmar instalação").click();
    await vi.advanceTimersByTimeAsync(0);
    expect(chamadas.find(c => c.url.endsWith("/instalar"))?.corpo).toBe('{"confirmado":true}');
    expect(raiz.textContent).toContain("Baixando pacote");
    estado = "concluido"; item = { ...item, instalado: true };
    await vi.advanceTimersByTimeAsync(800);
    expect(cadastrar).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ id: "ollama", tipo_provedor: "ollama" }));
    await vi.advanceTimersByTimeAsync(2000);
    expect(cadastrar).toHaveBeenCalledTimes(1);
  });

  it("cancela pelo núcleo e interrompe consulta ao fechar o modal", async () => {
    vi.useFakeTimers();
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn()).carregar();
    botao(raiz, "Instalar").click(); botao(raiz, "Confirmar instalação").click();
    await vi.advanceTimersByTimeAsync(0);
    botao(raiz, "Cancelar instalação").click(); await vi.advanceTimersByTimeAsync(0);
    expect(chamadas.some(c => c.url.endsWith("/cancelar"))).toBe(true);
    botao(raiz, "Fechar").click(); const total = chamadas.length;
    await vi.advanceTimersByTimeAsync(3000); expect(chamadas).toHaveLength(total);
  });

  it("CLI sem login só abre terminal ao clicar e permite cadastrar depois", async () => {
    item = { ...ollama, id: "claude", nome: "Claude Code", tipo_provedor: "cli-claude", instalado: true, login: "ausente" };
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn()).carregar();
    expect(raiz.textContent).toContain("Falta entrar na conta");
    expect(chamadas.some(c => c.url.endsWith("/login"))).toBe(false);
    botao(raiz, "Entrar na conta").click();
    await vi.waitFor(() => expect(raiz.textContent).toContain("Terminal aberto"));
    expect(chamadas.some(c => c.url.endsWith("/login"))).toBe(true);
  });

  it("manual oferece link oficial sem disparar instalação", async () => {
    item = { ...ollama, id: "agy", nome: "Antigravity", manual: true, comando: [], fonte: "https://antigravity.google/docs/cli/install/" };
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn()).carregar();
    botao(raiz, "Instruções de instalação").click();
    expect(raiz.querySelector("a")?.href).toBe(item.fonte);
    expect(chamadas).toHaveLength(1);
  });

  it("falha fica visível e não cadastra provedor", async () => {
    vi.useFakeTimers(); estado = "falhou";
    const cadastrar = vi.fn();
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", cadastrar).carregar();
    botao(raiz, "Instalar").click(); botao(raiz, "Confirmar instalação").click();
    await vi.advanceTimersByTimeAsync(0);
    expect(raiz.textContent).toContain("Falhou"); expect(cadastrar).not.toHaveBeenCalled();
  });

  it("CLI instalada e já cadastrada como provedor some das sugestões", async () => {
    item = { ...ollama, id: "claude", nome: "Claude Code", tipo_provedor: "cli-claude", instalado: true, login: "dispensado" };
    const cadastrar = vi.fn();
    // O id do provedor nasce do nome digitado; o que liga o cadastro ao instalável é o tipo.
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", cadastrar, () => [{ id: "meu-claude", tipo: "cli-claude" }]).carregar();
    const botoes = [...raiz.querySelectorAll("button")].map(b => b.textContent?.trim());
    expect(botoes).not.toContain("Cadastrar provedor");
    expect(raiz.querySelector('[data-id="instalar-claude"]')).toBeNull();
  });

  it("provedor cadastrado não é sugerido para instalar mesmo quando o núcleo não acha o programa", async () => {
    item = { ...ollama, id: "lmstudio", nome: "LM Studio", tipo_provedor: "lmstudio", url_base: "http://127.0.0.1:1234/v1", instalado: false };
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn(), () => [{ id: "lm-studio", tipo: "lmstudio" }]).carregar();
    expect([...raiz.querySelectorAll("button")].some(b => b.textContent === "Instalar")).toBe(false);
    expect(raiz.querySelector('[data-id="instalar-lmstudio"]')).toBeNull();
    expect(raiz.textContent).toContain("Nada a sugerir");
  });

  it("cadastrada sem login continua visível só para entrar na conta", async () => {
    item = { ...ollama, id: "claude", nome: "Claude Code", tipo_provedor: "cli-claude", instalado: true, login: "ausente" };
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn(), () => [{ id: "claude", tipo: "cli-claude" }]).carregar();
    const botoes = [...raiz.querySelectorAll("button")].map(b => b.textContent?.trim());
    expect(botoes).toContain("Entrar na conta");
    expect(botoes).not.toContain("Cadastrar provedor");
  });

  it("OpenJarvis instalado não aparece nas sugestões: ele já tem card fixo", async () => {
    item = { ...ollama, id: "openjarvis", nome: "OpenJarvis", tipo_provedor: "", url_base: "", instalado: true };
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", vi.fn(), () => []).carregar();
    expect(raiz.querySelector('[data-id="instalar-openjarvis"]')).toBeNull();
  });

  it("CLI instalada mas não cadastrada ainda mostra 'Cadastrar provedor'", async () => {
    item = { ...ollama, id: "claude", nome: "Claude Code", tipo_provedor: "cli-claude", instalado: true, login: "dispensado" };
    const cadastrar = vi.fn();
    await new InstalaveisProvedores(raiz, "http://127.0.0.1:4700", cadastrar, () => [{ id: "lm", tipo: "lmstudio" }]).carregar();
    const botoes = [...raiz.querySelectorAll("button")].map(b => b.textContent?.trim());
    expect(botoes).toContain("Cadastrar provedor");
  });
});
