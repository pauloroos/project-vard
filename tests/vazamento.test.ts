import { describe, expect, it } from "vitest";
import { execFileSync, spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
// @ts-expect-error módulo .mjs sem tipos
import { achar, formatarAchado } from "../scripts/busca-vazamento.mjs";

describe("busca de vazamento", () => {
  it("acha_ip_que_nao_e_loopback", () => { expect(achar("host 203.0.113.7", "a.ts", [])).toHaveLength(1); });
  it("ignora_loopback_e_zero", () => { expect(achar("127.0.0.1 0.0.0.0 localhost", "a.ts", [])).toHaveLength(0); });
  it("ignora_versao_com_quatro_partes_em_package", () => { expect(achar('"version": "1.2.3.4"', "x/package.json", [])).toHaveLength(0); });
  it("acha_unidade_e_pasta_de_usuario", () => { expect(achar("Q:\\pasta\\x e C:\\Users\\fulano", "a.md", [])).toHaveLength(2); });
  it("acha_sk_e_bearer", () => { expect(achar("sk-proj-ABCDEFGHIJKLMNOPQRST e Bearer abcdefghijklmnopqrstuvwxyz", "a.ts", [])).toHaveLength(2); });
  it("acha_email_mas_nao_noreply", () => {
    expect(achar("fulano@empresa.com", "a.md", [])).toHaveLength(1);
    expect(achar("1+x@users.noreply.github.com noreply@exemplo.com", "a.md", [])).toHaveLength(0);
  });
  it("permitido_por_arquivo_e_trecho", () => { expect(achar("Paulo Roos", "LICENSE", [{ arquivo: "LICENSE", trecho: "Paulo Roos" }])).toHaveLength(0); });
  it("permitido_so_vale_com_a_entrada", () => {
    expect(achar("fulano@empresa.com", "LICENSE", [{ arquivo: "LICENSE", trecho: "fulano@empresa.com" }])).toHaveLength(0);
    expect(achar("fulano@empresa.com", "LICENSE", [])).toHaveLength(1);
  });
  it("permitido_nao_esconde_vazamento_na_mesma_linha", () => {
    expect(achar("E:\\DEV\\x (ex.: X:\\)", "a.md", [{ arquivo: "*", trecho: "X:\\" }])).toHaveLength(1);
  });
  it("formatar_achado_nao_imprime_o_segredo", () => {
    const [a] = achar("sk-proj-ABCDEFGHIJKLMNOPQRST", "a.ts", []);
    const saida = formatarAchado(a);
    expect(saida).not.toContain("ABCDEFGHIJKLMNOPQRST");
    expect(saida).toContain("a.ts:1");
    expect(saida).toContain("chave-sk");
    expect(saida).toContain("sk-p***");
    const [b] = achar("Bearer abcdefghijklmnopqrstuvwxyz", "a.ts", []);
    expect(formatarAchado(b)).not.toContain("abcdefghijklmnopqrstuvwxyz");
    const [e] = achar("fulano@empresa.com", "a.md", []);
    expect(formatarAchado(e)).not.toContain("empresa");
  });

  it("pessoal_da_lista_externa_acha_sem_imprimir_o_termo", () => {
    const [a] = achar("Falar com o Fulaninho agora", "a.md", [], ["fulaninho"]);
    expect(a.regra).toBe("pessoal");
    expect(formatarAchado(a)).toBe("a.md:1 [pessoal]");
  });
});

describe("busca de vazamento no repositório", () => {
  function repoTemporario() {
    const raiz = mkdtempSync(join(tmpdir(), "vard-vaz-"));
    mkdirSync(join(raiz, "scripts"));
    copyFileSync(join(__dirname, "..", "scripts", "busca-vazamento.mjs"), join(raiz, "scripts", "busca-vazamento.mjs"));
    writeFileSync(join(raiz, "scripts", "vazamento-permitido.txt"), "# vazio\n");
    execFileSync("git", ["init", "-q"], { cwd: raiz });
    return raiz;
  }
  function rodar(raiz: string, env: Record<string, string> = {}) {
    return spawnSync("node", [join(raiz, "scripts", "busca-vazamento.mjs")], { cwd: raiz, encoding: "utf8", env: { ...process.env, ...env } });
  }
  it("pega_arquivo_novo_nao_rastreado", () => {
    const raiz = repoTemporario();
    try {
      writeFileSync(join(raiz, "novo.md"), "chave sk-proj-ABCDEFGHIJKLMNOPQRST\n");
      const r = rodar(raiz);
      expect(r.status).toBe(1);
      expect(r.stderr).toContain("novo.md:1 [chave-sk]");
      expect(r.stderr + r.stdout).not.toContain("ABCDEFGHIJKLMNOPQRST");
    } finally { rmSync(raiz, { recursive: true, force: true }); }
  });
  it("pega_segredo_que_so_existe_no_indice", () => {
    const raiz = repoTemporario();
    try {
      writeFileSync(join(raiz, "a.md"), "Bearer abcdefghijklmnopqrstuvwxyz\n");
      execFileSync("git", ["add", "a.md"], { cwd: raiz });
      writeFileSync(join(raiz, "a.md"), "limpo\n");
      const r = rodar(raiz);
      expect(r.status).toBe(1);
      expect(r.stderr).toContain("a.md:1 [bearer]");
    } finally { rmSync(raiz, { recursive: true, force: true }); }
  });
  it("pega_dado_pessoal_da_lista_externa_sem_vazar_o_valor", () => {
    const raiz = repoTemporario();
    try {
      writeFileSync(join(raiz, "lista.txt"), "# lista privada\ncicrano-real\n");
      writeFileSync(join(raiz, "b.md"), "oi Cicrano-Real\n");
      const r = rodar(raiz, { VARD_AUDITORIA_PESSOAL: join(raiz, "lista.txt") });
      expect(r.status).toBe(1);
      expect(r.stderr).toContain("b.md:1 [pessoal]");
      expect((r.stderr + r.stdout).toLowerCase()).not.toContain("cicrano");
    } finally { rmSync(raiz, { recursive: true, force: true }); }
  });
});
