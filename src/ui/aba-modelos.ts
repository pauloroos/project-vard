import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";

/** "1,8 s". */
export function formatarSegundos(ms: number): string { return `${(ms / 1000).toFixed(1).replace(".", ",")} s`; }

/** Uma pergunta curta e o tempo até a resposta. */
export async function medirModelo(conector: Pick<OpenJarvis, "perguntar">): Promise<{ ms: number; resposta: string }> {
  const t0 = performance.now();
  const resposta = await conector.perguntar([{ role: "user", content: "Responda apenas: ok." }]);
  return { ms: performance.now() - t0, resposta };
}

export interface DepsAbaModelos {
  /** Cliente no endereço salvo, já com o modelo pedido ("" = automático). */
  criarOj: (modelo: string) => OpenJarvis;
  statusPonte: () => Promise<StatusPonte | null>;
}

/** Aba Modelos: o que o conector expõe, a reserva informada pela ponte e o teste de tempo. A escolha fica em `escolhido`. */
export class AbaModelos {
  escolhido: string;

  constructor(private raiz: HTMLElement, modelo: string, private deps: DepsAbaModelos) { this.escolhido = modelo; }

  async carregar() {
    this.raiz.innerHTML = `
      <p class="nota">O Vard só escolhe entre os modelos que o OpenJarvis expõe. Trocar de provedor (OmniRouter, assinaturas, LM Studio) é configuração do OpenJarvis, não do Vard.</p>
      <fieldset><legend>Modelo principal</legend><div id="mod-lista">Carregando...</div></fieldset>
      <fieldset><legend>Reserva</legend><div id="mod-reserva">Consultando a ponte...</div></fieldset>
      <button id="mod-testar" type="button">Testar</button> <span id="mod-tempo"></span>`;
    this.raiz.querySelector("#mod-testar")!.addEventListener("click", () => { void this.testar(); });
    const lista = this.raiz.querySelector<HTMLElement>("#mod-lista")!;
    try { this.desenharLista(lista, await this.deps.criarOj("").modelos()); }
    catch (erro) { lista.textContent = `O OpenJarvis não respondeu à lista de modelos: ${String(erro)}`; }
    const st = await this.deps.statusPonte();
    this.raiz.querySelector("#mod-reserva")!.textContent = st === null
      ? "Ponte fora ou desligada: sem informação de reserva."
      : st.reserva ? `Se o principal falhar, o OpenJarvis usa ${st.reserva}.` : "A ponte não informa um modelo de reserva.";
  }

  private desenharLista(lista: HTMLElement, ids: string[]) {
    const opcoes: [string, string][] = [["", `Automático (o primeiro: ${ids[0] ?? "nenhum"})`], ...ids.map((id): [string, string] => [id, id])];
    if (this.escolhido && !ids.includes(this.escolhido)) opcoes.push([this.escolhido, `${this.escolhido} (não está mais no OpenJarvis; o Vard usa o primeiro)`]);
    lista.innerHTML = "";
    for (const [valor, rotulo] of opcoes) {
      const l = document.createElement("label");
      l.className = "marca";
      const r = document.createElement("input");
      r.type = "radio"; r.name = "modelo"; r.value = valor; r.checked = valor === this.escolhido;
      r.addEventListener("change", () => { if (r.checked) this.escolhido = valor; });
      l.append(r, document.createTextNode(` ${rotulo}`)); // texto, não HTML: ids vêm do servidor
      lista.append(l);
    }
  }

  private async testar() {
    const saida = this.raiz.querySelector<HTMLElement>("#mod-tempo")!;
    saida.textContent = "Perguntando...";
    try {
      const { ms, resposta } = await medirModelo(this.deps.criarOj(this.escolhido));
      saida.textContent = `${formatarSegundos(ms)}: "${resposta.slice(0, 80)}"`;
    } catch (erro) { saida.textContent = `Falhou: ${String(erro)}`; }
  }
}
