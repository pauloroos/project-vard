import { CentralAvisos, rotuloDoAviso, type PonteAvisos } from "../avisos/central";
import type { Aviso } from "../conectores/ponte/cliente";
import { formatarHoraAviso } from "../avisos/formata-hora";

/** "10:32:05" vira "10:32"; hora malformada fica como está. Mantida para compatibilidade. */
export function horaCurta(hora: string): string {
  const m = /^(\d{2}:\d{2})/.exec(hora);
  return m ? m[1] : hora;
}

/** Aba Avisos: lista da ponte, não lidos em destaque, resultado das tarefas em texto puro e "marcar tudo como lido". */
export class AbaAvisos {
  private central: CentralAvisos;
  private lista!: HTMLElement;
  private msg!: HTMLElement;
  private bloco!: HTMLElement;
  private encerrar: (() => void) | null = null;
  private ativa = false;
  private foraDoAr = false;

  constructor(private raiz: HTMLElement, private deps: PonteAvisos) {
    this.central = new CentralAvisos(deps);
    this.central.aoMudar = () => this.desenhar();
  }

  montar() {
    const topo = document.createElement("div"); topo.className = "avi-topo";
    const botao = document.createElement("button");
    botao.type = "button"; botao.textContent = "Marcar tudo como lido";
    botao.addEventListener("click", () => { void this.marcarTudo(); });
    // T14: opção para a Aurora chamar quando algo ficar pronto
    const chkChamar = document.createElement("label"); chkChamar.className = "avi-chamar";
    const inputChamar = document.createElement("input"); inputChamar.type = "checkbox";
    inputChamar.checked = true; // padrão ligado
    inputChamar.id = "avi-chamar-quando-pronto";
    chkChamar.append(inputChamar, document.createTextNode(" Me chamar quando algo ficar pronto"));
    topo.append(botao, chkChamar);
    this.lista = document.createElement("div"); this.lista.id = "avi-lista";
    this.bloco = document.createElement("div"); this.bloco.id = "avi-resultado"; this.bloco.hidden = true;
    this.msg = document.createElement("div"); this.msg.id = "avi-msg";
    this.raiz.append(topo, this.lista, this.bloco, this.msg);
    this.desenhar();
  }

  ativar() {
    this.ativa = true;
    void this.carregarAtiva();
    this.encerrar?.(); // reativação não pode assinar duas vezes
    this.encerrar = this.deps.eventos((tipo, dados) => {
      if (tipo !== "oficina" && tipo !== "reuniao") return;
      this.central.aplicarEvento(tipo, dados);
    });
  }

  desativar() { this.ativa = false; this.encerrar?.(); this.encerrar = null; }

  /** Recarrega pela ponte e pinta (também chamado nos testes para esperar a primeira carga). */
  async carregar() {
    const ok = await this.central.carregar();
    this.foraDoAr = !ok;
    this.desenhar();
  }

  /** A carga da ativação não pode repintar uma aba que já fechou no meio da espera. */
  private async carregarAtiva() {
    const ok = await this.central.carregar();
    if (!this.ativa) return;
    this.foraDoAr = !ok;
    this.desenhar();
  }

  private async marcarTudo() { await this.central.marcarLidos(); }

  private async verResultado(n: number) {
    this.bloco.hidden = false;
    this.bloco.textContent = "Consultando...";
    const r = await this.deps.resultadoTarefa(n);
    this.bloco.textContent = r ? r.texto : "A ponte não respondeu.";
  }

  private desenhar() {
    this.lista.innerHTML = "";
    if (this.foraDoAr) { this.msg.textContent = "Ponte fora do ar"; return; }
    this.msg.textContent = this.central.avisos.length ? "" : "Nenhum aviso";
    for (const a of this.central.avisos) this.lista.append(this.linha(a));
  }

  private linha(a: Aviso): HTMLElement {
    const div = document.createElement("div");
    div.className = `aviso-linha${a.lido ? "" : " novo"}`;
    const hora = document.createElement("span"); hora.className = "hora"; hora.textContent = formatarHoraAviso(a.hora) || horaCurta(a.hora);
    const tipo = document.createElement("span"); tipo.className = "tipo"; tipo.textContent = rotuloDoAviso(a);
    const resumo = document.createElement("span"); resumo.className = "resumo"; resumo.textContent = a.resumo;
    div.append(hora, tipo, resumo);
    if (a.tipo === "tarefa" && a.n !== undefined) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = "ver resultado";
      b.addEventListener("click", () => { void this.verResultado(a.n!); });
      div.append(b);
    }
    return div;
  }
}
