import type { OpenJarvis } from "../conectores/openjarvis/cliente";
import type { StatusPonte } from "../conectores/ponte/cliente";
import { CEREBROS, ehCerebro, type Cerebro } from "../config/cerebro";

/** "1,8 s". */
export function formatarSegundos(ms: number): string { return `${(ms / 1000).toFixed(1).replace(".", ",")} s`; }

/** Uma pergunta curta e o tempo até a resposta. */
export async function medirModelo(conector: Pick<OpenJarvis, "perguntar">): Promise<{ ms: number; resposta: string }> {
  const t0 = performance.now();
  const resposta = await conector.perguntar([{ role: "user", content: "Responda apenas: ok." }]);
  return { ms: performance.now() - t0, resposta };
}

/** Separa os modelos por origem: os que o LM Studio tem (informados pela ponte) e o resto (nuvem). Sem a lista da ponte, um grupo só. */
export function agruparModelos(ids: string[], locais: string[] | null): { titulo: string; ids: string[] }[] {
  if (locais === null) return [{ titulo: "Todos", ids }];
  const l = ids.filter((id) => locais.includes(id));
  const n = ids.filter((id) => !locais.includes(id));
  return [{ titulo: "LM Studio (local)", ids: l }, { titulo: "OmniRouter (nuvem)", ids: n }].filter((g) => g.ids.length > 0);
}

export interface DepsAbaModelos {
  /** Cliente no endereço salvo, já com o modelo pedido ("" = automático). */
  criarOj: (modelo: string) => OpenJarvis;
  statusPonte: () => Promise<StatusPonte | null>;
  /** Cérebro ativo no momento da abertura da aba. */
  cerebroInicial?: Cerebro;
  /** Chamado quando o usuário troca o cérebro na aba. */
  aoMudarCerebro?: (cerebro: Cerebro) => void;
}

const ROTULOS_CEREBRO: Record<Cerebro, string> = {
  openjarvis: "Pelo OpenJarvis (servidor atual)",
  proprio: "Direto num modelo (LM Studio, Claude, Antigravity)",
};

/** Aba Modelos: o que o conector expõe, a reserva informada pela ponte e o teste de tempo. A escolha fica em `escolhido`. */
export class AbaModelos {
  escolhido: string;
  cerebro: Cerebro;

  constructor(private raiz: HTMLElement, modelo: string, private deps: DepsAbaModelos) {
    this.escolhido = modelo;
    this.cerebro = ehCerebro(deps.cerebroInicial) ? deps.cerebroInicial : "openjarvis";
  }

  async carregar() {
    this.raiz.innerHTML = `
      <fieldset id="mod-cerebro"><legend>Cérebro</legend></fieldset>
      <p class="nota">O Vard só escolhe entre os modelos que o OpenJarvis expõe. Trocar de provedor (OmniRouter, assinaturas, LM Studio) é configuração do OpenJarvis, não do Vard.</p>
      <p class="nota aviso-gpu">Atenção: escolher um modelo diferente do automático, ou clicar em Testar nele, pode fazer o servidor de LLM (por exemplo o LM Studio) carregar um segundo modelo na GPU e consumir memória.</p>
      <fieldset><legend>Modelo principal</legend><div id="mod-lista">Carregando...</div></fieldset>
      <fieldset><legend>Reserva</legend><div id="mod-reserva">Consultando a ponte...</div></fieldset>
      <button id="mod-testar" type="button">Testar</button> <span id="mod-tempo"></span>`;
    this.desenharCerebro();
    this.raiz.querySelector("#mod-testar")!.addEventListener("click", () => { void this.testar(); });
    const lista = this.raiz.querySelector<HTMLElement>("#mod-lista")!;
    const [ids, st] = await Promise.all([
      this.deps.criarOj("").modelos().catch((erro: unknown) => erro as Error),
      this.deps.statusPonte(),
    ]);
    if (Array.isArray(ids)) this.desenharLista(lista, ids, st?.modelos_lmstudio ?? null);
    else lista.textContent = `O OpenJarvis não respondeu à lista de modelos: ${String(ids)}`;
    this.raiz.querySelector("#mod-reserva")!.textContent = st === null
      ? "Ponte fora ou desligada: sem informação de reserva."
      : st.reserva ? `Se o principal falhar, o OpenJarvis usa ${st.reserva}.` : "A ponte não informa um modelo de reserva.";
  }

  private desenharCerebro() {
    const campo = this.raiz.querySelector<HTMLElement>("#mod-cerebro");
    if (!campo) return;
    campo.innerHTML = "";
    for (const valor of CEREBROS) {
      const l = document.createElement("label");
      l.className = "marca";
      const r = document.createElement("input");
      r.type = "radio";
      r.name = "cerebro";
      r.value = valor;
      r.checked = valor === this.cerebro;
      r.addEventListener("change", () => {
        if (r.checked && this.cerebro !== valor) {
          this.cerebro = valor;
          this.deps.aoMudarCerebro?.(valor);
        }
      });
      l.append(r, document.createTextNode(` ${ROTULOS_CEREBRO[valor]}`));
      campo.append(l);
    }
  }

  private desenharLista(lista: HTMLElement, ids: string[], locais: string[] | null) {
    const rotulo = (valor: string, texto: string) => {
      const l = document.createElement("label");
      l.className = "marca";
      const r = document.createElement("input");
      r.type = "radio"; r.name = "modelo"; r.value = valor; r.checked = valor === this.escolhido;
      r.addEventListener("change", () => { if (r.checked) this.escolhido = valor; });
      l.append(r, document.createTextNode(` ${texto}`)); // texto, não HTML: ids vêm do servidor
      return l;
    };
    lista.innerHTML = "";
    lista.append(rotulo("", `Automático (o primeiro: ${ids[0] ?? "nenhum"})`));
    for (const g of agruparModelos(ids, locais)) {
      const f = document.createElement("fieldset");
      f.className = "grupo";
      const lg = document.createElement("legend");
      lg.textContent = g.titulo;
      f.append(lg, ...g.ids.map((id) => rotulo(id, id)));
      lista.append(f);
    }
    if (this.escolhido && !ids.includes(this.escolhido)) lista.append(rotulo(this.escolhido, `${this.escolhido} (não está mais no OpenJarvis; o Vard usa o primeiro)`));
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
