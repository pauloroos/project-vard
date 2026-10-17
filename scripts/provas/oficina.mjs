// Prova da Oficina por CDP, sem teclado/mouse do sistema nem serviços reais.
// Navegador isolado: PROVA_NAVEGADOR ou Edge do Windows; captura em .coordenacao/ (fora do git).
import { createServer } from "vite";
import { WebSocket } from "ws";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";

const saida = path.resolve(process.env.PROVA_SAIDA || ".coordenacao/0.9.5/oficina");
const executavel = process.env.PROVA_NAVEGADOR || path.join(process.env["ProgramFiles(x86)"] || "", "Microsoft/Edge/Application/msedge.exe");
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const inicio = new Date().toISOString();
await access(executavel);
await mkdir(saida, { recursive: true });
const perfil = await mkdtemp(path.join(saida, "navegador-"));
let servidor, navegador, canal;
const medidas = [];

class CDP {
  constructor(ws) {
    this.ws = ws; this.proximo = 0; this.pendentes = new Map();
    ws.on("message", (bruto) => {
      const msg = JSON.parse(bruto.toString());
      const p = this.pendentes.get(msg.id);
      if (!p) return;
      this.pendentes.delete(msg.id); clearTimeout(p.prazo);
      if (msg.error) p.rejeitar(new Error(msg.error.message)); else p.resolver(msg.result);
    });
  }
  enviar(method, params = {}) {
    return new Promise((resolver, rejeitar) => {
      const id = ++this.proximo;
      const prazo = setTimeout(() => { this.pendentes.delete(id); rejeitar(new Error(`CDP excedeu o prazo: ${method}`)); }, 10000);
      this.pendentes.set(id, { resolver, rejeitar, prazo });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async avaliar(expression) {
    const r = await this.enviar("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ": " + r.exceptionDetails.exception?.description);
    return r.result.value;
  }
}

async function esperar(expressao) {
  for (let i = 0; i < 100; i++) { if (await canal.avaliar(expressao)) return; await pausa(100); }
  throw new Error("Estado esperado não apareceu: " + expressao);
}
async function clicar(rotulo, seletor = "document") {
  await canal.avaliar(`(() => {
    const alvo = ${seletor};
    const botao = [...alvo.querySelectorAll('button')].find(b => b.textContent === ${JSON.stringify(rotulo)});
    if (!botao || botao.disabled) throw new Error('Botão indisponível');
    botao.click();
  })()`);
}
async function capturar(nome) {
  const medida = await canal.avaliar(`(() => {
    const elementos = [...document.querySelectorAll('body *')].filter(el => el.getClientRects().length && getComputedStyle(el).display !== 'none');
    const vazamentos = elementos.filter(el => {
      const r = el.getBoundingClientRect();
      const est = getComputedStyle(el);
      return r.right > innerWidth + 1 || r.left < -1 || (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && ['auto','scroll'].includes(est.overflowX));
    }).map(el => el.tagName + (el.id ? '#' + el.id : ''));
    const miolo = document.querySelector('.modal-miolo') || document.querySelector('.conteudo');
    return { largura: innerWidth, altura: innerHeight, vazamentos, rolagemVertical: miolo.scrollHeight > miolo.clientHeight, documentoHorizontal: document.documentElement.scrollWidth > innerWidth };
  })()`);
  assert.equal(medida.largura, 960); assert.equal(medida.altura, 640);
  assert.deepEqual(medida.vazamentos, [], nome); assert.equal(medida.documentoHorizontal, false);
  const captura = await canal.enviar("Page.captureScreenshot", { format: "png" });
  await writeFile(path.join(saida, `${nome}.png`), Buffer.from(captura.data, "base64"));
  medidas.push({ nome, ...medida });
}

try {
  servidor = await createServer({ configFile: false, server: { host: "127.0.0.1", port: 0, strictPort: false, watch: { ignored: ["**/.coordenacao/**", "**/src-tauri/**", "**/.venv/**"] } }, appType: "mpa" });
  await servidor.listen();
  const porta = servidor.httpServer.address().port;
  navegador = spawn(executavel, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${perfil}`, "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "about:blank"], { windowsHide: true, stdio: "ignore" });
  console.log(JSON.stringify({ processo: "Vite/Node", pid: process.pid, inicio }));
  console.log(JSON.stringify({ processo: path.basename(executavel), pid: navegador.pid, inicio: new Date().toISOString() }));
  let portaCDP;
  for (let i = 0; i < 100; i++) {
    try { portaCDP = Number((await readFile(path.join(perfil, "DevToolsActivePort"), "utf8")).split("\n")[0]); break; } catch { await pausa(100); }
  }
  assert.ok(portaCDP, "Navegador não disponibilizou CDP");
  const alvos = await (await fetch(`http://127.0.0.1:${portaCDP}/json/list`)).json();
  const ws = new WebSocket(alvos.find((a) => a.type === "page").webSocketDebuggerUrl);
  await once(ws, "open"); canal = new CDP(ws);
  await canal.enviar("Page.enable");
  await canal.enviar("Emulation.setDeviceMetricsOverride", { width: 960, height: 640, deviceScaleFactor: 1, mobile: false });
  await canal.enviar("Page.addScriptToEvaluateOnNewDocument", { source: `
    let proximo = 0;
    window.__oficina = { versao: 1, habilidades: [], desligadas: [] };
    window.__TAURI_INTERNALS__ = {
      invoke: async (cmd, args) => {
        if (cmd === 'ler_config') return { schema: 3, nome: 'Aurora', usuario: 'Visitante', variantes: ['aurora'], ponte_url: '', atualizacao_ao_abrir: false };
        if (cmd === 'ler_habilidades') return structuredClone(window.__oficina);
        if (cmd === 'gravar_habilidades') { window.__oficina = structuredClone(args.valor); return; }
        if (cmd === 'listar_monitores' || cmd === 'falhas_de_atalho') return [];
        if (cmd.startsWith('plugin:')) return ++proximo;
        return null;
      },
      transformCallback: cb => { const id = ++proximo; window['_' + id] = cb; return id; },
      unregisterCallback: () => {},
      convertFileSrc: p => p,
      metadata: { currentWindow: { label: 'configuracoes' }, currentWebview: { label: 'configuracoes', windowLabel: 'configuracoes' } },
    };
    window.fetch = async (entrada) => {
      const url = String(entrada);
      const dados = url.includes('/recursos') ? { componentes: [], externos: [], total_memoria_mb: 0, total_cpu_percent: 0 } : url.includes('/primeiro-uso') ? { schema: 1, etapa: 'resumo', concluido: true, pendencias: [] } : url.includes('/models') ? { data: [] } : {};
      return new Response(JSON.stringify(dados), { status: 200, headers: { 'Content-Type': 'application/json' } });
    };
  ` });
  await canal.enviar("Page.navigate", { url: `http://127.0.0.1:${porta}/configuracoes.html` });
  await esperar("!!document.querySelector('nav button[data-aba=oficina]') && !!document.querySelector('#oficina-habilidades')");
  await clicar("Oficina", "document.querySelector('nav')");
  await esperar("!document.querySelector('.oficina-filtros button').disabled");
  assert.equal(await canal.avaliar("document.querySelector('#cfg-titulo-secao').textContent"), "Oficina");
  await capturar("oficina-fabrica");
  await clicar("Nova habilidade");
  await esperar("!!document.querySelector('[role=dialog]')");
  assert.deepEqual(await canal.avaliar("[...document.querySelectorAll('.modal input:not([type=checkbox]), .modal textarea')].map(c => c.maxLength)"), [80, 2009, 4000]);
  await canal.avaliar(`(() => {
    const campos = document.querySelectorAll('.modal input:not([type=checkbox]), .modal textarea');
    campos[0].value = 'Planejar'; campos[1].value = 'bom dia'; campos[2].value = 'a'.repeat(4001);
    campos[2].dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await clicar("Salvar", "document.querySelector('[role=dialog]')");
  await esperar("document.querySelector('[role=dialog]')?.textContent.includes('Instruções devem ter até 4000 caracteres')");
  assert.equal(await canal.avaliar("window.__oficina.habilidades.length"), 0);
  await canal.avaliar(`(() => {
    const campos = document.querySelectorAll('.modal input:not([type=checkbox]), .modal textarea');
    campos[0].value = 'Planejar o dia'; campos[1].value = 'bom dia\\nvamos começar o dia';
    campos[2].value = '1. Consultar a agenda.\\n2. Resumir os compromissos.\\n' + '3. Confirmar a próxima tarefa.\\n'.repeat(20);
    campos[2].dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  assert.ok(await canal.avaliar("document.querySelector('[role=dialog]').textContent.includes(document.querySelectorAll('.modal textarea')[1].value.length + '/4000 caracteres')"));
  await capturar("oficina-cadastro-modal");
  await clicar("Salvar", "document.querySelector('[role=dialog]')");
  await esperar("window.__oficina.habilidades.length === 1 && !document.querySelector('[role=dialog]')");
  const id = await canal.avaliar("window.__oficina.habilidades[0].id");
  const card = `document.querySelector('[data-id=${id}]')`;
  await clicar("Editar", card);
  await canal.avaliar("document.querySelector('.modal input:not([type=checkbox])').value = 'Planejar o dia com calma'");
  await capturar("oficina-edicao-modal");
  await clicar("Salvar", "document.querySelector('[role=dialog]')");
  await esperar("window.__oficina.habilidades[0].nome === 'Planejar o dia com calma' && !document.querySelector('[role=dialog]')");
  await clicar("Marcar como validada", card);
  await esperar("window.__oficina.habilidades[0].situacao === 'validada'");
  await capturar("oficina-validada");
  await clicar("Excluir", card); await capturar("oficina-exclusao-modal");
  await clicar("Cancelar", "document.querySelector('[role=dialog]')");
  assert.equal(await canal.avaliar("window.__oficina.habilidades.length"), 1);
  await clicar("Excluir", card); await clicar("Excluir habilidade", "document.querySelector('[role=dialog]')");
  await esperar("window.__oficina.habilidades.length === 0 && !document.querySelector('[role=dialog]')");
  await clicar("Desligar", "document.querySelector('[data-id=computador]')");
  await esperar("window.__oficina.desligadas.includes('computador')");
  console.log("CRUD, confirmação, validação e liga/desliga aprovados por CDP.");
  await writeFile(path.join(saida, "medidas.json"), JSON.stringify({ inicio, medidas }, null, 2));
  console.log(JSON.stringify({ capturas: medidas.length, vazamentosHorizontais: medidas.flatMap((m) => m.vazamentos).length }));
} finally {
  if (canal) {
    canal.ws.send(JSON.stringify({ id: ++canal.proximo, method: "Browser.close" }));
    canal.ws.close();
  }
  if (navegador) {
    const encerrado = () => navegador.exitCode !== null || navegador.signalCode !== null;
    for (let i = 0; i < 50 && !encerrado(); i++) await pausa(100);
    if (!encerrado()) { navegador.kill(); await once(navegador, "exit"); }
    console.log(JSON.stringify({ processo: path.basename(executavel), pid: navegador.pid, encerrado: true }));
  }
  await servidor?.close();
  // Diretório exclusivo criado por esta prova; não aceita caminho fornecido como alvo de remoção.
  assert.equal(path.dirname(perfil), saida);
  await rm(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  console.log("Vite fechado e perfil temporário removido.");
}
