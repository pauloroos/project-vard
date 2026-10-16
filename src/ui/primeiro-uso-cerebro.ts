/** Etapa de cérebro: seleção manual pelos Painéis, testes sem histórico e pular retomável. */
import { atualizarEstadoPrimeiroUso, type EstadoPrimeiroUso } from "../config/primeiro-uso";
import { lerPaineis, gravarPaineis, type PaineisConfig, type Provedor } from "../config/paineis";
import { atualizarConfig } from "../config/config";
import { cofreLer } from "../config/segredos";

export interface DepsEtapaCerebro {
  ponteUrl: string;
  estadoInicial: EstadoPrimeiroUso;
  aoSalvar?: (estado: EstadoPrimeiroUso) => void;
  lerProvedores?: () => Promise<PaineisConfig>;
  gravarProvedores?: (config: PaineisConfig) => Promise<void>;
  salvarCerebro?: (cerebro: "openjarvis" | "proprio") => Promise<void>;
  lerCredencial?: (tipo: string, id: string) => Promise<string | null>;
}

interface ResultadoTeste { ok: boolean; detalhe: string; primeiro_token_ms?: number | null }

export function montarEtapaCerebro(container: HTMLElement, deps: DepsEtapaCerebro): () => void {
  const ac = new AbortController();
  const signal = ac.signal;
  let geracao = 0;
  let operacao = 0;
  let ocupado = false;
  let validado = "";
  let editado = false;
  let cfg: PaineisConfig | undefined;
  let escolhido = deps.estadoInicial.cerebro_id === "proprio" ? "proprio" : "openjarvis";
  let provedorId = "";
  let tipo = "lmstudio", url = "", modelo = "", ref = "";
  let status: HTMLElement;
  let salvar: HTMLButtonElement;
  let testar: HTMLButtonElement | undefined;
  const assinatura = () => JSON.stringify([escolhido, provedorId, tipo, url, modelo, ref]);
  const pendencias = (pendente: boolean) => [...deps.estadoInicial.pendencias.filter(p => p !== "cerebro_nao_testado"),
    ...(pendente ? ["cerebro_nao_testado"] : [])];

  function botao(texto: string, acao: () => void) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = texto;
    b.addEventListener("click", acao, { signal }); return b;
  }
  function invalidar() {
    editado = true; validado = ""; operacao++; ocupado = false;
    salvar.disabled = escolhido === "proprio";
    if (testar) testar.disabled = false;
  }
  function campo(rotulo: string, elemento: HTMLElement, pai: HTMLElement) {
    const l = document.createElement("label"); l.append(rotulo, elemento); pai.append(l);
  }
  function texto(rotulo: string, valor: string, mudar: (v: string) => void, pai: HTMLElement, tipoCampo = "text") {
    const input = document.createElement("input"); input.type = tipoCampo; input.value = valor;
    input.addEventListener("input", () => { mudar(input.value.trim()); invalidar(); }, { signal });
    campo(rotulo, input, pai); return input;
  }
  function desenhar() {
    geracao++; container.innerHTML = ""; testar = undefined;
    const f = document.createElement("fieldset"); f.innerHTML = "<legend>Cérebro</legend>";
    for (const [valor, rotulo] of [["openjarvis", "OpenJarvis"], ["proprio", "Cérebro próprio"]]) {
      const radio = document.createElement("input"); radio.type = "radio"; radio.name = "cerebro-escolha";
      radio.value = valor; radio.checked = escolhido === valor;
      radio.addEventListener("change", () => { if (radio.checked) { escolhido = valor; invalidar(); desenhar(); } }, { signal });
      campo(rotulo, radio, f);
    }
    if (escolhido === "proprio") {
      const form = document.createElement("div"); form.id = "cerebro-proprio-form";
      const tipos = document.createElement("select"); tipos.id = "cerebro-tipo";
      for (const [v, t] of [["openai_compat", "OpenAI compatível"], ["lmstudio", "LM Studio (modelos baixados)"],
        ["anthropic", "Anthropic"], ["google", "Google"], ["openai_nativo", "OpenAI"]]) {
        const o = document.createElement("option"); o.value = v; o.textContent = t; tipos.append(o);
      }
      tipos.value = tipo;
      tipos.addEventListener("change", () => { tipo = tipos.value; invalidar(); }, { signal });
      campo("Tipo de provedor", tipos, form);
      const urlInput = texto("URL base", url, v => { url = v; }, form, "url");
      const modeloInput = texto("Modelo", modelo, v => { modelo = v; }, form);
      texto("Referência da credencial (tipo:id, nos Painéis)", ref, v => { ref = v; }, form);
      // Também lê value no clique para chamadas DOM de harness sem eventos de entrada.
      testar = botao("Testar conexão", () => { url = urlInput.value.trim(); modelo = modeloInput.value.trim(); void testarConexao(); });
      form.append(testar);
      salvar = botao("Salvar", () => { void salvarEscolha(false); }); salvar.disabled = validado !== assinatura(); form.append(salvar);
      const listar = botao("Listar modelos baixados", () => { url = urlInput.value.trim(); void listarModelos(); });
      listar.id = "cerebro-listar"; form.append(listar);
      const modelos = document.createElement("select"); modelos.id = "cerebro-modelos";
      modelos.addEventListener("change", () => { modelo = modelos.value; modeloInput.value = modelo; invalidar(); }, { signal });
      form.append(modelos);
      const trocar = botao("Descarregar anterior e carregar escolhido", () => {
        url = urlInput.value.trim(); modelo = modeloInput.value.trim(); void trocarModelo();
      });
      trocar.id = "cerebro-trocar"; form.append(trocar);
      const nota = document.createElement("p");
      nota.textContent = "Sem GPU, configure CPU no provedor local. A troca exige confirmar a descarga; listar e testar não carregam modelos no LM Studio. Configure agentes pela caixa de ferramentas dos Painéis, sem teste de login.";
      form.append(nota);
      const link = document.createElement("a"); link.href = "https://lmstudio.ai/docs/developer/core/server";
      link.textContent = "Como iniciar o servidor do LM Studio"; link.target = "_blank"; link.rel = "noreferrer"; form.append(link);
      f.append(form);
    } else {
      const nota = document.createElement("p"); nota.textContent = "OpenJarvis conserva a configuração atual. A conversa permanece pendente até ser testada."; f.append(nota);
      salvar = botao("Salvar", () => { void salvarEscolha(true); }); f.append(salvar);
    }
    const cadastrados = document.createElement("select"); cadastrados.id = "cerebro-provedor";
    const manual = document.createElement("option"); manual.value = ""; manual.textContent = "Configuração manual"; cadastrados.append(manual);
    for (const p of cfg?.provedores ?? []) {
      const opt = document.createElement("option"); opt.value = p.id; opt.textContent = p.nome; cadastrados.append(opt);
    }
    cadastrados.value = provedorId;
    cadastrados.addEventListener("change", () => {
      const p = cfg?.provedores.find(p => p.id === cadastrados.value);
      provedorId = cadastrados.value;
      if (p) { escolhido = "proprio"; tipo = p.tipo; url = p.url_base; modelo = p.modelo; ref = p.credencial_ref ?? ""; }
      invalidar(); desenhar();
    }, { signal });
    campo("Provedor cadastrado nos Painéis", cadastrados, f);
    status = document.createElement("p"); status.role = "status"; status.className = "status-teste"; f.append(status);
    const pular = botao("Pular e deixar pendente", () => { void salvarEscolha(true, true); }); pular.id = "cerebro-pular"; f.append(pular);
    container.append(f);
  }

  async function chave() {
    if (!ref) return "";
    const partes = ref.split(":");
    if (partes.length !== 2) throw new Error("credencial_ausente");
    return (await (deps.lerCredencial ?? cofreLer)(partes[0], partes[1])) ?? "";
  }
  async function requisitar(acao: string, corpo: object) {
    const resposta = await fetch(`${deps.ponteUrl}/primeiro-uso/cerebro/${acao}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo), signal: AbortSignal.any([signal, AbortSignal.timeout(32000)]),
    });
    if (!resposta.ok) throw new Error("provedor_indisponivel");
    return resposta.json();
  }
  async function executar(acao: () => Promise<void>) {
    if (ocupado) return;
    ocupado = true; const id = ++operacao;
    status.textContent = "Aguarde…";
    try { await acao(); }
    catch { if (!signal.aborted && id === operacao) status.textContent = "Não consegui concluir. Confira provedor e credencial nos Painéis ou deixe pendente."; }
    finally { if (id === operacao) { ocupado = false; if (testar) testar.disabled = false; } }
  }
  async function testarConexao() {
    validado = ""; salvar.disabled = true;
    if (!tipo || !url || !modelo) { status.textContent = "Preencha tipo, URL e modelo antes de testar."; return; }
    await executar(async () => {
      const s = assinatura(), g = geracao, id = operacao;
      if (testar) testar.disabled = true;
      const resultado = await requisitar("testar", { tipo, base_url: url, modelo, chave: await chave() }) as ResultadoTeste;
      if (signal.aborted || g !== geracao || s !== assinatura() || id !== operacao) return;
      status.textContent = resultado.ok ? `Conexão OK (${resultado.primeiro_token_ms ?? "?"} ms até primeiro token)` : `Falha: ${resultado.detalhe}. Tente novamente ou deixe pendente.`;
      if (resultado.ok) { validado = s; salvar.disabled = false; }
    });
  }
  async function listarModelos() {
    await executar(async () => {
      const g = geracao, s = assinatura(), id = operacao;
      const resultado = await requisitar("modelos", { tipo, base_url: url, chave: await chave() });
      if (signal.aborted || g !== geracao || s !== assinatura() || id !== operacao) return;
      if (!resultado.ok) { status.textContent = `Falha: ${resultado.detalhe}`; return; }
      const select = container.querySelector<HTMLSelectElement>("#cerebro-modelos")!; select.innerHTML = "";
      for (const m of resultado.modelos as { id: string; instancias: unknown[] }[]) {
        const o = document.createElement("option"); o.value = m.id; o.textContent = `${m.id}${m.instancias.length ? " (carregado)" : " (baixado)"}`; select.append(o);
      }
      select.value = modelo;
      status.textContent = "Modelos já baixados. Escolha manualmente; nenhuma carga foi feita.";
    });
  }
  async function trocarModelo() {
    validado = ""; salvar.disabled = true;
    if (tipo !== "lmstudio") { status.textContent = "Controle de carga disponível apenas para LM Studio. Use o painel do seu provedor."; return; }
    await executar(async () => {
      const s = assinatura(), g = geracao, id = operacao;
      const r = await requisitar("trocar", { tipo, base_url: url, modelo, chave: await chave() }) as ResultadoTeste;
      if (signal.aborted || g !== geracao || s !== assinatura() || id !== operacao) return;
      status.textContent = r.ok ? "Carga confirmada. Teste a conexão antes de salvar." : `Troca interrompida: ${r.detalhe}`;
    });
  }
  async function salvarEscolha(pendente: boolean, pular = false) {
    if (ocupado || signal.aborted) return;
    if (!pendente && validado !== assinatura()) return;
    await executar(async () => {
      if (!pular) {
        if (escolhido === "proprio") {
          if (!cfg) throw new Error("cadastro_indisponivel");
          const p: Provedor = { id: provedorId || "primeiro-uso", nome: provedorId || "Primeiro uso", tipo, url_base: url, modelo,
            ...(ref ? { credencial_ref: ref } : {}) };
          const novo = { ...cfg, ativo: p.id, provedores: [...cfg.provedores.filter(x => x.id !== p.id), p] };
          await (deps.gravarProvedores ?? gravarPaineis)(novo); cfg = novo;
        }
        await (deps.salvarCerebro ?? (c => atualizarConfig({ cerebro: c as "openjarvis" | "proprio" })))(escolhido as "openjarvis" | "proprio");
      }
      const novo = await atualizarEstadoPrimeiroUso(deps.ponteUrl, { etapa: "voz", pendencias: pendencias(pendente),
        ...(!pular ? { cerebro_id: escolhido } : {}) });
      if (signal.aborted) return;
      if (!novo) throw new Error("persistencia_falhou");
      deps.aoSalvar?.(novo);
    });
  }
  desenhar();
  void (deps.lerProvedores ?? lerPaineis)().then(p => {
    cfg = p;
    if (signal.aborted || editado) return;
    const ativo = p.provedores.find(x => x.id === p.ativo);
    if (ativo) { provedorId = ativo.id; tipo = ativo.tipo; url = ativo.url_base; modelo = ativo.modelo; ref = ativo.credencial_ref ?? ""; }
    desenhar();
  }).catch(() => { /* Painéis indisponíveis: pular permanece disponível. */ });
  return () => { ac.abort(); container.innerHTML = ""; };
}
