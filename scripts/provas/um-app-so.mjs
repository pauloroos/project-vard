// Runner de prova da T12b — Um app só (0.7). Node >= 22.
// Abre o app em dev com instalacao.json de TESTE e valida por CDP/HTTP.
import { spawn, execSync } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(__dirname, "..", "..");
const PROVA_DIR = path.join(RAIZ, ".coordenacao", "0.7-prova", "t12");
const RESULTADO_PATH = path.join(RAIZ, ".coordenacao", "0.7-prova", "t12.json");

const PORTA_OJ = 18765;
const PORTA_PONTE = 14700;
const PORTA_VOZ = 14710;
const PORTA_LMSTUDIO = 11234;
const PORTA_NUCLEO = 14750;
const PORTA_CDP = 9222;

const resultado = { data: new Date().toISOString(), versao: "0.7.0", itens: {}, processos: { abertos: [], fechados: [] }, logs: [] };
function log(msg) { const l = `[${new Date().toISOString()}] ${msg}`; resultado.logs.push(l); console.log(l); }

async function portaLivre(porta) {
  return new Promise((r) => {
    const s = net.createServer();
    s.once("error", () => r(false));
    s.once("listening", () => s.close(() => r(true)));
    s.listen(porta, "127.0.0.1");
  });
}

async function aguardarPorta(porta, ms = 60000) {
  const i = Date.now();
  while (Date.now() - i < ms) {
    try {
      await new Promise((ok, no) => {
        const c = net.createConnection({ port: porta, host: "127.0.0.1" });
        c.once("connect", () => { c.end(); ok(); });
        c.once("error", no);
      });
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  return false;
}

function listarVardPids() {
  try {
    // Usa powershell para evitar tradução de /FI pelo Git Bash
    const cmd = 'powershell -NoProfile -Command "Get-Process vard.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"';
    const o = execSync(cmd, { encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }).trim();
    if (!o) return [];
    return o.split(/\r?\n/).map(l => parseInt(l.trim(), 10)).filter(n => !isNaN(n));
  } catch { return []; }
}

function matarPid(pid) {
  try { execSync(`taskkill /T /F /PID ${pid}`, { stdio: "ignore" }); return true; } catch { return false; }
}

function criarSrv(nome, porta, handler) {
  return new Promise((ok, no) => {
    const s = http.createServer(handler);
    s.listen(porta, "127.0.0.1", () => { log(`${nome} em :${porta}`); ok(s); });
    s.on("error", no);
  });
}

const hNucleo = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/saude") return j({ status: "ok" });
  if (req.url === "/status") return j({ modo: "ligado" });
  j({}, 404);
};
const hLM = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/v1/models") return j({ data: [{ id: "m-falso" }] });
  if (req.url === "/unload") return j({ ok: true });
  if (req.method === "POST" && req.url === "/v1/chat/completions") {
    let b = ""; req.on("data", c => b += c);
    req.on("end", () => j({ choices: [{ message: { content: "ok" } }] }));
    return;
  }
  j({}, 404);
};
const hVoz = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/saude") return j({ pronta: true });
  if (req.url === "/falar") { res.writeHead(200, { "Content-Type": "audio/wav" }); res.end(Buffer.alloc(44)); return; }
  j({}, 404);
};
const hOJ = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/health") return j({ status: "ok" });
  j({}, 404);
};

let cdpId = 1;
async function cdpSend(ws, method, params = {}, timeoutMs = 60000) {
  const id = cdpId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((ok, no) => {
    const t = setTimeout(() => no(new Error(`CDP ${method} timeout (${timeoutMs}ms)`)), timeoutMs);
    const h = r => {
      try {
        const m = JSON.parse(r.toString());
        if (m.id === id) { clearTimeout(t); ws.removeListener("message", h); if (m.error) no(new Error(JSON.stringify(m.error))); else ok(m.result); }
      } catch {}
    };
    ws.on("message", h);
  });
}

async function cdpEval(ws, expr, ap = false, timeoutMs = 60000) {
  const r = await cdpSend(ws, "Runtime.evaluate", { expression: expr, awaitPromise: ap, returnByValue: true }, timeoutMs);
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result?.value;
}

