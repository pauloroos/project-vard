// Prova CDP do assistente de primeiro uso (0.9 T2b/T2c).
// Segue o modelo de um-app-so.mjs: abre app em dev com WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS,
// conecta por CDP, valida cenários A (config vazia → abre) e B (config usada → não abre; botão reabre).
import { spawn, execSync } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(__dirname, "..", "..");
const PROVA_DIR = path.join(RAIZ, ".coordenacao", "0.9-prova", "t2b");
const RESULTADO_PATH = path.join(RAIZ, ".coordenacao", "0.9-prova", "t2b.json");
const CAPTURAS_DIR = path.join(PROVA_DIR, "capturas");

// Portas livres (evita 4700/8000/1234/4710/4720 da instalação real)
const PORTA_OJ = 28765;
const PORTA_PONTE = 24700;
const PORTA_VOZ = 24710;
const PORTA_NUCLEO = 24750;
const PORTA_CDP = 29222;
const PORTA_VITE = 25173;

const resultado = {
  data: new Date().toISOString(),
  versao: "0.9.0",
  cenarios: {},
  processos: { abertos: [], fechados: [] },
  logs: [],
};

function log(msg) {
  const l = `[${new Date().toISOString()}] ${msg}`;
  resultado.logs.push(l);
  console.log(l);
}

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

// Harness mínimo para primeiro uso: núcleo responde /primeiro-uso e /saude
let estadoPrimeiroUso = { schema: 1, etapa: "importar", concluido: false, pendencias: [] };
const hNucleo = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/saude") return j({ status: "ok" });
  if (req.url === "/status") return j({ modo: "ligado" });
  if (req.method === "GET" && req.url === "/primeiro-uso") return j(estadoPrimeiroUso);
  if (req.method === "PUT" && req.url === "/primeiro-uso") {
    let b = ""; req.on("data", c => b += c);
    req.on("end", () => {
      try {
        const patch = JSON.parse(b);
        for (const [k, v] of Object.entries(patch)) {
          if (k in estadoPrimeiroUso) estadoPrimeiroUso[k] = v;
        }
        j(estadoPrimeiroUso);
      } catch { j({ erro: "json_invalido" }, 400); }
    });
    return;
  }
  if (req.method === "POST" && req.url === "/primeiro-uso/reabrir") {
    estadoPrimeiroUso.concluido = false;
    return j(estadoPrimeiroUso);
  }
  j({}, 404);
};

