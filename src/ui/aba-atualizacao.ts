import { invoke } from "@tauri-apps/api/core";
import { interpretarRelease, type Release } from "../atualizacao/release";

export interface DepsAbaAtualizacao {
  url: string;
  /** GET do endereço pelo Rust (allowlist de hosts); devolve o corpo em texto. */
  buscar: (url: string) => Promise<string>;
  instalar: (setup: NonNullable<Release["setup"]>) => Promise<void>;
  versao: () => Promise<string>;
}

const dataBr = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}/${d.getUTCFullYear()}`;
};

/** Aba Atualização: consulta a release só por ação do usuário (botão, ou a caixa "ao abrir" tratada pelo painel). Notas por textContent, nunca HTML. */
export class AbaAtualizacao {
  private instalada = "";
  private resultado!: HTMLElement;
  private notas!: HTMLElement;
  private botaoInstalar!: HTMLButtonElement;
  private botaoVerificar!: HTMLButtonElement;
  private linhaInstalada!: HTMLElement;
  private consultou = false;
  private ocupado = false;

  constructor(private raiz: HTMLElement, private deps: DepsAbaAtualizacao) {}

  montar() {
    this.raiz.replaceChildren();
    this.linhaInstalada = document.createElement("p");
    this.linhaInstalada.textContent = "Instalada: ...";
    this.botaoVerificar = document.createElement("button");
    this.botaoVerificar.type = "button"; this.botaoVerificar.textContent = "Verificar agora";
    this.botaoVerificar.addEventListener("click", () => { void this.verificar(); });
    this.resultado = document.createElement("div"); this.resultado.id = "atu-resultado"; this.resultado.setAttribute("role", "status");
    this.notas = document.createElement("pre"); this.notas.id = "atu-notas"; this.notas.hidden = true;
    this.botaoInstalar = document.createElement("button");
    this.botaoInstalar.type = "button"; this.botaoInstalar.hidden = true;
    this.raiz.append(this.linhaInstalada, this.botaoVerificar, this.resultado, this.notas, this.botaoInstalar);
    void this.deps.versao().then((v) => { this.instalada = v; this.linhaInstalada.textContent = `Instalada: ${v}`; }).catch(() => { this.linhaInstalada.textContent = "Instalada: desconhecida"; });
  }

  /** Chamado ao abrir a aba com "Verificar ao abrir o painel" marcada: consulta uma vez por abertura do painel. */
  aoAbrir() {
    if (this.consultou) return;
    void this.verificar();
  }

  async verificar() {
    if (this.ocupado) return;
    this.ocupado = true; this.consultou = true;
    this.notas.hidden = true; this.botaoInstalar.hidden = true; this.botaoVerificar.disabled = true;
    this.resultado.replaceChildren(); this.resultado.textContent = "Consultando...";
    try {
      if (!this.instalada) { try { this.instalada = await this.deps.versao(); } catch { this.instalada = ""; } }
      if (!this.instalada) { this.resultado.textContent = "Não consegui ler a versão instalada."; return; }
      const rel = interpretarRelease(JSON.parse(await this.deps.buscar(this.deps.url)), this.instalada);
      if (!rel) { this.resultado.textContent = "Resposta inesperada do GitHub."; return; }
      this.mostrar(rel);
    } catch (e) {
      this.resultado.textContent = `Não consegui consultar: ${String(e)}`;
    } finally { this.ocupado = false; this.botaoVerificar.disabled = false; }
  }

  private mostrar(rel: Release) {
    if (!rel.maisNova) { this.resultado.textContent = "Você está na versão mais nova."; return; }
    this.resultado.textContent = `Mais nova: ${rel.versao}${rel.publicadaEm ? `, publicada em ${dataBr(rel.publicadaEm)}` : ""}`;
    this.notas.textContent = rel.notas; this.notas.hidden = rel.notas === "";
    if (rel.setup) {
      const setup = rel.setup;
      this.botaoInstalar.textContent = `Baixar e instalar (${(setup.bytes / 1048576).toFixed(1)} MB)`;
      this.botaoInstalar.disabled = false; this.botaoInstalar.hidden = false;
      this.botaoInstalar.onclick = () => { void this.instalar(setup); };
    } else {
      const p = document.createElement("p");
      p.append("Baixe pela página da release: ");
      const a = document.createElement("a");
      a.textContent = rel.url; a.href = rel.url;
      // O painel não tem permissão do opener: abre pelo comando abrir_url (só http/https).
      a.addEventListener("click", (ev) => { ev.preventDefault(); void invoke("abrir_url", { url: rel.url }).catch(() => {}); });
      p.append(a);
      this.resultado.append(p);
    }
  }

  private async instalar(setup: NonNullable<Release["setup"]>) {
    this.botaoInstalar.disabled = true;
    this.resultado.textContent = "Baixando...";
    try { await this.deps.instalar(setup); }
    catch (e) { this.resultado.textContent = `Não consegui instalar: ${String(e)}`; this.botaoInstalar.disabled = false; }
  }
}
