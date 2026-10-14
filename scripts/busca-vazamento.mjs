// Busca de vazamento no repositório público: IP, caminho de unidade/usuário, chave e e-mail.
// Uso: `npm run vazamento` (varre `git ls-files` + arquivos novos + conteúdo do índice; sai com código 1 se houver achado).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BINARIOS = /\.(png|ico|icns|wav)$/i;
const SEM_IP = /(^|\/)(package\.json|package-lock\.json)$|\.lock$/;

// Ordem importa: a pasta de usuário vem antes da letra de unidade, para contar uma vez só.
const REGRAS = [
  { regra: "pasta-de-usuario", re: /C:[\\/]Users[\\/]/g },
  { regra: "unidade", re: /[A-Z]:[\\/]/g },
  { regra: "chave-sk", re: /sk-[A-Za-z0-9_-]{16,}/g },
  { regra: "bearer", re: /Bearer [A-Za-z0-9._~+/=-]{20,}/g },
  { regra: "email", re: /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/g, ignorar: /noreply|example|exemplo/i },
  { regra: "ip", re: /(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.]*\d)/g, ip: true },
];

function ipSuspeito(m) {
  const o = m.slice(1, 5).map(Number);
  if (o.some((n) => n > 255)) return false;
  if (o[0] === 127) return false;
  const t = o.join(".");
  return t !== "0.0.0.0" && t !== "255.255.255.255";
}

const norm = (p) => p.replace(/\\/g, "/");

/** O achado é ignorado só se o `trecho` do permitido estiver contido no texto do próprio achado e o arquivo casar (`*` vale para qualquer um). */
function permitido(permitidos, arquivo, trecho) {
  return permitidos.some((p) => (p.arquivo === "*" || norm(p.arquivo) === norm(arquivo)) && trecho.includes(p.trecho));
}

/** @returns {{arquivo: string, linha: number, regra: string, trecho: string}[]} */
export function achar(texto, arquivo, permitidos, pessoais = []) {
  const achados = [];
  const linhas = texto.split(/\r?\n/);
  linhas.forEach((linha, i) => {
    const baixa = linha.toLowerCase();
    for (const termo of pessoais) {
      if (baixa.includes(termo) && !permitido(permitidos, arquivo, termo)) achados.push({ arquivo, linha: i + 1, regra: "pessoal", trecho: termo });
    }
    const ocupados = [];
    for (const r of REGRAS) {
      if (r.ip && SEM_IP.test(norm(arquivo))) continue;
      for (const m of linha.matchAll(r.re)) {
        const ini = m.index;
        const fim = ini + m[0].length;
        if (ocupados.some(([a, b]) => ini < b && fim > a)) continue;
        if (r.ignorar?.test(m[0])) continue;
        if (r.ip && !ipSuspeito(m)) continue;
        ocupados.push([ini, fim]);
        if (permitido(permitidos, arquivo, m[0])) continue;
        achados.push({ arquivo, linha: i + 1, regra: r.regra, trecho: m[0] });
      }
    }
  });
  return achados;
}

const NAO_SEGREDO = new Set(["unidade", "pasta-de-usuario", "ip"]);

/** Lista privada externa (um termo por linha, em VARD_AUDITORIA_PESSOAL). O termo real nunca vai ao log: o achado só diz arquivo, linha e regra. */
export function lerPessoais(caminho) {
  if (!caminho) return [];
  try {
    return readFileSync(caminho, "utf8").split(/\r?\n/).map((l) => l.trim().toLowerCase()).filter((l) => l !== "" && !l.startsWith("#"));
  } catch { return []; }
}

/** Linha de log de um achado. O log do CI é público: segredo (chave, bearer, e-mail) sai mascarado (4 primeiros caracteres + ***). */
export function formatarAchado(a) {
  if (a.regra === "pessoal") return `${a.arquivo}:${a.linha} [pessoal]`;
  const trecho = NAO_SEGREDO.has(a.regra) ? a.trecho : `${a.trecho.slice(0, 4)}***`;
  return `${a.arquivo}:${a.linha} [${a.regra}] ${trecho}`;
}

export function lerPermitidos(caminho) {
  return readFileSync(caminho, "utf8")
    .split(/\r?\n/)
    .filter((l) => l.trim() !== "" && !l.startsWith("#"))
    .map((l) => {
      const i = l.indexOf("\t");
      return { arquivo: l.slice(0, i), trecho: l.slice(i + 1) };
    })
    .filter((p) => p.trecho !== "");
}

function principal() {
  const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
  const permitidos = lerPermitidos(join(raiz, "scripts", "vazamento-permitido.txt"));
  const arquivos = execFileSync("git", ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], { cwd: raiz, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 })
    .split("\0")
    .filter((f) => f && !BINARIOS.test(f) && f !== "scripts/vazamento-permitido.txt" && !f.split("/").includes("node_modules"));
  const pessoais = lerPessoais(process.env.VARD_AUDITORIA_PESSOAL);
  let total = 0;
  for (const f of arquivos) {
    const textos = [];
    try { textos.push(readFileSync(join(raiz, f), "utf8")); } catch { /* removido da arvore: ainda vale o indice */ }
    try { textos.push(execFileSync("git", ["show", `:${f}`], { cwd: raiz, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] })); } catch { /* fora do indice */ }
    const vistos = new Set();
    for (const texto of textos) {
      if (texto.includes(String.fromCharCode(0))) continue;
      for (const a of achar(texto, f, permitidos, pessoais)) {
        const chave = `${a.linha}|${a.regra}|${a.trecho}`;
        if (vistos.has(chave)) continue;
        vistos.add(chave);
        total += 1;
        console.error(formatarAchado(a));
      }
    }
  }
  if (total > 0) {
    console.error(`vazamento: ${total} achado(s)`);
    process.exit(1);
  }
  console.log(`vazamento: OK (${arquivos.length} arquivos)`);
}

if (process.argv[1] && norm(fileURLToPath(import.meta.url)) === norm(process.argv[1])) principal();
