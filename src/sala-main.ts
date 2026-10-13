import { invoke } from "@tauri-apps/api/core";
import { emitTo, listen } from "@tauri-apps/api/event";
import { Nucleo } from "./ui/nucleo";
import { ROTULO_ESTADO } from "./ui/hud";
import { EspectroRemoto, type Niveis } from "./sala/espectro";
import { ESPELHO_INICIAL, formatarHora, reduzir, type Espelho } from "./sala/espelho";

// Sala: só espelho. Quem ouve, pensa e fala é o widget; aqui chegam estado, textos e níveis por evento.
window.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("nucleo") as HTMLCanvasElement;
  const el = (id: string) => document.getElementById(id) as HTMLElement;
  const ladoSala = () => Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.62);
  const nucleo = new Nucleo(canvas, ladoSala());
  const entrada = new EspectroRemoto();
  const saida = new EspectroRemoto();
  nucleo.setAnalisadores(entrada, saida);
  nucleo.iniciar();
  window.addEventListener("resize", () => nucleo.redimensionar(ladoSala()));

  let espelho: Espelho = ESPELHO_INICIAL;
  const pintar = () => {
    nucleo.setEstado(espelho.estado);
    document.body.dataset.estado = espelho.estado;
    el("estado").textContent = espelho.detalhe || ROTULO_ESTADO[espelho.estado];
    el("ouvido").textContent = espelho.ouvido;
    el("resposta").textContent = espelho.resposta;
  };
  const tique = () => { el("relogio").textContent = formatarHora(new Date()); };
  tique();
  setInterval(tique, 1000);
  pintar();

  // Payloads vêm de outra janela: reduzir e EspectroRemoto.atualizar descartam o que não tem a forma esperada.
  await listen<unknown>("sala:espelho", (ev) => { espelho = reduzir(espelho, ev.payload); pintar(); });
  await listen<unknown>("sala:niveis", (ev) => {
    const p = typeof ev.payload === "object" && ev.payload !== null ? (ev.payload as { entrada?: Partial<Niveis>; saida?: Partial<Niveis> }) : null;
    entrada.atualizar(p?.entrada);
    saida.atualizar(p?.saida);
  });
  window.addEventListener("keydown", (ev) => { if (ev.key === "Escape") void invoke("alternar_sala"); });
  await emitTo("hud", "sala:pronta"); // o widget responde com o retrato e começa a mandar os níveis
});
