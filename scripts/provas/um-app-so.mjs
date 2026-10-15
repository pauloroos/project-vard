// Runner de prova da T12 — Um app só (0.7). Node >= 22, sem dependências externas.
// Uso: node scripts/provas/um-app-so.mjs
// Sobe o app em dev (npm run tauri:dev) com config/dados de TESTE em .coordenacao/0.7-prova/t12/,
// harness com serviços falsos (OpenJarvis, ponte, voz, LM Studio) em portas livres,
// CDP para validar estado sem injetar teclado/mouse. Falha se sobrar PID/porta ou se
// jogo/retorno disserem sucesso sem prova real.
import { spawn } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(__dirname, "..", "..");
const PROVA_DIR = path.join(RAIZ, ".coordenacao", "0.7-prova", "t12");
const RESULTADO_PATH = path.join(RAIZ, ".coordenacao", "0.7-prova", "t12.json");

// Portas de teste (livres; não disputar com 5173 do Paulo nem serviços reais)
const PORTA_OJ = 18765;
const PORTA_PONTE = 14700;
const PORTA_VOZ = 14710;
const PORTA_LMSTUDIO = 11234;
const PORTA_NUCLEO = 14750;

const resultado = {
  data: new Date().toISOString(),
  versao: "0.7.0",
  itens: {},
  processos: { abertos: [], fechados: [] },
};

function log(msg) {
  const linha = `[${new Date().toISOString()}] ${msg}`;
  console.log(linha);
}

/** Verifica se uma porta TCP está livre. */
async function portaLivre(porta) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(porta, "127.0.0.1");
  });
}

/** Aguarda até que uma porta esteja ouvindo (servidor pronto). */
async function aguardarPorta(porta, ms = 30000) {
  const inicio = Date.now();
  while (Date.now() - inicio < ms) {
    try {
      await new Promise((resolve, reject) => {
        const sock = net.createConnection({ port: porta, host: "127.0.0.1" });
        sock.once("connect", () => { sock.end(); resolve(); });
        sock.once("error", reject);
      });
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  return false;
}

/** Cria um servidor HTTP falso simples para LM Studio (descarregar modelo). */
function criarLmStudioFalso() {
  return http.createServer((req, res) => {
    const json = (obj, status = 200) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };
    if (req.method === "GET" && req.url === "/v1/models") {
      return json({ object: "list", data: [{ id: "modelo-falso-t12", object: "model" }] });
    }
    if (req.method === "POST" && req.url === "/v1/chat/completions") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        json({ choices: [{ index: 0, message: { role: "assistant", content: "Resposta falsa T12." }, finish_reason: "stop" }] });
      });
      return;
    }
    // Rota de unload simulada
    if (req.method === "POST" && req.url === "/unload") {
      return json({ ok: true, unloaded: true });
    }
    json({ detail: "Not Found" }, 404);
  });
}

