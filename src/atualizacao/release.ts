// Release do GitHub: comparação de versões e leitura do JSON da API. Puro; quem faz rede é o Rust (allowlist de hosts).
export const URL_RELEASE = "https://api.github.com/repos/pauloroos/project-vard/releases/latest";

export interface Release {
  versao: string; nome: string; notas: string; publicadaEm: string; url: string;
  setup: { nome: string; url: string; bytes: number; sha256: string | null } | null;
  maisNova: boolean;
}

function partes(v: string): { numeros: number[]; pre: boolean } {
  const s = v.trim().replace(/^v/i, "");
  const [base, pre] = s.split("-", 2);
  const numeros = base.split(".").map((p) => Number.parseInt(p, 10)).map((n) => (Number.isFinite(n) ? n : 0));
  while (numeros.length < 3) numeros.push(0);
  return { numeros, pre: pre !== undefined };
}

/** -1, 0 ou 1 como `a <=> b`. "v" na frente é ignorado; "1.0" = "1.0.0"; sufixo "-x" conta como menor que a mesma versão sem ele. */
export function compararVersoes(a: string, b: string): -1 | 0 | 1 {
  const x = partes(a), y = partes(b);
  for (let i = 0; i < Math.max(x.numeros.length, y.numeros.length); i++) {
    const d = (x.numeros[i] ?? 0) - (y.numeros[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  if (x.pre !== y.pre) return x.pre ? -1 : 1;
  return 0;
}

/** Lê a resposta de /releases/latest; qualquer coisa fora da forma esperada devolve null. */
export function interpretarRelease(json: unknown, instalada: string): Release | null {
  if (typeof json !== "object" || json === null) return null;
  const j = json as Record<string, unknown>;
  if (typeof j.tag_name !== "string" || !j.tag_name.trim()) return null;
  const versao = j.tag_name.trim().replace(/^v/i, "");
  const assets = Array.isArray(j.assets) ? j.assets : [];
  let setup: Release["setup"] = null;
  for (const a of assets) {
    if (typeof a !== "object" || a === null) continue;
    const o = a as Record<string, unknown>;
    if (typeof o.name === "string" && /-setup\.exe$/i.test(o.name) && typeof o.browser_download_url === "string" && typeof o.size === "number") {
      const m = typeof o.digest === "string" ? /^sha256:([0-9a-f]{64})$/i.exec(o.digest.trim()) : null;
      setup = { nome: o.name, url: o.browser_download_url, bytes: o.size, sha256: m ? m[1].toLowerCase() : null }; break;
    }
  }
  return {
    versao, nome: typeof j.name === "string" ? j.name : versao, notas: typeof j.body === "string" ? j.body : "",
    publicadaEm: typeof j.published_at === "string" ? j.published_at : "", url: typeof j.html_url === "string" ? j.html_url : "",
    setup, maisNova: compararVersoes(versao, instalada) > 0,
  };
}