const hOJ = (req, res) => {
  const j = (o, s = 200) => { res.writeHead(s, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
  if (req.url === "/health") return j({ status: "ok" });
  if (req.method === "POST" && req.url === "/transcrever") {
    let b = ""; req.on("data", c => b += c);
    req.on("end", () => j({ texto: "frase de teste" }));
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

async function cdpScreenshot(ws, filename) {
  const r = await cdpSend(ws, "Page.captureScreenshot", { format: "png" });
  const buf = Buffer.from(r.data, "base64");
  const p = path.join(CAPTURAS_DIR, filename);
  fs.writeFileSync(p, buf);
  log(`captura: ${p}`);
  return p;
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

function prepararAmbienteTeste(cenario) {
  const tmpBase = path.join(process.env.TEMP || "/tmp", `vard-test-${cenario}-${Date.now()}`);
  const configDir = path.join(tmpBase, "config");
  const dadosDir = path.join(tmpBase, "dados");
  // Tauri dev usa APPDATA/io.github.pauloroos.vard.dev/ (identifier de dev)
  const appdataDevDir = path.join(tmpBase, "appdata", "io.github.pauloroos.vard.dev");
  fs.mkdirSync(configDir, { recursive: true });
  fs.mkdirSync(dadosDir, { recursive: true });
  fs.mkdirSync(appdataDevDir, { recursive: true });

  // Configura ponte_url para apontar para o núcleo falso
  const hudConfig = { ponte_url: `http://127.0.0.1:${PORTA_NUCLEO}` };
  // Cenário B: hud.config.json com nome fictício → instalação existente
  if (cenario === "B") {
    hudConfig.nome = "Aurora";
  }
  fs.writeFileSync(path.join(appdataDevDir, "hud.config.json"), JSON.stringify(hudConfig));
  return { configDir, dadosDir, appdataDir: path.dirname(appdataDevDir) };
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
  resultado.processos.fechados.push(...listarVardPids());
}

async function rodarCenario(nome, cenario) {
  log(`=== Cenário ${nome} ===`);
  estadoPrimeiroUso = { schema: 1, etapa: "importar", concluido: false, pendencias: [] };
  const dirs = prepararAmbienteTeste(cenario);
  const env = {
    ...process.env,
    VARD_CONFIG: dirs.configDir,
    VARD_DADOS: dirs.dadosDir,
    APPDATA: path.dirname(dirs.appdataDir),
    LOCALAPPDATA: path.dirname(dirs.appdataDir),
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${PORTA_CDP}`,
    WEBVIEW2_USER_DATA_FOLDER: path.join(dirs.dadosDir, "wv2"),
    VITE_OJ_ALVO: `http://127.0.0.1:${PORTA_OJ}`,
  };
  const srvs = [
    await criarSrv("nuc", PORTA_NUCLEO, hNucleo),
    await criarSrv("voz", PORTA_VOZ, hVoz),
    await criarSrv("oj", PORTA_OJ, hOJ),
  ];
  const app = spawn("npm.cmd", ["run", "tauri:dev"], { cwd: RAIZ, env, stdio: ["ignore", "pipe", "pipe"], shell: true });
  resultado.processos.abertos.push({ pid: app.pid, cenario: nome });
  log(`app pid ${app.pid}`);
  if (!(await aguardarPorta(PORTA_CDP, 180000))) {
    log("CDP timeout");
    await limpar(app, srvs);
    return { ok: false, erro: "CDP timeout" };
  }
  let ws;
  try { ws = await conectarCdp(); } catch (e) {
    log(`CDP erro: ${e.message}`);
    await limpar(app, srvs);
    return { ok: false, erro: e.message };
  }
  const res = {};
  try {
    await new Promise(r => setTimeout(r, 3000));
    const temAssistente = await cdpEval(ws, "!!document.querySelector('#primeiro-uso-etapa')");
    res.assistente_abriu = !!temAssistente;
    await cdpScreenshot(ws, `cenario-${nome}-inicio.png`);
    if (cenario === "A" && temAssistente) {
      // Percorre etapas até resumo
      for (let i = 0; i < 7; i++) {
        const btn = await cdpEval(ws, "document.querySelector('#primeiro-uso-proximo')?.click() || 'ok'");
        await new Promise(r => setTimeout(r, 500));
        await cdpScreenshot(ws, `cenario-${nome}-etapa-${i}.png`);
      }
      const concluido = await cdpEval(ws, "document.querySelector('#primeiro-uso-resumo')?.textContent || ''");
      res.concluido_texto = concluido;
    }
    if (cenario === "B") {
      // Dispara evento reabrir via API dev
      await cdpEval(ws, "window.__TAURI__?.event?.emit('reabrir-primeiro-uso')");
      await new Promise(r => setTimeout(r, 1000));
      const reaberto = await cdpEval(ws, "!!document.querySelector('#primeiro-uso-etapa')");
      res.reabriu_via_evento = !!reaberto;
      await cdpScreenshot(ws, `cenario-${nome}-reaberto.png`);
    }
    res.ok = cenario === "A" ? res.assistente_abriu : !res.assistente_abriu && res.reabriu_via_evento;
  } catch (e) {
    res.ok = false;
    res.erro = e.message;
  }
  await limpar(app, srvs);
  return res;
}

async function main() {
  log("=== Prova Primeiro Uso T2b ===");
  fs.mkdirSync(CAPTURAS_DIR, { recursive: true });
  const pidsAntes = listarVardPids();
  if (pidsAntes.length) {
    log(`AVISO: vard.exe já rodando: ${pidsAntes}`);
  }
  resultado.cenarios.A = await rodarCenario("A", "A");
  resultado.cenarios.B = await rodarCenario("B", "B");
  fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2));
  log(`Resultado: ${RESULTADO_PATH}`);
  log(`A: ${resultado.cenarios.A.ok}, B: ${resultado.cenarios.B.ok}`);
}

main().catch(e => { log(`FATAL: ${e.message}`); process.exit(1); });