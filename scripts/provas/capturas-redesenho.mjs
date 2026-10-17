// Prova do redesenho da janela de Configurações — rodada 2.
// Captura cada seção + etapas do assistente em escala 1 e 1.5.
// Injeta dados fictícios nos painéis e estados longos (avisos, diagnóstico, caminho).
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RAIZ_REPO = path.resolve(__dirname, "..", "..");
// Saída fora do git: CAPTURAS_SAIDA escolhe a pasta; o padrão fica em .coordenacao/ (ignorada).
const SAIDA = process.env.CAPTURAS_SAIDA || path.join(RAIZ_REPO, ".coordenacao", "capturas-configuracoes");
const CAPTURAS_DIR = path.join(SAIDA, "capturas");
const MEDIDAS_PATH = path.join(SAIDA, "medidas.json");
const URL_BASE = process.env.VITE_URL || "http://localhost:5175";

fs.mkdirSync(CAPTURAS_DIR, { recursive: true });

const ABAS = [
  "geral", "perfil", "voz", "atalhos", "saber", "modelos",
  "paineis-mcps",
  "sistema", "reuniao", "avisos", "atualizacao", "diagnostico"
];
const ETAPAS_PU = ["importar", "detectar", "nome", "cerebro", "voz", "audio", "resumo"];

