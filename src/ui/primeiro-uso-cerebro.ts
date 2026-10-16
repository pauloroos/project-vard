/** Etapa 'cerebro' do assistente de primeiro uso (T3).
 *  Permite escolher entre OpenJarvis (padrão) ou cérebro próprio, testar a
 *  conexão com o provedor escolhido e salvar a escolha no estado do assistente.
 *  Arquivo separado para evitar conflitos com a T2b; expõe montarEtapaCerebro()
 *  que será ligada ao fluxo principal quando a T2b mesclar. */

import type { EstadoPrimeiroUso } from "../config/primeiro-uso";
import { atualizarEstadoPrimeiroUso } from "../config/primeiro-uso";

export interface DepsEtapaCerebro {
  /** URL base da ponte/núcleo (ex: http://127.0.0.1:8765). */
  ponteUrl: string;
  /** Estado atual do assistente; usado para pré-preencher escolhas. */
  estadoInicial: EstadoPrimeiroUso;
  /** Chamado quando o usuário salva uma escolha válida. */
  aoSalvar?: (estado: EstadoPrimeiroUso) => void;
}

interface ResultadoTeste {
  ok: boolean;
  detalhe: string;
  primeiro_token_ms: number | null;
}

const CEREBROS = [
  { valor: "openjarvis", rotulo: "OpenJarvis (padrão)" },
  { valor: "proprio", rotulo: "Cérebro próprio (experimental)" },
] as const;

type ValorCerebro = (typeof CEREBROS)[number]["valor"];

function ehValorCerebro(v: unknown): v is ValorCerebro {
  return typeof v === "string" && CEREBROS.some((c) => c.valor === v);
}

/** Cria a UI da etapa 'cerebro' dentro do container informado.
 *  Retorna função de limpeza que remove listeners e elementos. */
