import { listen } from "@tauri-apps/api/event";
import { carregarConfig } from "./config/config";
import { abrirMicrofone, onAmostras, rmsAtual, taxaAtual } from "./audio/microfone";
import { DetectorDeVoz } from "./audio/vad";
import { Nucleo } from "./ui/nucleo";

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
  const dica = document.getElementById("dica") as HTMLElement;
  const nucleo = new Nucleo(canvas);
  nucleo.iniciar();

  let pttSegurado = false;
  let pcm: Float32Array[] = [];
  let capturando = false;
  const detector = new DetectorDeVoz({ limiar: cfg.limiar_vad, inicioMs: 150, fimMs: cfg.finish_ms, tetoMs: 12000 });

  const encerrar = () => {
    capturando = false;
    const total = pcm.reduce((s, b) => s + b.length, 0);
    const tudo = new Float32Array(total);
    let o = 0;
    for (const b of pcm) { tudo.set(b, o); o += b.length; }
    pcm = [];
    // A tarefa 4 envia isto; por enquanto só registra o tamanho.
    console.log("fala capturada", tudo.length, "amostras a", taxaAtual(), "Hz");
  };

  let ligado = false;
  canvas.addEventListener("click", async () => {
    if (ligado) return;
    try {
      const mic = await abrirMicrofone();
      ligado = true;
      dica.hidden = true;
      nucleo.setAnalisadores(mic.analisador, null);
      onAmostras((a) => { if (capturando) pcm.push(a); });
      setInterval(() => {
        const ev = detector.alimentar(rmsAtual(), performance.now());
        if (ev === "inicio") { capturando = true; pcm = []; nucleo.setEstado("ouvindo"); }
        else if (ev === "fim" || ev === "teto") { encerrar(); if (!pttSegurado) nucleo.setEstado("repouso"); }
      }, 50);
    } catch (erro) {
      console.error("falha ao abrir o microfone", erro);
      dica.textContent = "microfone indisponível";
      nucleo.setEstado("erro");
    }
  });

  await listen("ptt-inicio", () => { pttSegurado = true; nucleo.setEstado("ouvindo"); });
  await listen("ptt-fim", () => { pttSegurado = false; nucleo.setEstado(detector.falando ? "ouvindo" : "repouso"); });
});