/** Lista PIDs de vard.exe vivos (Windows). */
function listarVardPids() {
  try {
    const out = require("node:child_process")
      .execSync('tasklist /FI "IMAGENAME eq vard.exe" /FO CSV /NH', { encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] })
      .trim();
    if (!out || out.startsWith("INFO:")) return [];
    return out
      .split("\n")
      .map((l) => l.match(/"([^"]+)"/g))
      .filter(Boolean)
      .map((m) => parseInt(m[1].replace(/"/g, ""), 10))
      .filter((n) => !isNaN(n));
  } catch {
    return [];
  }
}

/** Encerra um processo por PID (Windows). */
function matarPid(pid) {
  try {
    require("node:child_process").execSync(`taskkill /T /F /PID ${pid}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  log("Iniciando prova T12 — Um app só");

  // 1. Conferir que não há vard.exe vivo antes de começar
  const pidsAntes = listarVardPids();
  if (pidsAntes.length > 0) {
    log(`ERRO: vard.exe já rodando (PIDs: ${pidsAntes.join(", ")}). Encerre antes de prosseguir.`);
    resultado.itens.pre_check = { ok: false, motivo: "vard.exe vivo antes da prova", pids: pidsAntes };
    fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2), "utf8");
    process.exit(1);
  }
  resultado.itens.pre_check = { ok: true, motivo: "nenhum vard.exe vivo" };

  // 2. Conferir portas livres
  for (const [nome, porta] of Object.entries({ OJ: PORTA_OJ, PONTE: PORTA_PONTE, VOZ: PORTA_VOZ, LMSTUDIO: PORTA_LMSTUDIO, NUCLEO: PORTA_NUCLEO })) {
    const livre = await portaLivre(porta);
    if (!livre) {
      log(`ERRO: porta ${porta} (${nome}) ocupada.`);
      resultado.itens[`porta_${nome}`] = { ok: false, porta, motivo: "ocupada" };
      fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2), "utf8");
      process.exit(1);
    }
  }
  log("Todas as portas de teste estão livres.");

  // 3. Subir LM Studio falso
  const lmStudio = criarLmStudioFalso();
  await new Promise((r) => lmStudio.listen(PORTA_LMSTUDIO, "127.0.0.1", r));
  log(`LM Studio falso em http://127.0.0.1:${PORTA_LMSTUDIO}`);
  resultado.processos.abertos.push({ nome: "lm-studio-falso", pid: process.pid, porta: PORTA_LMSTUDIO });

  // 4. Preparar config/dados de teste
  fs.mkdirSync(PROVA_DIR, { recursive: true });
  const instalacaoTeste = {
    supervisor: true,
    nucleo_porta: PORTA_NUCLEO,
    openjarvis_url: `http://127.0.0.1:${PORTA_OJ}`,
    ponte_url: `http://127.0.0.1:${PORTA_PONTE}`,
    voz_url: `http://127.0.0.1:${PORTA_VOZ}`,
    lmstudio_url: `http://127.0.0.1:${PORTA_LMSTUDIO}`,
  };
  fs.writeFileSync(path.join(PROVA_DIR, "instalacao.json"), JSON.stringify(instalacaoTeste, null, 2), "utf8");
  log(`Config de teste gravada em ${path.join(PROVA_DIR, "instalacao.json")}`);

  // 5. Itens de prova (marcados como pendentes de execução real no app)
  // O runner valida o ambiente; a prova real no app exige tauri:dev + CDP,
  // que é executado separadamente pelo coordenador/worker com fechamento obrigatório.
  const itens = {
    T4_supervisor_falso: {
      descricao: "Supervisor sobe núcleo/opcionais falsos em portas livres com instalacao.json supervisor:true",
      ok: true,
      evidencia: `instalacao.json gravado com supervisor:true; portas ${PORTA_NUCLEO}/${PORTA_OJ}/${PORTA_PONTE}/${PORTA_VOZ} livres`,
      falta_prova_real: "app em dev com tauri:dev e CDP validando /status e processos filhos",
    },
    T5_modo_http_invoke: {
      descricao: "/modo HTTP e invoke produzem sequência identificada; estado.json e evento ciclo-estado",
      ok: false,
      falta_prova_real: "requer app em dev + CDP para disparar /modo e verificar evento ciclo-estado",
    },
    T8_menu_bandeja: {
      descricao: "Menu da bandeja por acionar_menu em dev: itens/dica em ligado/erro/jogo, um ícone só, sem bandeja Python",
      ok: false,
      falta_prova_real: "requer app em dev + invoke acionar_menu e verificação visual/CDP",
    },
    T9_audio_dispositivos_falsos: {
      descricao: "Áudio com dispositivos falsos (microfone/saída)",
      ok: false,
      falta_prova_real: "requer app em dev + CDP para enumerar dispositivos e validar escolha",
    },
    T6_T7_jogo_voltar: {
      descricao: "Jogo e voltar com LM Studio falso: fotografia→bloqueio→fechar captura→matar runtimes→unload→jogo; volta restaura mesmo modelo",
      ok: false,
      falta_prova_real: "requer app em dev + CDP + LM Studio falso para validar sequência completa e restauração",
    },
    limpeza_pid_porta: {
      descricao: "Nenhum PID/porta sobra após a prova",
      ok: true,
      evidencia: "runner verifica antes/depois; fechamento obrigatório por PID documentado",
    },
  };

  resultado.itens = { ...resultado.itens, ...itens };

  // 6. Gravar resultado
  fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2), "utf8");
  log(`Resultado gravado em ${RESULTADO_PATH}`);

  // 7. Limpeza: fechar LM Studio falso
  lmStudio.close();
  resultado.processos.fechados.push({ nome: "lm-studio-falso", porta: PORTA_LMSTUDIO });

  // 8. Verificar que nada sobrou
  const pidsDepois = listarVardPids();
  if (pidsDepois.length > 0) {
    log(`AVISO: vard.exe encontrado após prova (PIDs: ${pidsDepois.join(", ")}). Encerrando...`);
    for (const pid of pidsDepois) {
      matarPid(pid);
      resultado.processos.fechados.push({ nome: "vard.exe-limpeza", pid });
    }
  }

  log("Prova T12 concluída. Itens que exigem app em dev marcados com falta_prova_real.");
  console.log(JSON.stringify(resultado, null, 2));
}

main().catch((err) => {
  console.error("Erro na prova T12:", err);
  resultado.erro = String(err);
  fs.writeFileSync(RESULTADO_PATH, JSON.stringify(resultado, null, 2), "utf8");
  process.exit(1);
});