export function montarEtapaCerebro(
  container: HTMLElement,
  deps: DepsEtapaCerebro,
): () => void {
  const abortController = new AbortController();
  const signal = abortController.signal;

  let cerebroEscolhido: ValorCerebro = ehValorCerebro(deps.estadoInicial.cerebro_id)
    ? deps.estadoInicial.cerebro_id
    : "openjarvis";

  // Campos do formulário (só aparecem quando cerebroEscolhido === 'proprio')
  let tipoInput: HTMLSelectElement | null = null;
  let urlInput: HTMLInputElement | null = null;
  let modeloInput: HTMLInputElement | null = null;
  let chaveInput: HTMLInputElement | null = null;
  let btnTestar: HTMLButtonElement | null = null;
  let btnSalvar: HTMLButtonElement | null = null;
  let statusEl: HTMLElement | null = null;
  let detalhesEl: HTMLElement | null = null;

  function desenhar() {
    container.innerHTML = "";

    const fieldset = document.createElement("fieldset");
    fieldset.innerHTML = "<legend>Cérebro</legend>";

    const descricao = document.createElement("p");
    descricao.className = "nota";
    descricao.textContent =
      "O cérebro é quem responde às suas perguntas. OpenJarvis usa um serviço externo; cérebro próprio conversa diretamente com um modelo local (LM Studio, llama-server, etc.).";
    fieldset.appendChild(descricao);

    // Radio buttons para escolha do cérebro
    for (const opcao of CEREBROS) {
      const label = document.createElement("label");
      label.className = "marca";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "cerebro-escolha";
      radio.value = opcao.valor;
      radio.checked = cerebroEscolhido === opcao.valor;
      radio.addEventListener(
        "change",
        () => {
          if (radio.checked) {
            cerebroEscolhido = opcao.valor;
            desenhar();
          }
        },
        { signal },
      );
      label.appendChild(radio);
      label.appendChild(document.createTextNode(opcao.rotulo));
      fieldset.appendChild(label);
    }

    // Formulário do cérebro próprio (só quando escolhido)
    if (cerebroEscolhido === "proprio") {
      const formProprio = document.createElement("div");
      formProprio.id = "cerebro-proprio-form";

      // Tipo de provedor
      const lblTipo = document.createElement("label");
      lblTipo.textContent = "Tipo de provedor:";
      tipoInput = document.createElement("select");
      for (const opt of [
        { v: "openai_compat", t: "OpenAI Compatível (LM Studio, llama-server)" },
        { v: "anthropic", t: "Anthropic (Claude)" },
        { v: "google", t: "Google (Gemini)" },
        { v: "openai_nativo", t: "OpenAI Nativo" },
      ]) {
        const option = document.createElement("option");
        option.value = opt.v;
        option.textContent = opt.t;
        tipoInput.appendChild(option);
      }
      lblTipo.appendChild(tipoInput);
      formProprio.appendChild(lblTipo);

      // URL base
      const lblUrl = document.createElement("label");
      lblUrl.textContent = "URL base:";
      urlInput = document.createElement("input");
      urlInput.type = "url";
      urlInput.placeholder = "http://localhost:1234";
      urlInput.required = true;
      lblUrl.appendChild(urlInput);
      formProprio.appendChild(lblUrl);

      // Modelo
      const lblModelo = document.createElement("label");
      lblModelo.textContent = "Modelo:";
      modeloInput = document.createElement("input");
      modeloInput.type = "text";
      modeloInput.placeholder = "nome-do-modelo";
      modeloInput.required = true;
      lblModelo.appendChild(modeloInput);
      formProprio.appendChild(lblModelo);

      // Chave (opcional)
      const lblChave = document.createElement("label");
      lblChave.textContent = "Chave API (opcional):";
      chaveInput = document.createElement("input");
      chaveInput.type = "password";
      chaveInput.autocomplete = "off";
      lblChave.appendChild(chaveInput);
      formProprio.appendChild(lblChave);

      // Botões
      const botoes = document.createElement("div");
      botoes.className = "botoes";

      btnTestar = document.createElement("button");
      btnTestar.type = "button";
      btnTestar.textContent = "Testar conexão";
      btnTestar.addEventListener("click", () => void executarTeste(), { signal });
      botoes.appendChild(btnTestar);

      btnSalvar = document.createElement("button");
      btnSalvar.type = "button";
      btnSalvar.textContent = "Salvar";
      btnSalvar.disabled = true; // Só habilita após teste bem-sucedido
      btnSalvar.addEventListener("click", () => void salvarEscolha(), { signal });
      botoes.appendChild(btnSalvar);

      formProprio.appendChild(botoes);

      // Status e detalhes do teste
      statusEl = document.createElement("p");
      statusEl.className = "status-teste";
      formProprio.appendChild(statusEl);

      detalhesEl = document.createElement("pre");
      detalhesEl.className = "detalhes-teste";
      formProprio.appendChild(detalhesEl);

      fieldset.appendChild(formProprio);
    } else {
      // OpenJarvis: sem configuração extra, salvar direto
      const info = document.createElement("p");
      info.className = "nota";
      info.textContent =
        "OpenJarvis já está configurado. Clique em Salvar para continuar.";
      fieldset.appendChild(info);

      btnSalvar = document.createElement("button");
      btnSalvar.type = "button";
      btnSalvar.textContent = "Salvar";
      btnSalvar.addEventListener("click", () => void salvarEscolha(), { signal });
      fieldset.appendChild(btnSalvar);

      statusEl = document.createElement("p");
      statusEl.className = "status-teste";
      fieldset.appendChild(statusEl);
    }

    container.appendChild(fieldset);
  }

  async function executarTeste(): Promise<void> {
    if (!btnTestar || !statusEl || !detalhesEl) return;
    if (cerebroEscolhido !== "proprio") return;

    const tipo = tipoInput?.value?.trim() || "";
    const baseUrl = urlInput?.value?.trim() || "";
    const modelo = modeloInput?.value?.trim() || "";
    const chave = chaveInput?.value?.trim() || "";

    if (!tipo || !baseUrl || !modelo) {
      statusEl.textContent = "Preencha tipo, URL e modelo antes de testar.";
      statusEl.className = "status-teste erro";
      detalhesEl.textContent = "";
      return;
    }

    btnTestar.disabled = true;
    statusEl.textContent = "Testando...";
    statusEl.className = "status-teste";
    detalhesEl.textContent = "";

    try {
      const resposta = await fetch(`${deps.ponteUrl}/primeiro-uso/cerebro/testar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tipo, base_url: baseUrl, modelo, chave }),
        signal,
      });

      if (!resposta.ok) {
        const texto = await resposta.text().catch(() => "");
        throw new Error(`HTTP ${resposta.status}: ${texto.slice(0, 200)}`);
      }

      const resultado = (await resposta.json()) as ResultadoTeste;

      if (resultado.ok) {
        statusEl.textContent = `Conexão OK (${resultado.primeiro_token_ms ?? "?"} ms até primeiro token)`;
        statusEl.className = "status-teste sucesso";
        detalhesEl.textContent = resultado.detalhe;
        if (btnSalvar) btnSalvar.disabled = false;
      } else {
        statusEl.textContent = `Falha: ${resultado.detalhe}`;
        statusEl.className = "status-teste erro";
        detalhesEl.textContent = "";
        if (btnSalvar) btnSalvar.disabled = true;
      }
    } catch (erro) {
      statusEl.textContent = `Erro ao testar: ${erro instanceof Error ? erro.message : String(erro)}`;
      statusEl.className = "status-teste erro";
      detalhesEl.textContent = "";
      if (btnSalvar) btnSalvar.disabled = true;
    } finally {
      btnTestar.disabled = false;
    }
  }

  async function salvarEscolha(): Promise<void> {
    if (!btnSalvar || !statusEl) return;

    btnSalvar.disabled = true;
    statusEl.textContent = "Salvando...";
    statusEl.className = "status-teste";

    const patch: Partial<EstadoPrimeiroUso> = {
      cerebro_id: cerebroEscolhido,
      etapa: "voz", // Avança para próxima etapa
    };

    const novoEstado = await atualizarEstadoPrimeiroUso(deps.ponteUrl, patch);

    if (novoEstado) {
      statusEl.textContent = "Escolha salva.";
      statusEl.className = "status-teste sucesso";
      deps.aoSalvar?.(novoEstado);
    } else {
      statusEl.textContent = "Erro ao salvar. Tente novamente.";
      statusEl.className = "status-teste erro";
      btnSalvar.disabled = false;
    }
  }

  desenhar();

  // Função de limpeza
  return () => {
    abortController.abort();
    container.innerHTML = "";
  };
}