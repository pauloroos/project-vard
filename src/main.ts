import { carregarConfig } from "./config/config";

window.addEventListener("DOMContentLoaded", async () => {
  const cfg = await carregarConfig();
  console.log("config carregada", cfg.nome);
});
