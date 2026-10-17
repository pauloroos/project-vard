import type { Config } from "../config/config";
import type { Nucleo } from "./nucleo";

/** Mesma aparência na abertura e quando a configuração muda, no widget e na sala. */
export function aplicarAparencia(cfg: Pick<Config, "cor_elementos" | "opacidade_elementos">, nucleo: Nucleo) {
  document.documentElement.style.setProperty("--cor-elementos", cfg.cor_elementos || "var(--ciano)");
  document.documentElement.style.setProperty("--opacidade-elementos", String(cfg.opacidade_elementos));
  nucleo.definirCor(cfg.cor_elementos || null);
}
