import { extrairComando, classificar, ehInterrupcao, ehConfirmacao, proximoEstadoPorStatus, JanelaTermino, FINISH_MS } from "./rotas.js";
import { FALAS } from "./falas.js";

const $ = (id) => document.getElementById(id);
const mudo = new URLSearchParams(location.search).has("mute");
// jogo: modo jogo ou ponte fora; ninguém escuta (spec §5). servico: "ligado" | "jogo" | "ponte_fora" (rotas.proximoEstadoPorStatus).
const estado = { ouvindo: false, pensando: false, falando: false, tela: null, confirmarJogo: false, timerJogo: null, micBloqueado: false, ultimoErro: null, jogo: false, servico: "ligado" };
window.vard = { mudo, estado, falar };

function setEstado(t) { $("estado").textContent = t; }
function rotuloRepouso() { return estado.jogo ? "modo jogo" : (estado.micBloqueado ? "microfone bloqueado" : (estado.ouvindo ? "ouvindo" : "parado")); }
function log(quem, texto) { const p = document.createElement("p"); p.className = quem; p.textContent = (quem === "eu" ? "Você: " : "Vard: ") + texto; const l = $("log"); l.prepend(p); while (l.children.length > 200) l.lastChild.remove(); }

// ---------------------------------------------------------------- boca (UMA função)
let vozPt = null;
function escolherVoz() {
  const vozes = speechSynthesis.getVoices();
  vozPt = vozes.find((v) => v.lang === "pt-BR" && /google/i.test(v.name))
       || vozes.find((v) => v.lang === "pt-BR") || null;
}
speechSynthesis.onvoiceschanged = escolherVoz; escolherVoz();

function falar(texto) {
  log("vard", texto);
  if (mudo) return;                     // ?mute=1: nunca fala, checado AQUI dentro
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "pt-BR"; if (vozPt) u.voice = vozPt; u.rate = 1.05;
  u.onstart = () => { estado.falando = true; $("nucleo").classList.add("falando"); setEstado("falando"); };
  u.onend = () => { estado.falando = false; $("nucleo").classList.remove("falando"); setEstado(rotuloRepouso()); };
  estado.falando = true;                // antes do speak: pega interrupção nos primeiros instantes
  try { speechSynthesis.speak(u); }
  catch (e) { console.warn("boca:", e); estado.falando = false; $("nucleo").classList.remove("falando"); setEstado(rotuloRepouso()); }
}

// ---------------------------------------------------------------- ouvido
// O Chrome encerra a sessão com "no-speech" depois de ~7-10 s de silêncio: isso é normal e NÃO é queda.
// Só erro real conta; religa com backoff e avisa em voz no máximo uma vez por minuto.
let rec = null; let quedas = [];
const BACKOFF_MS = [300, 1000, 5000, 30000];
const BENIGNOS = ["no-speech", "aborted"];
let passoBackoff = 0; let ultimoAviso = 0; let reiniciouPorErro = false;
const janela = new JanelaTermino(FINISH_MS, despachar, { semGatilho: () => estado.confirmarJogo });

function avisarOuvido() {
  const agora = Date.now();
  if (agora - ultimoAviso < 60000) return;
  ultimoAviso = agora; falar(FALAS.erroOuvido);
}

function ligarOuvido() {
  if (!("webkitSpeechRecognition" in window)) { setEstado("este navegador não tem reconhecimento de voz"); return; }
  rec = new webkitSpeechRecognition();
  rec.lang = "pt-BR"; rec.continuous = true; rec.interimResults = true;
  rec.onstart = () => {
    estado.ouvindo = true; estado.micBloqueado = false; $("nucleo").classList.add("ouvindo");
    setEstado(reiniciouPorErro ? "ouvindo (ouvido reiniciado)" : "ouvindo");
    if (!reiniciouPorErro) passoBackoff = 0;   // sessão normal: zera; após erro real o backoff só zera numa sessão sem erro
    reiniciouPorErro = false;
  };
  rec.onresult = (ev) => {
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const r = ev.results[i]; const t = r[0].transcript.trim();
      if (estado.falando) {                       // a própria voz do Vard / áudio de fundo: só interrupção vale
        if (ehInterrupcao(t)) { speechSynthesis.cancel(); janela.cancelar(); return; }
        continue;
      }
      if (r.isFinal && t) janela.receber(t);
    }
  };
  rec.onerror = (e) => {
    estado.ultimoErro = e.error;
    if (!BENIGNOS.includes(e.error)) console.warn("ouvido:", e.error);
    if (["not-allowed", "audio-capture", "service-not-allowed"].includes(e.error)) {
      const jaBloqueado = estado.micBloqueado;
      estado.micBloqueado = true; setEstado("microfone bloqueado");
      if (!jaBloqueado) avisarOuvido();   // avisa uma vez só
    }
  };
  rec.onend = () => {            // o Chrome encerra sozinho de tempos em tempos: religar
    estado.ouvindo = false; $("nucleo").classList.remove("ouvindo");
    const erro = estado.ultimoErro; estado.ultimoErro = null;
    if (estado.micBloqueado) return;   // negado: não religa em loop
    let atraso = BACKOFF_MS[0];
    if (erro && !BENIGNOS.includes(erro)) {      // queda real
      reiniciouPorErro = true;
      const agora = Date.now(); quedas = quedas.filter((q) => agora - q < 60000); quedas.push(agora);
      if (quedas.length >= 3) { avisarOuvido(); quedas = []; }
      atraso = BACKOFF_MS[Math.min(passoBackoff, BACKOFF_MS.length - 1)]; passoBackoff++;
    }
    const este = rec;
    setTimeout(() => {
      if (estado.jogo || este !== rec) return;   // modo jogo ou ouvido trocado: não religa
      try { este.start(); } catch (e) { if (e.name !== "InvalidStateError") avisarOuvido(); }
    }, atraso);
  };
  rec.start();
}

