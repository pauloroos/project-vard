/** Assistente de primeiro uso: 7 etapas retomáveis, IDs DOM estáveis e progresso
 * separado da config ativa. Abre sozinho só na primeira vez de uma instalação nova;
 * botão "Configurar primeiro uso" nas Configurações reabre sem apagar escolhas. */
import type { EstadoPrimeiroUso } from "../config/primeiro-uso";
import { atualizarEstadoPrimeiroUso, lerEstadoPrimeiroUso, reabrirPrimeiroUso } from "../config/primeiro-uso";
import { montarEtapaAudio, type DepsEtapaAudio, type ResultadoEtapaAudio } from "./primeiro-uso-audio";

const ETAPAS = ["importar", "detectar", "nome", "cerebro", "voz", "audio", "resumo"] as const;
type Etapa = (typeof ETAPAS)[number];

const TITULOS_ETAPA: Record<Etapa, string> = {
  importar: "Importar ou começar",
  detectar: "Detectar PC",
  nome: "Nome de chamada",
  cerebro: "Cérebro",
  voz: "Voz e dispositivos",
  audio: "Teste de áudio",
  resumo: "Resumo",
};

export type { DepsEtapaAudio };

export interface DepsPrimeiroUso {
  ponteUrl: string;
  /** Salva o nome de chamada e variantes na config ativa (acessor existente). */
  salvarNome?: (nome: string, variantes: string[]) => Promise<void>;
  /** Recursos da janela hospedeira; a restauração da escuta permanece com o widget. */
  audio?: DepsEtapaAudio;
}

function criarContainer(): HTMLDivElement {
  const div = document.createElement("div");
  div.id = "primeiro-uso-etapa";
  div.className = "primeiro-uso";
  return div;
}

