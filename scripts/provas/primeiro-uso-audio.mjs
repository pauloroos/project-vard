/** Prova CDP isolada, sem hardware. Uso: node scripts/provas/primeiro-uso-audio.mjs
 * <endpoint-cdp> <origem-vite>. Não abre app/navegador e não grava arquivos.
 * O operador fornece um navegador de teste e encerra seus processos ao fim.
 */
import { createServer } from "node:http";
import assert from "node:assert/strict";
import { basename } from "node:path";

const [endpoint, origem] = process.argv.slice(2);
if (!endpoint || !origem) throw new Error("Informe endpoint CDP e origem Vite de teste");
const pedidos = [];
const servidor = createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", new URL(origem).origin);
  res.setHeader("Access-Control-Allow-Headers", "content-type");
  res.setHeader("Access-Control-Expose-Headers", "X-Taxa");
  if (req.method === "OPTIONS") { res.writeHead(204).end(); return; }
  const blocos = []; for await (const b of req) blocos.push(b);
  const corpo = Buffer.concat(blocos);
  if (req.url === "/transcrever") {
    assert.equal(corpo.subarray(0, 4).toString(), "RIFF");
    assert.equal(corpo.readUInt32LE(24), 16000);
    pedidos.push({ rota: "/transcrever", bytes: corpo.length, taxa: 16000 });
    res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ texto: "fala sintética de teste" }));
  } else if (req.url === "/falar") {
    const fala = JSON.parse(corpo.toString());
    assert.equal(fala.texto, "O teste de voz está funcionando"); assert.equal(fala.voz, "voz-teste");
    pedidos.push({ rota: "/falar", bytes: 4800, voz: fala.voz });
    res.setHeader("Content-Type", "audio/pcm"); res.setHeader("X-Taxa", "24000"); res.end(Buffer.alloc(4800));
  } else { res.writeHead(404).end(); }
});
await new Promise((ok) => servidor.listen(0, "127.0.0.1", ok));
const vozUrl = `http://127.0.0.1:${servidor.address().port}`;
let ws;
try {
  const alvos = await (await fetch(`${endpoint}/json/list`)).json();
  const alvo = alvos.find((t) => t.type === "page" && t.url.startsWith(origem));
  if (!alvo) throw new Error("Página de teste não encontrada no endpoint CDP");
  ws = new WebSocket(alvo.webSocketDebuggerUrl);
  await new Promise((ok, falhar) => { ws.onopen = ok; ws.onerror = falhar; });
  let id = 0; const pendentes = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id) { const p = pendentes.get(m.id); pendentes.delete(m.id); m.error ? p?.reject(new Error(m.error.message)) : p?.resolve(m.result); } };
  const cdp = (method, params) => new Promise((resolve, reject) => {
    const atual = ++id; pendentes.set(atual, { resolve, reject }); ws.send(JSON.stringify({ id: atual, method, params }));
  });
  const resposta = await cdp("Runtime.evaluate", { awaitPromise: true, returnByValue: true, expression: `
    (async () => {
      const { montarEtapaAudio } = await import('/src/ui/primeiro-uso-audio.ts');
      const { CONFIG_PADRAO } = await import('/src/config/config.ts');
      const { pcmParaWav } = await import('/src/audio/wav.ts');
      const recursos = { tracksParadas: 0, contextosAbertos: 0, contextosFechados: 0, restauracoes: 0, suspensoes: 0, saida: '', entrada: '', wavSintetico: false };
      const originalContexto = window.AudioContext;
      const originalDevices = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
      const amostras = Float32Array.from({length:48000}, (_, i) => 0.2 * Math.sin(2 * Math.PI * 440 * i / 48000));
      const wav = new DataView(pcmParaWav(amostras,48000));
      const sinteticas = Float32Array.from({length:48000}, (_, i) => wav.getInt16(44+i*2,true)/32768);
      recursos.wavSintetico = true;
      const dispositivos = { enumerateDevices: async () => [
        {deviceId:'mic-teste',kind:'audioinput',label:'Entrada de teste'}, {deviceId:'saida-teste',kind:'audiooutput',label:'Saída de teste'}],
        getUserMedia: async (c) => { recursos.entrada = c.audio.deviceId.exact; return { getTracks: () => [{stop: () => recursos.tracksParadas++, addEventListener(){}, removeEventListener(){}}] }; },
        addEventListener(){}, removeEventListener(){} };
      Object.defineProperty(navigator, 'mediaDevices', {configurable:true,value:dispositivos});
      window.AudioContext = class {
        state='running'; sampleRate=48000; destination={};
        constructor(){recursos.contextosAbertos++}
        createMediaStreamSource(){return {connect(){},disconnect(){}}}
        createGain(){return {gain:{value:1},connect(){},disconnect(){}}}
        createScriptProcessor(){const p={onaudioprocess:null,connect(){},disconnect(){clearInterval(timer)}};
          const timer=setInterval(()=>p.onaudioprocess?.({inputBuffer:{getChannelData:()=>sinteticas}}),100); return p;}
        async setSinkId(id){recursos.saida=id}
        async decodeAudioData(){return {}}
        createBufferSource(){const s={buffer:null,onended:null,connect(){},disconnect(){},start(){setTimeout(()=>s.onended?.(),20)},stop(){}}; return s;}
        async close(){if(this.state!=='closed'){this.state='closed';recursos.contextosFechados++}}
      };
      const container=document.createElement('div');document.body.append(container);
      const salvos=[];
      let etapa;
      try {
        etapa=montarEtapaAudio(container,{config:{...CONFIG_PADRAO,voz_url:${JSON.stringify(vozUrl)},voz_propria:'voz-teste',voz_provedor:'propria',microfone_id:'mic-teste',saida_id:'saida-teste'},
          transcrever: async (wav,signal) => (await (await fetch(${JSON.stringify(vozUrl)}+'/transcrever',{method:'POST',body:wav,signal})).json()).texto,
          suspenderEscuta: async()=>{recursos.suspensoes++;return()=>recursos.restauracoes++},salvar:async(r)=>salvos.push(r)});
        const aguardar=async(f)=>{const inicio=Date.now();while(!f()){if(Date.now()-inicio>10000)throw new Error('Prazo da prova');await new Promise(r=>setTimeout(r,25))}};
        await new Promise(r=>setTimeout(r,50));
        container.querySelector('[data-audio=microfone]').click();
        await aguardar(()=>container.textContent.includes('Transcrição: fala sintética de teste'));
        const transcricao=true;
        container.querySelector('[data-audio=voz]').click();
        await aguardar(()=>!container.querySelector('[data-audio=confirmar]').disabled);
        const antes=salvos.at(-1).voz_ouvida;
        container.querySelector('[data-audio=confirmar]').click();
        await new Promise(r=>setTimeout(r,25));
        return {recursos,transcricao,vozOuvidaAntes:antes,confirmacaoSimulada:salvos.at(-1).voz_ouvida};
      } finally {
        etapa?.sair();container.remove();window.AudioContext=originalContexto;
        if(originalDevices)Object.defineProperty(navigator,'mediaDevices',originalDevices);else delete navigator.mediaDevices;
      }
    })()` });
  if (resposta.exceptionDetails) throw new Error(resposta.exceptionDetails.exception?.description || "Falha na página");
  const prova = resposta.result.value;
  assert.equal(prova.transcricao, true); assert.equal(prova.vozOuvidaAntes, false);
  assert.equal(prova.recursos.contextosAbertos, prova.recursos.contextosFechados);
  assert.equal(prova.recursos.tracksParadas, 1); assert.equal(prova.recursos.restauracoes, 2);
  assert.equal(prova.recursos.entrada, "mic-teste"); assert.equal(prova.recursos.saida, "saida-teste");
  console.log(JSON.stringify({ ...prova, pedidos,
    processo: { pid: process.pid, executavel: basename(process.execPath), inicio: new Date(Date.now() - process.uptime() * 1000).toISOString() },
    falta_prova_real: ["microfone físico e transcrição", "áudio ouvido na saída física selecionada"] }, null, 2));
} finally {
  ws?.close(); await new Promise((ok) => servidor.close(ok));
}
