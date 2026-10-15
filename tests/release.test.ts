import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const RAIZ = resolve(import.meta.dirname, '..');
const BUILD_NUCLEO = join(RAIZ, 'build', 'nucleo');
const MEDIDAS = join(RAIZ, 'build', 'nucleo-medidas.json');
const PYTHON_EMBUTIDO = join(BUILD_NUCLEO, 'python', 'python.exe');

describe('release T2 — runtime Python 3.13 embutido', () => {
  it('runtime.toml existe com versao 3.13.x, url oficial e sha256 valido', () => {
    const toml = readFileSync(join(RAIZ, 'nucleo', 'runtime.toml'), 'utf8');
    expect(toml).toMatch(/versao\s*=\s*"3\.13\.\d+"/);
    expect(toml).toMatch(/url\s*=\s*"https:\/\/github\.com\/astral-sh\/python-build-standalone\//);
    expect(toml).toMatch(/sha256\s*=\s*"[0-9a-f]{64}"/);
  });

  it('montar-nucleo.ps1 existe e referencia vard (nao vard_nucleo)', () => {
    const script = readFileSync(join(RAIZ, 'scripts', 'windows', 'montar-nucleo.ps1'), 'utf8');
    expect(script).toContain('-m vard --versao');
    expect(script).toContain('vard.server');
    expect(script).not.toContain('vard_nucleo');
  });

  it('tauri.nucleo.conf.json aponta build/nucleo como recurso', () => {
    const conf = JSON.parse(
      readFileSync(join(RAIZ, 'src-tauri', 'tauri.nucleo.conf.json'), 'utf8'),
    );
    expect(conf.bundle?.resources).toBeDefined();
    const recursos = conf.bundle.resources;
    const chave = Object.keys(recursos).find((k) => k.includes('build/nucleo'));
    expect(chave).toBeDefined();
    expect(recursos[chave!]).toBe('nucleo/');
  });

  it('package.json tem script nucleo que chama montar-nucleo.ps1', () => {
    const pkg = JSON.parse(readFileSync(join(RAIZ, 'package.json'), 'utf8'));
    expect(pkg.scripts?.nucleo).toContain('montar-nucleo.ps1');
  });

  it('bundle montado existe com python.exe e medidas validas', () => {
    if (!existsSync(PYTHON_EMBUTIDO)) {
      throw new Error(`runtime nao montado: ${PYTHON_EMBUTIDO} ausente (rode npm run nucleo)`);
    }
    expect(existsSync(MEDIDAS)).toBe(true);
    const dados = JSON.parse(readFileSync(MEDIDAS, 'utf8'));
    expect(dados.python).toMatch(/^3\.13\./);
    expect(dados.bytes_total).toBeGreaterThan(0);
    expect(dados.arquivos).toBeGreaterThan(0);
    expect(dados.maior_caminho_len).toBeLessThanOrEqual(160);
  });
});