// Dados fictícios realistas para os painéis
const DADOS_PAINEIS = {
  versao: 1,
  provedores: [
    { id: "openai-gpt4o", nome: "OpenAI GPT-4o Omni (Produção)", tipo: "openai", url_base: "https://api.openai.com/v1/chat/completions", modelo: "gpt-4o-2024-08-06", credencial_ref: "env:OPENAI_API_KEY" },
    { id: "anthropic-claude", nome: "Anthropic Claude 3.5 Sonnet v2", tipo: "anthropic", url_base: "https://api.anthropic.com/v1/messages", modelo: "claude-3-5-sonnet-20241022", credencial_ref: "cofre:anthropic_prod" },
    { id: "ollama-local", nome: "Ollama Local Llama 3.1 70B Q4_K_M", tipo: "ollama", url_base: "http://localhost:11434/api/chat", modelo: "llama3.1:70b-instruct-q4_K_M", credencial_ref: "" },
    { id: "cli-claude-code", nome: "Claude Code CLI (Agente Principal)", tipo: "cli-claude", url_base: "", modelo: "claude-sonnet-5-5", yolo: true, enxuto: false, esforco: "high" },
  ],
  ativo: "anthropic-claude",
  reserva: "ollama-local",
  agentes: {
    claude: { padrao: "claude-sonnet-5-5", modelos: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"] },
    codex: { padrao: "o3-mini", modelos: ["o3-mini", "o4-mini", "gpt-4o"] },
    opencode: { padrao: "gemini-2.5-pro", modelos: ["gemini-2.5-pro", "gemini-2.5-flash"] },
    agy: { padrao: "agy-v1", modelos: ["agy-v1", "agy-v0"] },
  },
  mcps: [
    { id: "filesystem", nome: "Filesystem MCP Server", habilitado: true, command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"], credencial_ref: "" },
    { id: "github", nome: "GitHub MCP (Repos & Issues)", habilitado: true, url: "https://mcp.github.com/api/v1/stream", credencial_ref: "cofre:github_mcp_token" },
    { id: "postgres-dev", nome: "PostgreSQL Dev Database", habilitado: false, command: "docker", args: ["exec", "-i", "postgres-dev", "psql", "-U", "devuser"], credencial_ref: "env:PGPASSWORD" },
  ],
};

// Avisos fictícios (12 itens)
const AVISOS_FICTICIOS = Array.from({ length: 12 }, (_, i) => ({
  id: `aviso-${i + 1}`,
  hora: new Date(Date.now() - i * 3600000).toISOString(),
  resumo: i % 3 === 0
    ? `Tarefa "${["Análise de código", "Refatoração do módulo X", "Atualização de dependências", "Revisão de PR"][i % 4]}" concluída com sucesso após ${12 + i} minutos de processamento.`
    : i % 3 === 1
      ? `Erro na conexão com o provedor ${["OpenAI", "Anthropic", "Ollama"][i % 3]}: timeout após 30s. Tentativa ${i + 1} de 3.`
      : `Novo aviso do sistema: ${["Memória acima de 80%", "GPU em uso por outro processo", "Atualização disponível", "Configuração alterada externamente"][i % 4]}.`,
  lido: i > 4,
}));

// Diagnóstico com saída longa
const DIAGNOSTICO_LONGO = Array.from({ length: 40 }, (_, i) =>
  `[${new Date(Date.now() - i * 60000).toLocaleTimeString("pt-BR")}] ${
    i % 5 === 0 ? "INFO" : i % 5 === 1 ? "WARN" : i % 5 === 2 ? "ERROR" : i % 5 === 3 ? "DEBUG" : "TRACE"
  } ${[
    "Verificando integridade dos arquivos de configuração...",
    "Conexão com OpenJarvis estabelecida em 127.0.0.1:8765",
    "Falha ao carregar modelo 'llama3.1:70b': memória insuficiente na GPU",
    "Cache de tokens: 12.4MB utilizados, 87.6MB disponíveis",
    "Latência média do provedor Anthropic: 1.2s (últimas 10 requisições)",
    "Processo do widget reiniciado automaticamente (PID anterior: 4521)",
    "Sincronização de configurações com o HUD concluída",
    "Aviso: certificado SSL do endpoint local expira em 14 dias",
    "Módulo de voz: transcrição ativa com VAD threshold=0.03",
    "Backup automático da config criado em %LOCALAPPDATA%\\rdl-vard\\backup\\config-20261016.json",
  ][i % 10]}`
).join("\n");

// Caminho longo (fictício, sem letra de unidade) para teste de quebra de linha
const CAMINHO_LONGO = "%LOCALAPPDATA%\\Programas\\Vard\\resources\\app\\src-tauri\\target\\release\\build\\tauri-app-abcdef1234567890\\out\\configuracoes.html";

async function medirPagina(page, nome) {
  return await page.evaluate((label) => {
    const doc = document.scrollingElement || document.documentElement;
    const temRolagemH = doc.scrollWidth > doc.clientWidth + 1;
    const viewportW = window.innerWidth;
    const elementosCortados = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) {
      const el = walker.currentNode;
      if (!(el instanceof HTMLElement)) continue;
      const estilo = getComputedStyle(el);
      if (estilo.display === "none" || estilo.visibility === "hidden") continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 && rect.height < 1) continue;
      if (rect.right > viewportW + 1 && el.textContent.trim().length > 0) {
        const tag = el.tagName.toLowerCase();
        const id = el.id ? `#${el.id}` : "";
        elementosCortados.push(`${tag}${id} right=${Math.round(rect.right)} viewport=${viewportW}`);
      }
    }
    const containersRolagemV = [];
    const todos = document.querySelectorAll("*");
    for (const el of todos) {
      if (!(el instanceof HTMLElement)) continue;
      if (el.scrollHeight > el.clientHeight + 2) {
        const estilo = getComputedStyle(el);
        if (estilo.overflowY === "auto" || estilo.overflowY === "scroll") {
          const tag = el.tagName.toLowerCase();
          const id = el.id ? `#${el.id}` : "";
          const cls = el.className ? `.${el.className.split(" ")[0]}` : "";
          containersRolagemV.push(`${tag}${id}${cls}`);
        }
      }
    }
    // Contagem de nós visíveis com texto (para detectar telas vazias)
    let nosComTexto = 0;
    const walkerTexto = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walkerTexto.nextNode()) {
      const no = walkerTexto.currentNode;
      if (no.textContent.trim().length > 0) {
        const pai = no.parentElement;
        if (pai) {
          const estilo = getComputedStyle(pai);
          if (estilo.display !== "none" && estilo.visibility !== "hidden") nosComTexto++;
        }
      }
    }
    return {
      nome: label,
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      temRolagemHorizontal: temRolagemH,
      elementosCortados,
      containersComRolagemVertical: containersRolagemV,
      nosComTextoVisiveis: nosComTexto,
      viewport: { width: window.innerWidth, height: window.innerHeight },
    };
  }, nome);
}