// Modo jogo (ou ponte fora): o ouvido para de vez e a aba fica quieta. Sem fala aqui.
function calarOuvido(motivo) {
  estado.jogo = true;
  estado.confirmarJogo = false; clearTimeout(estado.timerJogo);
  if (rec) { rec.onstart = rec.onend = rec.onresult = rec.onerror = null; try { rec.abort(); } catch {} }
  rec = null;
  estado.ouvindo = false; $("nucleo").classList.remove("ouvindo");
  janela.cancelar();
  setEstado(motivo === "ponte_fora" ? "ponte fora" : "modo jogo");
}

async function despachar(textoFinal) {
  if (estado.confirmarJogo) {
    estado.confirmarJogo = false; clearTimeout(estado.timerJogo);
    if (ehConfirmacao(textoFinal)) {
      try {
        const r = await fetch("/modo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modo: "jogo" }) });
        if (r.ok) { falar(FALAS.modoJogoAtivado); estado.servico = "jogo"; calarOuvido("jogo"); return; }
        const d = await r.json().catch(() => ({}));
        falar(FALAS.erros[d.erro] ?? FALAS.erroModelo);
      } catch { falar(FALAS.erroModelo); }
    }
    return;
  }
  const comando = extrairComando(textoFinal);
  if (comando === null) return;            // não era com o Vard: ignora em silêncio
  if (comando === "") { falar(FALAS.saudacao); return; }   // só o nome: chamou e não pediu nada
  log("eu", comando);
  const rota = classificar(comando);
  if (rota === "modo") { estado.confirmarJogo = true; clearTimeout(estado.timerJogo); estado.timerJogo = setTimeout(() => { estado.confirmarJogo = false; }, 15000); falar(FALAS.modoJogoConfirmar); return; }
  if (rota === "see") return perguntarTela(comando);
  return perguntar(comando);
}

// ---------------------------------------------------------------- cérebro
async function perguntar(comando) {
  setEstado("pensando"); const t = setTimeout(() => falar(FALAS.pensando), 6000);
  try {
    const r = await fetch("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto: comando }) });
    clearTimeout(t);
    const d = await r.json();
    falar(r.ok ? d.resposta : (FALAS.erros[d.erro] ?? FALAS.erroModelo));
  } catch { clearTimeout(t); falar(FALAS.erroModelo); }
}

// ---------------------------------------------------------------- olhos
async function compartilharTela() {
  try {
    estado.tela = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
    $("video").srcObject = estado.tela; $("tela").classList.add("ativo");
    estado.tela.getVideoTracks()[0].onended = () => { estado.tela = null; $("tela").classList.remove("ativo"); };
  } catch (e) { console.warn("tela:", e); }
}

function capturarQuadro() {           // UM quadro, agora, resolução cheia, JPEG
  const v = $("video"); const c = document.createElement("canvas");
  if (!v.videoWidth || !v.videoHeight) return Promise.resolve(null);
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0);
  return new Promise((res) => c.toBlob(res, "image/jpeg", 0.9));
}

async function perguntarTela(comando) {
  if (!estado.tela) { falar(FALAS.telaNaoCompartilhada); return; }   // sem chamar modelo
  setEstado("olhando");
  try {
    const blob = await capturarQuadro();
    if (!blob) { setEstado(rotuloRepouso()); falar(FALAS.telaAindaCarregando); return; }
    const fd = new FormData(); fd.append("imagem", blob, "tela.jpg"); fd.append("pergunta", comando);
    const r = await fetch("/see", { method: "POST", body: fd }); const d = await r.json();
    falar(r.ok ? d.resposta : (FALAS.erros[d.erro] ?? FALAS.erroModelo));
  } catch { falar(FALAS.erroModelo); }
}

// ---------------------------------------------------------------- HUD e boot
async function atualizarServicos() {
  let s = null;
  try { s = await (await fetch("/status")).json(); } catch {}   // ponte fora: segue tentando a cada 10 s, calada
  if (s) $("servicos").textContent = `OpenJarvis ${s.openjarvis ? "ok" : "fora"} · LM Studio ${s.lmstudio ? s.modelo || "sem modelo" : "fora"}`;
  else $("servicos").textContent = "ponte fora";
  estado.servico = proximoEstadoPorStatus(estado.servico, s);
  if (estado.servico !== "ligado") calarOuvido(estado.servico);   // idempotente
  else if (estado.jogo) {   // voltou: o Chrome não garante religar o microfone sem gesto; o botão religa
    estado.jogo = false; setEstado("clique em Ligar o ouvido");
  }
}
$("btn-iniciar").onclick = async () => {
  if (estado.jogo) {   // confere de novo antes de ligar: pode ter voltado entre duas consultas
    await atualizarServicos();
    if (estado.jogo) { setEstado(estado.servico === "ponte_fora" ? "ponte fora: volte pela bandeja" : "modo jogo: volte pela bandeja"); return; }
  }
  if (rec) { estado.micBloqueado = false; try { rec.start(); } catch {} }   // religar depois de negado/parado
  else ligarOuvido();
  falar(FALAS.saudacao);
};   // 1º clique libera áudio
$("btn-tela").onclick = compartilharTela;
atualizarServicos(); setInterval(atualizarServicos, 10000);
new EventSource("/events");            // a oficina (plano 3) vai publicar aqui
setEstado("clique em Ligar o ouvido");
