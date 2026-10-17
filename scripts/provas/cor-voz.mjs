// Prova por CDP, sem teclado/mouse do sistema e sem serviços ou dados reais.
// Abre Vite em porta livre e Edge isolado; fecha ambos ao terminar.
import { createServer } from "vite";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import WebSocket from "ws";

const saida = path.resolve(".coordenacao/prova-cor-voz");
const perfil = await fs.mkdtemp(path.join(os.tmpdir(), "vard-cor-voz-"));
const executavel = process.env.VARD_NAVEGADOR || path.join(process.env["PROGRAMFILES(X86)"], "Microsoft/Edge/Application/msedge.exe");
const aguardar = (ms) => new Promise((ok) => setTimeout(ok, ms));
let navegador, servidor, socket, fimNavegador;
const pendentes = new Map();
let sequencia = 0;
const resultados = [];
const erros = [];

function chamar(method, params = {}) {
  const id = ++sequencia;
  return new Promise((ok, falhar) => {
    const prazo = setTimeout(() => { pendentes.delete(id); falhar(new Error(`Prazo excedido: ${method}`)); }, 10000);
    pendentes.set(id, { ok: (r) => { clearTimeout(prazo); ok(r); }, falhar: (e) => { clearTimeout(prazo); falhar(e); } });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function avaliar(expression) {
  const r = await chamar("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
  return r.result.value;
}
async function esperar(expression) {
  for (let i = 0; i < 100; i++) {
    if (await avaliar(expression)) return;
    await aguardar(100);
  }
  throw new Error(`Condição não atendida: ${expression}`);
}

try {
  await fs.mkdir(saida, { recursive: true });
  servidor = await createServer({ server: { port: 0, host: "127.0.0.1", strictPort: true } });
  await servidor.listen();
  const porta = servidor.httpServer.address().port;
  const origem = `http://127.0.0.1:${porta}`;
  navegador = spawn(executavel, ["--headless=new", "--no-first-run", "--disable-gpu", "--remote-debugging-port=0", `--user-data-dir=${perfil}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
  fimNavegador = new Promise((ok) => navegador.once("exit", ok));
  console.log(JSON.stringify({ executavel: path.basename(executavel), pid: navegador.pid, inicio: new Date().toISOString(), portaVite: porta }));
  let portaCdp;
  for (let i = 0; i < 150; i++) {
    try { portaCdp = Number((await fs.readFile(path.join(perfil, "DevToolsActivePort"), "utf8")).split("\n")[0]); break; } catch { await aguardar(100); }
  }
  if (!portaCdp) throw new Error("Navegador não abriu o CDP");
  const paginas = await (await fetch(`http://127.0.0.1:${portaCdp}/json/list`)).json();
  socket = new WebSocket(paginas.find((p) => p.type === "page").webSocketDebuggerUrl);
  await new Promise((ok, falhar) => { socket.once("open", ok); socket.once("error", falhar); });
  socket.on("message", (dados) => {
    const ev = JSON.parse(dados.toString());
    if (ev.id && pendentes.has(ev.id)) {
      const p = pendentes.get(ev.id); pendentes.delete(ev.id);
      if (ev.error) p.falhar(new Error(ev.error.message)); else p.ok(ev.result);
    }
    if (ev.method === "Runtime.exceptionThrown") erros.push(ev.params.exceptionDetails.text);
  });
  await chamar("Page.enable");
  await chamar("Runtime.enable");
  await chamar("Page.addScriptToEvaluateOnNewDocument", { source: `
    window.__provaSalva = null;
    let proximo = 1;
    window.__TAURI_INTERNALS__ = {
      invoke: async (cmd, args) => {
        if (cmd === 'ler_config') return { nome: 'vard', variantes: ['vard'], voz_provedor: 'propria', voz_motor: 'edge', voz_propria: 'pt-BR-FranciscaNeural', cor_elementos: '#ec4899', opacidade_elementos: 0.6, ponte_url: 'http://127.0.0.1:49999', voz_url: 'http://127.0.0.1:49998', atualizacao_ao_abrir: false };
        if (cmd === 'gravar_config') { window.__provaSalva = args.config; return null; }
        if (cmd === 'falhas_de_atalho' || cmd === 'listar_monitores') return [];
        if (cmd === 'versao_do_app') return '0.9.5';
        if (cmd.startsWith('plugin:')) return proximo++;
        return null;
      },
      transformCallback: (cb) => { const id = proximo++; window['_' + id] = cb; return id; },
      unregisterCallback: () => {},
      metadata: { currentWindow: { label: 'configuracoes' }, currentWebview: { label: 'configuracoes', windowLabel: 'configuracoes' } }
    };
    const original = window.fetch.bind(window);
    window.fetch = async (alvo, init) => {
      const u = new URL(String(alvo), location.href);
      let dados;
      if (u.pathname === '/saude') dados = { pronta: true, xtts: false, kokoro: true, edge: true, piper: true };
      else if (u.pathname === '/vozes') dados = { vozes: ['Voz Fictícia'], atual: 'Voz Fictícia' };
      else if (u.pathname === '/pacotes') dados = { pacotes: [{ id: 'xtts-v2', nome: 'XTTS-v2', versao: '1', tipo: 'motor', descricao: 'Motor opcional', bytes_download: 100, licenca_url: 'https://example.com/licenca', licenca_nome: 'Licença fictícia' }] };
      else if (u.pathname === '/primeiro-uso') dados = { schema: 1, concluido: true, etapa: 'resumo', pendencias: [] };
      else if (u.origin !== location.origin || u.pathname.startsWith('/oj/')) dados = {};
      else return original(alvo, init);
      return new Response(JSON.stringify(dados), { headers: { 'Content-Type': 'application/json' } });
    };
  ` });
  await chamar("Emulation.setDeviceMetricsOverride", { width: 960, height: 640, deviceScaleFactor: 1, mobile: false });
  await chamar("Page.navigate", { url: `${origem}/configuracoes.html` });
  await esperar('Boolean(document.querySelector("nav button[data-aba=voz]"))');
  await avaliar('document.querySelector("nav button[data-aba=voz]").click()');
  await esperar('document.querySelector("[data-motor=edge]")?.getAttribute("aria-pressed") === "true"');
  await esperar('document.querySelector("#cfg-voz-principal")?.options.length > 1');

  for (const [largura, altura] of [[960, 640], [640, 427]]) {
    await chamar("Emulation.setDeviceMetricsOverride", { width: largura, height: altura, deviceScaleFactor: 1, mobile: false });
    const medidas = await avaliar(`(() => {
      const conteudo = document.querySelector('.conteudo');
      const secao = document.querySelector('section[data-aba=voz]');
      const fora = [...secao.querySelectorAll('*')].filter(el => el.getClientRects().length && el.getBoundingClientRect().right > innerWidth + 1).map(el => el.id || el.className || el.tagName);
      return { largura: innerWidth, altura: innerHeight, documento: document.documentElement.scrollWidth, conteudo: conteudo.clientWidth, larguraConteudo: conteudo.scrollWidth, rolagemVertical: conteudo.scrollHeight > conteudo.clientHeight, fora };
    })()`);
    resultados.push(medidas);
    if (medidas.documento > largura || medidas.larguraConteudo > medidas.conteudo + 1 || medidas.fora.length) throw new Error(`Estouro horizontal: ${JSON.stringify(medidas)}`);
    const captura = await chamar("Page.captureScreenshot", { format: "png" });
    await fs.writeFile(path.join(saida, `voz-${largura}x${altura}.png`), Buffer.from(captura.data, "base64"));
  }
  await avaliar('document.querySelector("[data-motor=piper]").click(); document.querySelector("#cfg-salvar").click()');
  await esperar('window.__provaSalva?.voz_motor === "piper"');
  resultados.push(await avaliar('({ motorSalvo: window.__provaSalva.voz_motor, provedorSalvo: window.__provaSalva.voz_provedor, vozSalva: window.__provaSalva.voz_propria })'));
  await chamar("Emulation.setDeviceMetricsOverride", { width: 960, height: 640, deviceScaleFactor: 1, mobile: false });
  await chamar("Page.navigate", { url: `${origem}/sala.html` });
  await esperar('document.querySelector("#nucleo")?.width > 0 && document.documentElement.style.getPropertyValue("--cor-elementos") === "#ec4899"');
  await aguardar(350);
  const captura = await chamar("Page.captureScreenshot", { format: "png" });
  await fs.writeFile(path.join(saida, "sala-cor.png"), Buffer.from(captura.data, "base64"));
  if (erros.length) throw new Error(`Erros de execução: ${JSON.stringify(erros)}`);
  await fs.writeFile(path.join(saida, "medidas.json"), JSON.stringify({ resultados, erros }, null, 2));
  console.log(JSON.stringify({ resultados, erros }));
  console.log("VERDICT: PASS");
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    await chamar("Browser.close").catch(() => {});
    socket.close();
  }
  if (navegador && navegador.exitCode === null && navegador.signalCode === null) {
    await Promise.race([fimNavegador, aguardar(5000)]);
    if (navegador.exitCode === null && navegador.signalCode === null) {
      navegador.kill();
      await Promise.race([fimNavegador, aguardar(5000)]);
    }
  }
  await servidor?.close();
  // Só remove o perfil temporário criado por esta prova, dentro do temporário do sistema.
  if (path.dirname(path.resolve(perfil)) === path.resolve(os.tmpdir()) && path.basename(perfil).startsWith("vard-cor-voz-")) {
    await fs.rm(perfil, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  }
  const encerrado = !navegador || navegador.exitCode !== null || navegador.signalCode !== null;
  console.log(JSON.stringify({ pidNavegador: navegador?.pid, encerrado, viteFechado: !servidor?.httpServer?.listening }));
  if (!encerrado) throw new Error("Navegador da prova ainda está em execução");
}
