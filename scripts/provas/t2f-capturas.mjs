// Prova T2f: captura das etapas do assistente na janela de Configurações.
// Usa Playwright contra Vite dev server com invoke/ponte simulados via route.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(__dirname, "..", "..");
const CAPTURAS_DIR = path.join(RAIZ, ".coordenacao", "0.9-prova", "t2f");
const URL_BASE = "http://localhost:5174";

fs.mkdirSync(CAPTURAS_DIR, { recursive: true });

// Estado simulado do primeiro uso (instalação nova)
let estadoPU = { schema: 1, etapa: "importar", concluido: false, pendencias: [] };

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 800, height: 600 } });
  const page = await context.newPage();

  // Simula invoke do Tauri e rotas da ponte
  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (url.includes("/primeiro-uso/reabrir")) {
      estadoPU.concluido = false;
      estadoPU.etapa = "importar";
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadoPU) });
    }
    if (url.endsWith("/primeiro-uso") && route.request().method() === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadoPU) });
    }
    if (url.endsWith("/primeiro-uso") && route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() || "{}");
      Object.assign(estadoPU, body);
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadoPU) });
    }
    if (url.includes("/saude") || url.includes("/status")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }
    // Demais requests seguem normalmente
    await route.continue();
  });

  // Mock do invoke do Tauri
  await page.addInitScript(() => {
    window.__TAURI__ = {
      core: {
        invoke: async (cmd, args) => {
          if (cmd === "ler_config") return { ponte_url: "http://localhost:5174", nome: "", variantes: [], idioma: "pt" };
          if (cmd === "abrir_configuracoes") return null;
          if (cmd === "inicio_no_logon_ativo") return false;
          if (cmd === "listar_monitores") return [];
          if (cmd === "falhas_de_atalho") return [];
          return null;
        },
      },
      event: {
        emitTo: async () => {},
        listen: async () => () => {},
      },
    };
  });

  await page.goto(`${URL_BASE}/configuracoes.html`);
  await page.waitForSelector("#primeiro-uso-container", { timeout: 10000 });

  // Captura cada etapa
  const etapas = ["importar", "detectar", "nome", "cerebro", "voz", "audio", "resumo"];
  for (const etapa of etapas) {
    // Espera a etapa renderizar
    await page.waitForTimeout(500);
    const visivel = await page.$eval("#primeiro-uso-container", el => !el.hidden).catch(() => false);
    if (!visivel) break;

    await page.screenshot({
      path: path.join(CAPTURAS_DIR, `etapa-${etapa}.png`),
      fullPage: true
    });
    console.log(`Capturada etapa: ${etapa}`);

    // Avança para próxima etapa
    const btnProximo = await page.$("#primeiro-uso-proximo");
    if (btnProximo) {
      // Preenche campo de nome se estiver na etapa nome
      if (etapa === "nome") {
        const inputNome = await page.$("#primeiro-uso-nome-input");
        if (inputNome) await inputNome.fill("Aurora");
      }
      await btnProximo.click();
      await page.waitForTimeout(300);
    } else {
      break;
    }
  }

  // Captura final
  await page.screenshot({
    path: path.join(CAPTURAS_DIR, "assistente-completo.png"),
    fullPage: true
  });

  await browser.close();
  console.log(`Capturas salvas em: ${CAPTURAS_DIR}`);
}

main().catch(e => { console.error(e); process.exit(1); });