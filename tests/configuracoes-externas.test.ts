import { expect, it, vi } from "vitest";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
import { invoke } from "@tauri-apps/api/core";
import { Configuracoes, type DepsConfiguracoes } from "../src/ui/configuracoes";
import { AbaPerfil } from "../src/ui/aba-perfil";
import { PERFIL_PADRAO } from "../src/config/perfil";
import { CONFIG_PADRAO, carregarConfig, salvarConfig, aplicarVozAoVivo, mudancasQueExigemReinicio } from "../src/config/config";

it("recarrega aparência externa sem refazer o formulário nem perder outro campo em edição", async () => {
  document.body.innerHTML = '<input id="cfg-cor-elementos"><input id="cfg-opacidade-elementos"><input id="cfg-usuario" value="editando"><span id="cfg-opacidade-valor"></span><div id="cfg-aparencia-preview"></div>';
  const cfg = structuredClone(CONFIG_PADRAO);
  const painel = new Configuracoes(cfg, document.body, {} as DepsConfiguracoes);
  painel.mudouExternamente({ ...cfg, cor_elementos: "#ff00aa", opacidade_elementos: 0.4 });
  expect(cfg.cor_elementos).toBe("#ff00aa");
  expect(document.querySelector<HTMLInputElement>("#cfg-cor-elementos")!.value).toBe("#ff00aa");
  expect(document.querySelector<HTMLInputElement>("#cfg-opacidade-elementos")!.value).toBe("0.4");
  expect(document.querySelector<HTMLInputElement>("#cfg-usuario")!.value).toBe("editando");
  expect(document.querySelector<HTMLElement>("#cfg-aparencia-preview")!.style.opacity).toBe("0.4");
});

it("preserva campos futuros quando carrega para editar e salvar", async () => {
  vi.mocked(invoke).mockResolvedValue({ cor_elementos: "#112233", futuro: { conservar: true } });
  expect(await carregarConfig()).toMatchObject({ cor_elementos: "#112233", futuro: { conservar: true } });
});

it("tela recusa os mesmos valores de aparência que o MCP", async () => {
  vi.mocked(invoke).mockClear();
  await expect(salvarConfig({ ...CONFIG_PADRAO, opacidade_elementos: 0.1 })).rejects.toThrow();
  expect(invoke).not.toHaveBeenCalled();
});

it("aplica a voz principal e reserva sem reiniciar nem alterar credenciais", () => {
  const vivo = { ...CONFIG_PADRAO, gemini_chave: "chave-ficticia" };
  const novo = { ...vivo, voz_provedor: "gemini" as const, gemini_voz: "Puck", voz_reserva_provedor: "gemini" as const, voz_reserva_id: "Kore" };
  expect(aplicarVozAoVivo(vivo, novo)).toBe(true);
  expect(vivo.gemini_voz).toBe("Puck");
  expect(vivo.voz_reserva_id).toBe("Kore");
  expect(vivo.gemini_chave).toBe("chave-ficticia");
  expect(aplicarVozAoVivo(vivo, novo)).toBe(false);
  expect(mudancasQueExigemReinicio(CONFIG_PADRAO, { ...CONFIG_PADRAO, voz_provedor: "gemini" })).not.toContain("voz");
});

it("perfil recarrega mudanças externas e conserva campos futuros no próximo salvamento", async () => {
  let perfil = { ...PERFIL_PADRAO, tom: "calmo", futuro: 3 };
  const raiz = document.createElement("div");
  const aba = new AbaPerfil(raiz, { nome: () => "Aurora", usuario: () => "", variantes: () => [], ler: async () => perfil, gravar: async () => {}, previa: async () => null });
  await aba.montar();
  raiz.querySelector<HTMLTextAreaElement>("#perfil-instrucoes")!.value = "editando";
  perfil = { ...perfil, tom: "direto" };
  await aba.recarregar();
  expect(raiz.querySelector<HTMLInputElement>("#perfil-tom")!.value).toBe("direto");
  expect(aba.lerPerfil()).toMatchObject({ futuro: 3, instrucoes: "editando" });
});
