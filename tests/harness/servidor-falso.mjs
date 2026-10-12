// Servidor falso do OpenJarvis para provar o ciclo sem voz humana. Node >= 20, sem dependências.
// Uso: npm run harness  (porta 8765; mude com PORTA=...). Aponte o HUD para ele com VITE_OJ_ALVO.
import http from "node:http";
import { pathToFileURL } from "node:url";

/** WAV PCM 16 bits mono com uma senoide de `segundos` segundos. */
export function senoideWav(segundos = 0.3, freq = 440, taxa = 22050) {
  const n = Math.floor(segundos * taxa);
  const buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(taxa, 24); buf.writeUInt32LE(taxa * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(Math.sin((2 * Math.PI * freq * i) / taxa) * 0.4 * 32767), 44 + i * 2);
  return buf;
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function lerCorpo(req) {
  return new Promise((resolve) => {
    const partes = [];
    req.on("data", (c) => partes.push(c));
    req.on("end", () => resolve(Buffer.concat(partes)));
  });
}

export function criarServidor({ log = () => {} } = {}) {
  return http.createServer(async (req, res) => {
    const caminho = new URL(req.url, "http://x").pathname;
    const json = (obj, status = 200) => {
      res.writeHead(status, { "Content-Type": "application/json", ...CORS });
      res.end(JSON.stringify(obj));
    };
    log(req.method, caminho);
    if (req.method === "OPTIONS") { res.writeHead(204, CORS); res.end(); return; }
    if (caminho === "/health") return json({ status: "ok" });
    if (caminho === "/v1/speech/health") return json({ available: true, backend: "harness" });
    if (caminho === "/v1/models") return json({ object: "list", data: [{ id: "modelo-falso", object: "model" }] });
    if (req.method === "POST" && caminho === "/v1/speech/transcribe") {
      await lerCorpo(req);
      const texto = req.headers["x-texto-falso"];
      return json({ text: typeof texto === "string" && texto ? texto : "Vard, que horas são", language: "pt" });
    }
    if (req.method === "POST" && caminho === "/v1/chat/completions") {
      const corpo = JSON.parse((await lerCorpo(req)).toString("utf8") || "{}");
      if (corpo.tools) return json({ error: "o harness não aceita tools (caminho do agente)" }, 400);
      return json({ choices: [{ index: 0, message: { role: "assistant", content: "Agora são 13h." }, finish_reason: "stop" }] });
    }
    if (req.method === "POST" && caminho === "/v1/speech/synthesize") {
      await lerCorpo(req);
      res.writeHead(200, { "Content-Type": "audio/wav", ...CORS });
      res.end(senoideWav());
      return;
    }
    json({ detail: "Not Found" }, 404);
  });
}

/** Ponte falsa do Vard (porta 4700 no uso real): /status, /see, /modo e /events. Guarda a origem e o modo em `estado`. */
export function criarPonteFalsa({ estado = { modo: "ligado", pedidos: [] } } = {}) {
  const srv = http.createServer(async (req, res) => {
    const caminho = new URL(req.url, "http://x").pathname;
    const origem = req.headers.origin;
    const cors = { ...CORS, ...(origem ? { "Access-Control-Allow-Origin": origem } : {}) };
    const json = (obj, status = 200) => { res.writeHead(status, { "Content-Type": "application/json", ...cors }); res.end(JSON.stringify(obj)); };
    if (req.method === "OPTIONS") { res.writeHead(204, cors); res.end(); return; }
    if (caminho === "/status") return json({ openjarvis: true, lmstudio: true, modelo: "falso", modo: estado.modo });
    if (req.method === "POST" && caminho === "/see") {
      const corpo = await lerCorpo(req);
      estado.pedidos.push({ caminho, bytes: corpo.length, jpeg: corpo.includes(Buffer.from([0xff, 0xd8])) });
      if (estado.erroVer) return json({ erro: estado.erroVer }, 503);
      return json({ resposta: "Um editor de código aberto.", nuvem: false });
    }
    if (req.method === "POST" && caminho === "/modo") {
      const { modo } = JSON.parse((await lerCorpo(req)).toString("utf8") || "{}");
      estado.pedidos.push({ caminho, modo, origem });
      if (modo === "jogo") estado.modo = "jogo";
      if (modo === "voltar") estado.modo = "ligado";
      return json({ ok: true, pid: 1 });
    }
    if (caminho === "/events") {
      res.writeHead(200, { "Content-Type": "text/event-stream", ...cors });
      res.write(["event: ping", "data: {}", "", ""].join(String.fromCharCode(10)));
      return;
    }
    json({ detail: "Not Found" }, 404);
  });
  srv.estado = estado;
  return srv;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const porta = Number(process.env.PORTA ?? 8765);
  if (process.env.PONTE) criarPonteFalsa().listen(Number(process.env.PONTE), "127.0.0.1", () => console.log(`ponte falsa em http://127.0.0.1:${process.env.PONTE}`));
  criarServidor({ log: (m, c) => console.log(m, c) }).listen(porta, "127.0.0.1", () => {
    console.log(`servidor falso em http://127.0.0.1:${porta}`);
  });
}