function renderizarEtapa(
  container: HTMLElement,
  etapa: Etapa,
  estado: EstadoPrimeiroUso,
  deps: DepsPrimeiroUso,
  onAtualizado: (novo: EstadoPrimeiroUso) => void,
): () => void {
  let limparConteudo = () => {};
  let pararTeste = () => {};
  let salvarAudio: (() => Promise<void>) | undefined;
  container.innerHTML = "";
  const titulo = document.createElement("h2");
  titulo.textContent = TITULOS_ETAPA[etapa];
  container.appendChild(titulo);

  const corpo = document.createElement("div");
  corpo.id = `primeiro-uso-conteudo-${etapa}`;
  container.appendChild(corpo);

  if (etapa === "nome") {
    const input = document.createElement("input");
    input.type = "text";
    input.id = "primeiro-uso-nome-input";
    input.placeholder = "Ex.: Aurora";
    input.value = estado.nome_chamada || "";
    corpo.appendChild(input);
  } else if (etapa === "resumo") {
    const resumoDiv = document.createElement("div");
    resumoDiv.id = "primeiro-uso-resumo";
    resumoDiv.textContent = estado.concluido
      ? estado.pendencias.length ? `Configuração concluída com pendências: ${estado.pendencias.join(", ")}` : "Tudo pronto para conversar."
      : estado.pendencias.length ? `Revise suas escolhas. Pendências: ${estado.pendencias.join(", ")}` : "Revise suas escolhas e conclua.";
    corpo.appendChild(resumoDiv);
  } else if ((etapa === "audio" || etapa === "voz") && deps.audio) {
    const containerAudio = document.createElement("div");
    containerAudio.id = `primeiro-uso-container-${etapa}`;
    corpo.appendChild(containerAudio);
    const salvarResultado = async (r: ResultadoEtapaAudio) => {
      await deps.audio!.salvar(r);
      const pendencias = estado.pendencias.filter((p) => p !== "microfone_nao_testado" && p !== "voz_nao_testada");
      if (!r.microfone_testado) pendencias.push("microfone_nao_testado");
      if (!r.voz_ouvida) pendencias.push("voz_nao_testada");
      const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, {
        microfone_id: r.microfone_id, saida_id: r.saida_id, voz_id: r.voz_id, pendencias,
      });
      if (!novo) throw new Error("Não consegui salvar o teste de áudio");
      Object.assign(estado, novo);
    };
    const config = { ...deps.audio.config,
      microfone_id: estado.microfone_id ?? deps.audio.config.microfone_id,
      saida_id: estado.saida_id ?? deps.audio.config.saida_id };
    const campoVoz = config.voz_provedor === "propria" ? "voz_propria" : config.voz_provedor === "gemini" ? "gemini_voz" : config.voz_provedor === "elevenlabs" ? "elevenlabs_voz" : "voz";
    if (estado.voz_id !== undefined) config[campoVoz] = estado.voz_id;
    const audio = montarEtapaAudio(containerAudio, { ...deps.audio, config, salvar: salvarResultado,
      resultadoInicial: { microfone_testado: estado.microfone_id !== undefined && !estado.pendencias.includes("microfone_nao_testado"),
        voz_ouvida: estado.saida_id !== undefined && !estado.pendencias.includes("voz_nao_testada") } });
    limparConteudo = audio.sair;
    pararTeste = audio.cancelar;
    salvarAudio = () => salvarResultado(audio.resultado());
  } else if (etapa === "audio" || etapa === "cerebro") {
    // Ponto de montagem para T3 (cerebro) e T4 (audio): container DOM próprio
    // sem conteúdo implementado aqui; os módulos montarEtapaCerebro/montarEtapaAudio
    // serão ligados por rebase após esta tarefa mesclar na main.
    const containerEtapa = document.createElement("div");
    containerEtapa.id = `primeiro-uso-container-${etapa}`;
    containerEtapa.className = "primeiro-uso-montagem";
    corpo.appendChild(containerEtapa);
  } else {
    const info = document.createElement("p");
    info.textContent = `Etapa ${etapa}: configure ou pule.`;
    corpo.appendChild(info);
  }

  const botoes = document.createElement("div");
  botoes.className = "primeiro-uso-botoes";

  const idxAtual = ETAPAS.indexOf(etapa);
  const prepararNavegacao = async () => {
    pararTeste();
    try { await salvarAudio?.(); return true; }
    catch {
      const aviso = document.createElement("p"); aviso.role = "alert";
      aviso.textContent = "Não consegui salvar o teste de áudio. Tente novamente.";
      corpo.appendChild(aviso); return false;
    }
  };
  if (idxAtual > 0) {
    const voltar = document.createElement("button");
    voltar.id = "primeiro-uso-voltar";
    voltar.textContent = "Voltar";
    voltar.onclick = async () => {
      if (!(await prepararNavegacao())) return;
      const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, { etapa: ETAPAS[idxAtual - 1] });
      if (novo) onAtualizado(novo);
    };
    botoes.appendChild(voltar);
  }

  const proximo = document.createElement("button");
  proximo.id = "primeiro-uso-proximo";
  proximo.textContent = etapa === "resumo" ? "Concluir" : "Próximo";
  proximo.onclick = async () => {
    if (!(await prepararNavegacao())) return;
    if (etapa === "nome") {
      const inputEl = corpo.querySelector<HTMLInputElement>("#primeiro-uso-nome-input");
      const nome = (inputEl?.value || "").trim();
      if (!nome) {
        inputEl?.classList.add("erro");
        return;
      }
      await deps.salvarNome?.(nome, [nome.toLowerCase()]);
      const proximaEtapa = idxAtual < ETAPAS.length - 1 ? ETAPAS[idxAtual + 1] : etapa;
      const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, {
        etapa: proximaEtapa,
        nome_chamada: nome,
      });
      if (novo) onAtualizado(novo);
      return;
    }
    if (etapa === "resumo") {
      const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, { concluido: true });
      if (novo) onAtualizado(novo);
      return;
    }
    const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, {
      etapa: ETAPAS[idxAtual + 1],
    });
    if (novo) onAtualizado(novo);
  };
  botoes.appendChild(proximo);
  container.appendChild(botoes);
  return limparConteudo;
}

/** Monta o assistente no elemento raiz dado; lê o estado atual e renderiza a etapa correta.
 * Devolve uma função de limpeza que remove o container. */
export async function montarAssistentePrimeiroUso(
  raiz: HTMLElement,
  deps: DepsPrimeiroUso,
): Promise<(() => void) | null> {
  const estado = await lerEstadoPrimeiroUso(deps.ponteUrl);
  if (!estado || estado.concluido) return null;

  const container = criarContainer();
  raiz.appendChild(container);

  let estadoAtual = estado;
  let limparEtapa = () => {};
  const render = () => {
    limparEtapa();
    const etapa = (ETAPAS.includes(estadoAtual.etapa as Etapa) ? estadoAtual.etapa : "importar") as Etapa;
    limparEtapa = renderizarEtapa(container, etapa, estadoAtual, deps, (novo) => {
      estadoAtual = novo;
      render();
    });
  };
  render();

  return () => {
    limparEtapa();
    container.remove();
  };
}

/** Reabre o assistente (botão nas Configurações) sem apagar escolhas salvas. */
export async function reabrirAssistentePrimeiroUso(
  raiz: HTMLElement,
  deps: DepsPrimeiroUso,
): Promise<(() => void) | null> {
  await reabrirPrimeiroUso(deps.ponteUrl);
  return montarAssistentePrimeiroUso(raiz, deps);
}