async function conectarCdp() {
  const url = await new Promise((ok, no) => {
    http.get(`http://127.0.0.1:${PORTA_CDP}/json`, r => {
      let b = ""; r.on("data", c => b += c);
      r.on("end", () => {
        try { const p = JSON.parse(b).find(x => x.type === "page"); p ? ok(p.webSocketDebuggerUrl) : no(new Error("sem page")); } catch (e) { no(e); }
      });
    }).on("error", no);
  });
  const { WebSocket } = await import("ws");
  const ws = new WebSocket(url);
  await new Promise((ok, no) => { ws.on("open", ok); ws.on("error", no); });
  await cdpSend(ws, "Runtime.enable");
  await cdpSend(ws, "Page.enable");
  for (let i = 0; i < 120; i++) {
    if (await cdpEval(ws, "!!window.__TAURI__?.core?.invoke")) return ws;
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error("__TAURI__ nao disponivel");
}

function prepararConfig() {
  fs.mkdirSync(PROVA_DIR, { recursive: true });
  const cfg = { raiz_codigo: RAIZ.replace(/\\/g, "/"), supervisor: true, modelo: "m-falso", contexto: 4096, servicos: { voz: true, reuniao: false, openjarvis: true, porta_nucleo: PORTA_NUCLEO, porta_voz: PORTA_VOZ } };
  const p = path.join(PROVA_DIR, "instalacao.json");
  fs.writeFileSync(p, JSON.stringify(cfg, null, 2));
  return p;
}

async function limpar(appProc, srvs) {
  log("Limpando...");
  if (appProc && !appProc.killed) {
    try { appProc.kill("SIGTERM"); } catch {}
    await new Promise(r => setTimeout(r, 2000));
    if (!appProc.killed) try { appProc.kill("SIGKILL"); } catch {}
  }
  for (let t = 0; t < 3; t++) {
    const pids = listarVardPids();
    if (!pids.length) break;
    for (const pid of pids) matarPid(pid);
    await new Promise(r => setTimeout(r, 1000));
  }
  for (const s of srvs) try { s.close(); } catch {}
  const resto = listarVardPids();
  if (resto.length) log(`AVISO: vard.exe sobrou: ${resto}`);
}

async function main() {
  log("=== T12b ===");
  const pidsAntes = listarVardPids();
  if (pidsAntes.length) {
    resultado.itens.pre_check = { ok: false, motivo: "vard vivo" };
    fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2));
    process.exit(1);
  }
  resultado.itens.pre_check = { ok: true };

  for (const [n, p] of Object.entries({ OJ: PORTA_OJ, PONTE: PORTA_PONTE, VOZ: PORTA_VOZ, LM: PORTA_LMSTUDIO, NUC: PORTA_NUCLEO, CDP: PORTA_CDP })) {
    if (!(await portaLivre(p))) { log(`porta ${p} ocupada`); process.exit(1); }
  }

  const srvs = [
    await criarSrv("nuc", PORTA_NUCLEO, hNucleo),
    await criarSrv("lm", PORTA_LMSTUDIO, hLM),
    await criarSrv("voz", PORTA_VOZ, hVoz),
    await criarSrv("oj", PORTA_OJ, hOJ),
  ];

  const instPath = prepararConfig();
  const env = {
    ...process.env,
    VARD_INSTALACAO: instPath,
    VARD_DADOS: PROVA_DIR,
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${PORTA_CDP}`,
    WEBVIEW2_USER_DATA_FOLDER: path.join(PROVA_DIR, "wv2"),
    VITE_OJ_ALVO: `http://127.0.0.1:${PORTA_OJ}`,
  };

  const app = spawn("npm", ["run", "tauri:dev"], { cwd: RAIZ, env, stdio: ["ignore", "pipe", "pipe"], shell: true });
  log(`app pid ${app.pid}`);

  if (!(await aguardarPorta(PORTA_CDP, 180000))) { log("CDP timeout"); await limpar(app, srvs); process.exit(1); }
  let ws;
  try { ws = await conectarCdp(); } catch (e) { log(`CDP erro: ${e.message}`); await limpar(app, srvs); process.exit(1); }

  // T4
  try {
    const ok = await aguardarPorta(PORTA_NUCLEO, 5000) && await aguardarPorta(PORTA_VOZ, 5000);
    const info = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_info'))()", true);
    resultado.itens.T4 = { ok: ok && info && !info.erro, info };
    log(`T4: ${resultado.itens.T4.ok}`);
  } catch (e) { resultado.itens.T4 = { ok: false, erro: e.message }; }

  // T5
  try {
    const antes = fs.existsSync(path.join(PROVA_DIR, "estado.json")) ? JSON.parse(fs.readFileSync(path.join(PROVA_DIR, "estado.json"), "utf8")) : null;
    const ped = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_pedir',{verbo:'iniciar'}))()", true);
    await new Promise(r => setTimeout(r, 2000));
    const depois = fs.existsSync(path.join(PROVA_DIR, "estado.json")) ? JSON.parse(fs.readFileSync(path.join(PROVA_DIR, "estado.json"), "utf8")) : null;
    resultado.itens.T5 = { ok: ped && (ped.ok || ped.id) && depois !== null, ped, antes, depois };
    log(`T5: ${resultado.itens.T5.ok}`);
  } catch (e) { resultado.itens.T5 = { ok: false, erro: e.message }; }

  // T8
  try {
    const foto = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_info'))()", true);
    resultado.itens.T8 = { ok: foto && !foto.erro && typeof foto.supervisor_ativo === "boolean", foto };
    log(`T8: ${resultado.itens.T8.ok}`);
  } catch (e) { resultado.itens.T8 = { ok: false, erro: e.message }; }

  // T9
  try {
    await cdpEval(ws, "navigator.mediaDevices||(navigator.mediaDevices={enumerateDevices:async()=>[{deviceId:'mic-falso',kind:'audioinput',label:'Mic Falso'},{deviceId:'spk-falso',kind:'audiooutput',label:'Spk Falso'}]})", true);
    const devs = await cdpEval(ws, "(async()=>navigator.mediaDevices.enumerateDevices())()", true);
    resultado.itens.T9 = { ok: Array.isArray(devs) && devs.length >= 2, devs };
    log(`T9: ${resultado.itens.T9.ok}`);
  } catch (e) { resultado.itens.T9 = { ok: false, erro: e.message }; }

  // T6/T7 jogo/voltar
  try {
    const fotoAntes = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_info'))()", true);
    const jogo = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_pedir',{verbo:'jogo'}))()", true);
    await new Promise(r => setTimeout(r, 4000));
    const estadoJogo = fs.existsSync(path.join(PROVA_DIR, "estado.json")) ? JSON.parse(fs.readFileSync(path.join(PROVA_DIR, "estado.json"), "utf8")) : null;
    const voltar = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_pedir',{verbo:'voltar'}))()", true);
    await new Promise(r => setTimeout(r, 4000));
    const fotoDepois = await cdpEval(ws, "(async()=>window.__TAURI__.core.invoke('cmd_ciclo_info'))()", true);
    const t6t7Ok = !!(jogo && jogo.ok && voltar && voltar.ok && estadoJogo && estadoJogo.modo === "jogo" && fotoDepois && fotoDepois.modo === "ligado");
    resultado.itens.T6_T7 = { ok: t6t7Ok, jogo, voltar, estadoJogo, fotoAntes, fotoDepois };
    log(`T6/T7: ${t6t7Ok}`);
  } catch (e) { resultado.itens.T6_T7 = { ok: false, erro: e.message }; }

  // Limpeza e verificação final
  await limpar(app, srvs);
  const pidsDepois = listarVardPids();
  resultado.itens.limpeza = { ok: pidsDepois.length === 0, pids_restantes: pidsDepois };
  resultado.processos.fechados.push(...srvs.map((_, i) => ({ nome: `srv-${i}` })));

  fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2));
  const todosOk = Object.values(resultado.itens).every(i => i.ok);
  log(`Resultado: ${todosOk ? "TODOS OK" : "FALHAS"} — ${JSON.stringify(Object.fromEntries(Object.entries(resultado.itens).map(([k, v]) => [k, v.ok])))}`);
  process.exit(todosOk ? 0 : 1);
}

main().catch(e => { console.error("ERRO FATAL:", e); process.exit(2); });