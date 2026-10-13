import { combinacaoDoEvento, exibirAtalho } from "../config/atalhos";

/**
 * Campo de captura: mostra a combinação; clicado, espera a próxima com Ctrl, Alt ou Win mais uma tecla.
 * Esc ou sair do campo cancelam. Uma combinação que já é atalho global não chega aqui (o Windows a entrega ao dono).
 */
export function campoAtalho(valor: string, aoMudar: (nova: string) => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "atalho";
  let atual = valor;
  const mostrar = () => { b.textContent = exibirAtalho(atual); };
  const parar = () => { window.removeEventListener("keydown", ouvir, true); b.classList.remove("ouvindo"); mostrar(); };
  const ouvir = (ev: KeyboardEvent) => {
    ev.preventDefault(); ev.stopImmediatePropagation();
    if (ev.key === "Escape") { parar(); return; }
    const combinacao = combinacaoDoEvento(ev);
    if (!combinacao) return; // só modificadores até agora, ou tecla fora da lista
    atual = combinacao; parar(); aoMudar(combinacao);
  };
  b.addEventListener("click", () => {
    if (b.classList.contains("ouvindo")) return;
    b.classList.add("ouvindo"); b.textContent = "pressione a combinação...";
    window.addEventListener("keydown", ouvir, true);
  });
  b.addEventListener("blur", () => { if (b.classList.contains("ouvindo")) parar(); });
  mostrar();
  return b;
}
