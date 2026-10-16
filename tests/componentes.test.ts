// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { abrirModal, desenharCards, campoModal, type Card } from "../src/ui/componentes";

afterEach(() => { document.body.innerHTML = ""; });

describe("abrirModal", () => {
  it("abre com título, foca o primeiro campo e fecha no Esc", () => {
    const corpo = document.createElement("div");
    const input = document.createElement("input");
    corpo.append(campoModal("Nome", input));
    const aoFechar = vi.fn();
    abrirModal({ titulo: "Novo provedor", corpo, aoFechar });
    expect(document.querySelector(".modal-titulo")!.textContent).toBe("Novo provedor");
    expect(document.activeElement).toBe(input);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(document.querySelector(".modal-fundo")).toBeNull();
    expect(aoFechar).toHaveBeenCalledOnce();
  });

  it("ação que devolve false mantém o modal aberto; a outra fecha", async () => {
    let tentativas = 0;
    abrirModal({
      titulo: "X", corpo: document.createElement("div"),
      acoes: [{ rotulo: "Salvar", primaria: true, aoClicar: () => (++tentativas > 1 ? undefined : false) }],
    });
    const salvar = document.querySelector<HTMLButtonElement>(".modal-acoes button.primaria")!;
    salvar.click();
    await Promise.resolve(); await Promise.resolve();
    expect(document.querySelector(".modal")).not.toBeNull();
    salvar.click();
    await Promise.resolve(); await Promise.resolve();
    expect(document.querySelector(".modal")).toBeNull();
  });

  it("erro na ação aparece no rodapé sem fechar", async () => {
    abrirModal({ titulo: "X", corpo: document.createElement("div"),
      acoes: [{ rotulo: "Testar", aoClicar: () => { throw new Error("endpoint fora do ar"); } }] });
    document.querySelector<HTMLButtonElement>(".modal-acoes button")!.click();
    await Promise.resolve(); await Promise.resolve();
    expect(document.querySelector(".modal-aviso")!.textContent).toBe("endpoint fora do ar");
    expect(document.querySelector(".modal-aviso")!.classList.contains("ruim")).toBe(true);
  });
});

describe("desenharCards", () => {
  const card = (i: number): Card => ({ id: `p${i}`, titulo: `Provedor ${i}`, etiqueta: "lmstudio",
    selos: i === 0 ? [{ texto: "Responde agora", tom: "ativo" }] : [], detalhes: [`http://127.0.0.1:${1230 + i}`],
    fichas: [`modelo-${i}`], acoes: [{ rotulo: "Editar", aoClicar: () => {} }] });

  it("lista vazia mostra a mensagem e o botão de adicionar", () => {
    const alvo = document.createElement("div");
    const adicionar = vi.fn();
    desenharCards(alvo, [], { vazio: "Nenhum provedor cadastrado.", adicionar: { rotulo: "Adicionar provedor", aoClicar: adicionar } });
    expect(alvo.querySelector(".cards-vazio p")!.textContent).toBe("Nenhum provedor cadastrado.");
    alvo.querySelector<HTMLButtonElement>(".cards-vazio button")!.click();
    expect(adicionar).toHaveBeenCalledOnce();
  });

  it("desenha um card por item com selo, detalhe e fichas", () => {
    const alvo = document.createElement("div");
    desenharCards(alvo, [card(0), card(1)], { vazio: "-" });
    expect(alvo.querySelectorAll(".card")).toHaveLength(2);
    expect(alvo.querySelector(".selo-ativo")!.textContent).toBe("Responde agora");
    expect(alvo.querySelector(".card-detalhe")!.textContent).toBe("http://127.0.0.1:1230");
    expect(alvo.querySelector(".cards-busca")).toBeNull();
  });

  it("com muitos itens mostra busca que filtra por título e fichas", () => {
    const alvo = document.createElement("div");
    desenharCards(alvo, Array.from({ length: 8 }, (_, i) => card(i)), { vazio: "-" });
    const busca = alvo.querySelector<HTMLInputElement>(".cards-busca")!;
    busca.value = "modelo-3";
    busca.dispatchEvent(new Event("input"));
    const visiveis = [...alvo.querySelectorAll<HTMLElement>(".card")].filter((c) => !c.hidden);
    expect(visiveis.map((c) => c.dataset.id)).toEqual(["p3"]);
  });
});