function registrarRotasAPI(page, primeiroUsoConcluido) {
  // Estado inteiro guardado entre chamadas: o PUT mescla e devolve o estado completo, como a ponte real.
  const estadoPU = { schema: 1, etapa: "importar", concluido: primeiroUsoConcluido, pendencias: [] };
  page.route((url) => url.pathname === "/primeiro-uso" || url.pathname === "/primeiro-uso/reabrir", async (route) => {
    if (route.request().method() === "PUT") Object.assign(estadoPU, JSON.parse(route.request().postData() || "{}"));
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadoPU) });
  });
  page.route((url) => url.pathname.endsWith("/saude"), async (route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
  });
  page.route((url) => url.pathname.endsWith("/status") && !url.pathname.includes("."), async (route) => {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const resultados = [];

  for (const scale of [1, 1.5]) {
    const context = await browser.newContext({
      viewport: { width: 960, height: 640 },
      deviceScaleFactor: scale,
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => console.log(`[${scale}x] ERRO DA PAGINA: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") console.log(`[${scale}x] CONSOLE: ${m.text().slice(0, 200)}`); });

    // Mock do invoke do Tauri com dados fictícios
    await page.addInitScript(({ dadosPaineis, avisos, diagnostico, caminhoLongo }) => {
      window.__TAURI__ = {
        core: {
          invoke: async (cmd, args) => {
            if (cmd === "ler_config") return {
              schema: 3, ponte_url: window.__PROVA_PONTE__ || "", nome: "Aurora", variantes: ["Auri", "Au"], idioma: "pt",
              openjarvis_url: "http://localhost:8765", gui_url: "http://localhost:3000/interface-texto-com-nome-bem-longo-para-testar-quebra-de-linha", usuario: "Ana",
              tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false,
              click_through: false, invisivel: false, logon: false, sala_monitor: "",
              nao_ouvir: false, nao_falar: false, falar_avisos: true,
              velocidade: 1.1, instrucao_formato: "Responda sempre em português do Brasil, de forma concisa.", finish_ms: 600, limiar_vad: 0.03,
              conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "claude-sonnet-5-5",
              microfone_id: "microfone_usb_hd_pro", saida_id: "saidas_hdmi_monitor_principal",
              caminho_instalacao: caminhoLongo,
            };
            if (cmd === "ler_paineis") {
              if (args?.arquivo === "estado") return { revisao: 3, estado: "aplicado", ativo_efetivo: "anthropic-claude", reserva_efetiva: "ollama-local" };
              return dadosPaineis;
            }
            if (cmd === "inicio_no_logon_ativo") return false;
            if (cmd === "listar_monitores") return [{ id: "\\\\.\\DISPLAY1", nome: "Monitor Principal 1920x1080" }, { id: "\\\\.\\DISPLAY2", nome: "Monitor Secundário 2560x1440" }];
            if (cmd === "falhas_de_atalho") return [];
            if (cmd === "versao_do_app") return "0.9.1";
            if (cmd === "buscar_release") return { url: "https://github.com/exemplo/vard/releases/download/v0.9.2/vard-setup.exe", nome: "vard-setup.exe", bytes: 4567890, sha256: "abc123def456" };
            return null;
          },
        },
        event: {
          emitTo: async () => {},
          listen: async () => () => {},
        },
      };
      // O app usa @tauri-apps/api, que chama window.__TAURI_INTERNALS__ (não window.__TAURI__).
      let proxId = 1;
      window.__TAURI_INTERNALS__ = {
        invoke: (cmd, args) => (cmd.startsWith("plugin:") ? Promise.resolve(proxId++) : window.__TAURI__.core.invoke(cmd, args)),
        transformCallback: (cb) => { const id = proxId++; window[`_${id}`] = cb; return id; },
        unregisterCallback: () => {},
        convertFileSrc: (p) => p,
        metadata: { currentWindow: { label: "configuracoes" }, currentWebview: { windowLabel: "configuracoes", label: "configuracoes" } },
      };
      window.__VARD_DADOS_PROVA__ = { avisos, diagnostico };
    }, { dadosPaineis: DADOS_PAINEIS, avisos: AVISOS_FICTICIOS, diagnostico: DIAGNOSTICO_LONGO, caminhoLongo: CAMINHO_LONGO });

    registrarRotasAPI(page, true);
    await page.goto(`${URL_BASE}/configuracoes.html`);
    await page.waitForSelector("#painel nav button", { timeout: 20000 });
    await page.waitForTimeout(800);

    // Preenche dados dinâmicos nas seções que precisam (avisos, diagnóstico)
    await page.evaluate(({ avisos, diagnostico }) => {
      // Avisos
      const listaAvisos = document.querySelector("#avi-lista");
      if (listaAvisos) {
        listaAvisos.innerHTML = avisos.map(a => `
          <div class="aviso-linha ${!a.lido ? 'novo' : ''}" data-id="${a.id}">
            <span class="hora">${new Date(a.hora).toLocaleTimeString("pt-BR")}</span>
            <span class="resumo">${a.resumo}</span>
            <button type="button" onclick="this.closest('.aviso-linha').remove()">✕</button>
          </div>
        `).join("");
      }
      // Diagnóstico
      const diagEl = document.querySelector("#cfg-diagnostico");
      if (diagEl) {
        diagEl.innerHTML = `<pre style="white-space:pre-wrap;max-height:400px;overflow-y:auto;overflow-x:hidden;background:rgba(0,240,255,0.05);padding:8px;border-radius:4px;font-size:11px;line-height:1.4;">${diagnostico}</pre>`;
      }
    }, { avisos: AVISOS_FICTICIOS, diagnostico: DIAGNOSTICO_LONGO });

    // Captura cada seção
    for (const aba of ABAS) {
      const btn = await page.$(`nav button[data-aba="${aba}"]`);
      if (!btn) {
        console.warn(`[${scale}x] Botão da aba "${aba}" não encontrado`);
        continue;
      }
      await btn.click();
      await page.waitForTimeout(400);
      const nomeArquivo = `secao-${aba}-escala${scale}.png`;
      await page.screenshot({ path: path.join(CAPTURAS_DIR, nomeArquivo), fullPage: false });
      const medida = await medirPagina(page, `${aba}@${scale}x`);
      resultados.push(medida);
      console.log(`[${scale}x] Capturada seção: ${aba} (${medida.nosComTextoVisiveis} nós com texto)`);
    }

    // Rodada 2 — Perfil: lista inteira com scroll, modal de confirmação aberto, campos preenchidos
    const btnPerfilR2 = await page.$('nav button[data-aba="perfil"]');
    if (btnPerfilR2) {
      await btnPerfilR2.click();
      await page.waitForTimeout(500);
      // 1. Lista inteira de perfis prontos (scroll até o fim para mostrar os bem-humorados)
      const gradePerfis = await page.$('.perfil-prontos-grade');
      if (gradePerfis) {
        await page.evaluate((el) => { el.scrollTop = el.scrollHeight; }, gradePerfis);
        await page.waitForTimeout(300);
      }
      await page.screenshot({ path: path.join(CAPTURAS_DIR, `perfil-lista-inteira-escala${scale}.png`), fullPage: false });
      resultados.push(await medirPagina(page, `perfil-lista-inteira@${scale}x`));
      // 2. Preencher campos com texto existente para forçar modal de confirmação
      await page.fill('#perfil-tom', 'tom existente');
      await page.fill('#perfil-personalidade', 'personalidade existente');
      await page.fill('#perfil-instrucoes', 'instruções existentes');
      await page.waitForTimeout(200);
      // Clicar no primeiro card para abrir o modal de confirmação
      const btnUsarPerfil = await page.$('#cfg-perfil .card button.primaria');
      if (btnUsarPerfil) {
        await btnUsarPerfil.click();
        await page.waitForSelector('.modal', { timeout: 5000 }).catch(() => null);
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `perfil-modal-confirmacao-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `perfil-modal-confirmacao@${scale}x`));
        // Confirmar substituição
        const btnSubstituir = await page.$('.modal button.primaria');
        if (btnSubstituir) {
          await btnSubstituir.click();
          await page.waitForTimeout(400);
        }
      }
      // 3. Campos do perfil preenchidos após escolher um perfil pronto
      await page.screenshot({ path: path.join(CAPTURAS_DIR, `perfil-campos-preenchidos-escala${scale}.png`), fullPage: false });
      resultados.push(await medirPagina(page, `perfil-campos-preenchidos@${scale}x`));
    }

    // Estados extras da seção "Quem responde" (brief 0.9.3 + rodada 2)
    // Cada estado recarrega a página com o mock adequado e espera o botão ficar visível antes de interagir.
    const btnModelos = await page.$('nav button[data-aba="modelos"]');
    if (btnModelos) {
      // Helper: recarrega, espera nav, clica em modelos, espera botão Adicionar ficar visível
      async function prepararEstadoExtras(setupInvoke) {
        if (setupInvoke) {
          await page.evaluate(setupInvoke);
        }
        await page.reload();
        await page.waitForSelector("#painel nav button", { timeout: 20000 });
        await page.waitForTimeout(300);
        const btn = await page.$('nav button[data-aba="modelos"]');
        if (btn) await btn.click();
        await page.waitForSelector('button.cards-adicionar', { timeout: 10000 }).catch(() => null);
        await page.waitForTimeout(400);
      }

      // 1. Modal de adicionar aberto
      await prepararEstadoExtras(null);
      const btnAdd1 = await page.$('button.cards-adicionar');
      if (btnAdd1) {
        await btnAdd1.click();
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-modal-adicionar-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `quem-responde-modal-adicionar@${scale}x`));
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);
      }

      // 2. Seção vazia
      await prepararEstadoExtras(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-vazia-escala${scale}.png`), fullPage: false });
      resultados.push(await medirPagina(page, `quem-responde-vazia@${scale}x`));

      // 3. Aviso de ponte fora
      await prepararEstadoExtras(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:99999", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-ponte-fora-escala${scale}.png`), fullPage: false });
      resultados.push(await medirPagina(page, `quem-responde-ponte-fora@${scale}x`));

      // 4. Modal de CLI detectada (Claude Code) — rota registrada ANTES do reload.
      // O invoke trocado por evaluate se perde no reload; o mock base lê a ponte de __PROVA_PONTE__,
      // e sem ponte a detecção nem é consultada.
      await page.addInitScript(() => { window.__PROVA_PONTE__ = "http://127.0.0.1:8765"; });
      await page.route("**/cli/detectar", (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ tipo: "cli-claude", instalada: true, versao: "2.1.301", modelos: ["claude-sonnet-5-5", "claude-opus-5-5"] }]) });
      });
      // Recarrega com a rota ativa para que detectarClis() pegue o mock
      await page.reload();
      await page.waitForSelector("#painel nav button", { timeout: 20000 });
      await page.waitForTimeout(300);
      const btnModelosCli = await page.$('nav button[data-aba="modelos"]');
      if (btnModelosCli) await btnModelosCli.click();
      await page.waitForSelector('button.cards-adicionar', { timeout: 10000 }).catch(() => null);
      await page.waitForTimeout(600);
      // Agora prepara o invoke mock (depois do reload, pois o evaluate anterior se perde)
      await page.evaluate(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:8765", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      const btnAddCli = await page.$('button.cards-adicionar');
      if (btnAddCli) {
        await btnAddCli.click();
        await page.waitForTimeout(400);
        const tipoSelCli = await page.$('.modal select');
        if (tipoSelCli) {
          await tipoSelCli.selectOption("cli-claude");
          await page.waitForTimeout(500);
        }
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-modal-cli-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `quem-responde-modal-cli@${scale}x`));
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);
      }
      await page.unroute("**/cli/detectar");

      // 4b. Modal de CLI Codex (tarefas longas travadas) — rota ANTES do reload
      await page.route("**/cli/detectar", (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ tipo: "cli-codex", instalada: true, versao: "0.1.2504", modelos: ["o3-mini", "o4-mini"] }]) });
      });
      await page.reload();
      await page.waitForSelector("#painel nav button", { timeout: 20000 });
      await page.waitForTimeout(300);
      const btnModelosCodex = await page.$('nav button[data-aba="modelos"]');
      if (btnModelosCodex) await btnModelosCodex.click();
      await page.waitForSelector('button.cards-adicionar', { timeout: 10000 }).catch(() => null);
      await page.waitForTimeout(600);
      await page.evaluate(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:8765", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      const btnAddCodex = await page.$('button.cards-adicionar');
      if (btnAddCodex) {
        await btnAddCodex.click();
        await page.waitForTimeout(400);
        const tipoSelCodex = await page.$('.modal select');
        if (tipoSelCodex) {
          await tipoSelCodex.selectOption("cli-codex");
          await page.waitForTimeout(500);
        }
        await page.$eval(".modal-miolo", (el) => { el.scrollTop = el.scrollHeight; }).catch(() => null);
        await page.waitForTimeout(150);
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-modal-codex-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `quem-responde-modal-codex@${scale}x`));
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);
      }
      await page.unroute("**/cli/detectar");

      // 4c. Modal de CLI não encontrada — rota ANTES do reload
      await page.route("**/cli/detectar", (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      });
      await page.reload();
      await page.waitForSelector("#painel nav button", { timeout: 20000 });
      await page.waitForTimeout(300);
      const btnModelosNao = await page.$('nav button[data-aba="modelos"]');
      if (btnModelosNao) await btnModelosNao.click();
      await page.waitForSelector('button.cards-adicionar', { timeout: 10000 }).catch(() => null);
      await page.waitForTimeout(600);
      await page.evaluate(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:8765", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      const btnAddNaoEncontrado = await page.$('button.cards-adicionar');
      if (btnAddNaoEncontrado) {
        await btnAddNaoEncontrado.click();
        await page.waitForTimeout(400);
        const tipoSelNao = await page.$('.modal select');
        if (tipoSelNao) {
          await tipoSelNao.selectOption("cli-claude");
          await page.waitForTimeout(500);
        }
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-modal-cli-nao-encontrado-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `quem-responde-modal-cli-nao-encontrado@${scale}x`));
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);
      }
      await page.unroute("**/cli/detectar");

      // 5. Modal de LM Studio após Buscar modelos
      await page.route("**/primeiro-uso/cerebro/modelos", (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, modelos: [{ id: "llama-3.2-3b-instruct" }, { id: "qwen2.5-7b-instruct" }, { id: "mistral-7b-v0.3" }, { id: "gemma-3-4b-it" }] }) });
      });
      await prepararEstadoExtras(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return { versao: 1, provedores: [], ativo: null, reserva: null, agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } }, mcps: [] };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:8765", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      const btnAddLm = await page.$('button.cards-adicionar');
      if (btnAddLm) {
        await btnAddLm.click();
        await page.waitForTimeout(400);
        const urlInputLm = await page.$('.modal input[type="url"]');
        if (urlInputLm) await urlInputLm.fill("http://localhost:1234/v1");
        const btnBuscarLm = await page.$('.modal button:has-text("Buscar modelos")');
        if (btnBuscarLm) {
          await btnBuscarLm.click();
          await page.waitForTimeout(800);
        }
        await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-modal-lmstudio-escala${scale}.png`), fullPage: false });
        resultados.push(await medirPagina(page, `quem-responde-modal-lmstudio@${scale}x`));
        await page.keyboard.press("Escape");
        await page.waitForTimeout(200);
      }
      await page.unroute("**/primeiro-uso/cerebro/modelos");

      // 6. Seção compacta com 6+ provedores
      await prepararEstadoExtras(() => {
        window.__TAURI_INTERNALS__.invoke = async (cmd) => {
          if (cmd === "ler_paineis") return {
            versao: 1,
            provedores: [
              { id: "lm1", nome: "LM Studio Local", tipo: "lmstudio", url_base: "http://localhost:1234/v1", modelo: "llama-3.2-3b-instruct" },
              { id: "ollama1", nome: "Ollama Servidor", tipo: "ollama", url_base: "http://localhost:11434", modelo: "qwen2.5:7b" },
              { id: "openai1", nome: "OpenAI API Produção", tipo: "openai_nativo", url_base: "https://api.openai.com/v1", modelo: "gpt-4o-mini" },
              { id: "anthropic1", nome: "Anthropic Claude", tipo: "anthropic", url_base: "https://api.anthropic.com", modelo: "claude-sonnet-5-5" },
              { id: "google1", nome: "Google Gemini", tipo: "google", url_base: "https://generativelanguage.googleapis.com", modelo: "gemini-2.5-flash" },
              { id: "compat1", nome: "Servidor OpenAI Compatível Interno com Nome Longo", tipo: "openai_compat", url_base: "http://127.0.0.1:8080/v1", modelo: "modelo-interno-v2" },
            ],
            ativo: "lm1",
            reserva: "ollama1",
            agentes: { claude: { padrao: "", modelos: [] }, codex: { padrao: "", modelos: [] }, opencode: { padrao: "", modelos: [] }, agy: { padrao: "", modelos: [] } },
            mcps: [],
          };
          if (cmd === "ler_config") return { schema: 3, ponte_url: "http://127.0.0.1:8765", nome: "Aurora", variantes: ["Auri"], idioma: "pt", openjarvis_url: "http://localhost:8765", gui_url: "", usuario: "Ana", tamanho: "medio", tamanho_px: 320, compacto: false, sempre_no_topo: false, click_through: false, invisivel: false, logon: false, sala_monitor: "", nao_ouvir: false, nao_falar: false, falar_avisos: true, velocidade: 1.1, instrucao_formato: "", finish_ms: 600, limiar_vad: 0.03, conversa_ms: 5000, atualizacao_ao_abrir: true, modelo: "", microfone_id: "", saida_id: "", caminho_instalacao: "" };
          return null;
        };
      });
      await page.screenshot({ path: path.join(CAPTURAS_DIR, `quem-responde-compacta-escala${scale}.png`), fullPage: false });
      resultados.push(await medirPagina(page, `quem-responde-compacta@${scale}x`));
    }

    // Captura etapas do assistente
    // Instalação nova: com uma ponte (fictícia) e /primeiro-uso não concluído, o app monta o assistente de verdade.
    await page.unrouteAll();
    registrarRotasAPI(page, false);
    await page.addInitScript(() => { window.__PROVA_PONTE__ = "http://127.0.0.1:59999"; });
    await page.reload();
    await page.waitForSelector("#primeiro-uso-container:not([hidden]) #primeiro-uso-proximo", { timeout: 20000 });
    await page.waitForTimeout(500);

    for (const etapa of ETAPAS_PU) {
      const visivel = await page.$eval("#primeiro-uso-container", (el) => !el.hidden).catch(() => false);
      if (!visivel) break;
      const nomeArquivo = `assistente-${etapa}-escala${scale}.png`;
      await page.screenshot({ path: path.join(CAPTURAS_DIR, nomeArquivo), fullPage: false });
      const medida = await medirPagina(page, `assistente-${etapa}@${scale}x`);
      resultados.push(medida);
      console.log(`[${scale}x] Capturada etapa assistente: ${etapa} (${medida.nosComTextoVisiveis} nós com texto)`);

      const btnProximo = await page.$("#primeiro-uso-proximo");
      if (btnProximo) {
        if (etapa === "nome") {
          const inputNome = await page.$("#primeiro-uso-nome-input");
          if (inputNome) await inputNome.fill("Aurora");
        }
        await btnProximo.click();
        await page.waitForTimeout(500);
      } else {
        break;
      }
    }

    await context.close();
  }

  await browser.close();

  const resumo = {
    geradoEm: new Date().toISOString(),
    totalCapturas: resultados.length,
    rolagemHorizontal: resultados.filter((r) => r.temRolagemHorizontal).map((r) => r.nome),
    elementosCortados: resultados.filter((r) => r.elementosCortados.length > 0).map((r) => ({ nome: r.nome, elementos: r.elementosCortados })),
    containersComRolagemVertical: [...new Set(resultados.flatMap((r) => r.containersComRolagemVertical))],
    capturasComPoucoTexto: resultados.filter((r) => r.nosComTextoVisiveis < 5).map((r) => ({ nome: r.nome, nos: r.nosComTextoVisiveis })),
    detalhes: resultados,
  };

  fs.writeFileSync(MEDIDAS_PATH, JSON.stringify(resumo, null, 2), "utf-8");
  console.log(`Medidas salvas em: ${MEDIDAS_PATH}`);
  console.log(`Rolagem horizontal detectada em: ${resumo.rolagemHorizontal.length} captura(s)`);
  console.log(`Elementos cortados em: ${resumo.elementosCortados.length} captura(s)`);
  console.log(`Capturas com pouco texto (<5 nós): ${resumo.capturasComPoucoTexto.length}`);
}

main().catch((e) => { console.error(e); process.exit(1); });