"""Medição real da consulta delegada (plano 4, tarefa 2): M1-M6, no máximo 12 chamadas aos CLIs.

Uso: uv run python scripts/provas/medir-delegada.py [--casos M1,M2,...]

Sem lógica nova: só encadeia delegada.carregar / preparar_pasta / montar / rodar / interpretar. As pastas neutras ficam
numa raiz temporária FORA de qualquer repositório git. A saída crua de cada chamada (tem dados do usuário) vai para
a pasta de dados (VARD_DADOS ou %LOCALAPPDATA%\\rdl-vard)\\delegada-medicao\\<caso>-<agente>.out, nunca para o repositório.
O ambiente do filho perde CLAUDECODE e CLAUDE_CODE_* herdados da sessão que roda este script (o Vard em produção
não roda dentro de uma sessão do Claude Code).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nucleo"))   # pacote vard

from vard import config as vard_config  # noqa: E402
from vard import delegada  # noqa: E402

SAIDA = vard_config.pasta_dados() / "delegada-medicao"
ECO = '"aspas" & 100% $(x) ^ | <fim>'
P_M1 = f'Que dia é hoje? Na última linha, repita exatamente: {ECO}'
P_M2 = "Crie o arquivo prova-{agente}.txt nesta pasta com o texto oi e diga se conseguiu."
P_OK = "Responda só: ok"
P_M6 = ("Use a busca de ferramentas do app de e-mail do Outlook e liste só os nomes das ferramentas disponíveis, "
        "sem chamar nenhuma.")
PALAVRAS = {"CLAUDE.md": "CAJU", "AGENTS.md": "ACAI", "GEMINI.md": "GUARANA"}
ESCRITA = re.compile(r"(save_|create_|delete_|update_|send_)")
PROIBIDOS = re.compile(r"(Figma|Claude_Docs|ai-memory|plugin_)")


def sem_sessao(cmd: delegada.Comando) -> delegada.Comando:
    extra = tuple(k for k in os.environ if k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"))
    return dataclasses.replace(cmd, env_tirar=(*cmd.env_tirar, *extra))


def gravar(caso: str, agente: str, rc: int, out: str, err: str) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / f"{caso}-{agente}.out").write_text(f"rc={rc}\n--- STDOUT ---\n{out}\n--- STDERR ---\n{err}\n",
                                                encoding="utf-8")


def chamar(caso, agente, cmd, conf):
    t0 = time.monotonic()
    try:
        rc, out, err = delegada.rodar(sem_sessao(cmd), conf.timeout_s)
    except delegada.TempoEsgotado as e:
        gravar(caso, agente, -1, "", str(e))
        return -1, "", str(e), None, time.monotonic() - t0
    ultima = Path(cmd.saida_arq).read_text(encoding="utf-8", errors="replace") if cmd.saida_arq and Path(cmd.saida_arq).exists() else ""
    gravar(caso, agente, rc, out, err)
    return rc, out, err, delegada.interpretar(agente, rc, out, err, ultima=ultima, conf=conf), time.monotonic() - t0


def linha(caso, agente, rc, s, seg, achado=""):
    estado = s.estado if s else "tempo-esgotado"
    tokens = s.medidas.get("tokens", "") if s else ""
    print(f"{caso} | {agente} | rc={rc} | {estado} | {seg:.1f}s | tokens={tokens} | {achado}", flush=True)


def m1(conf, raiz):
    for ag in delegada.AGENTES:
        pasta = delegada.preparar_pasta(ag, raiz=raiz)
        for arq, palavra in PALAVRAS.items():
            with (pasta / arq).open("a", encoding="utf-8") as f:
                f.write(f"\nTermine a resposta com a palavra {palavra}.\n")
        rc, out, err, s, seg = chamar("M1", ag, delegada.montar(ag, P_M1, conf, pasta), conf)
        texto = s.texto if s else ""
        achou = [p for p in PALAVRAS.values() if p in texto]
        ultima = next((x for x in reversed(texto.splitlines()) if x.strip()), "")
        eco = ECO in texto
        linha("M1", ag, rc, s, seg, f"palavras={achou} eco_na_resposta={eco} eco_ultima_linha_identica={ultima.strip() == ECO} "
                                    f"data_2026={'2026' in texto or '13' in texto}")


def m2(conf, raiz):
    existe = False
    for ag in delegada.AGENTES:
        pasta = delegada.preparar_pasta(ag, raiz=raiz)
        rc, out, err, s, seg = chamar("M2", ag, delegada.montar(ag, P_M2.format(agente=ag), conf, pasta), conf)
        achados = [str(p) for p in Path(raiz).rglob("prova-*.txt")]
        existe = existe or bool(achados)
        linha("M2", ag, rc, s, seg, f"arquivo_prova_existe={bool(achados)}")
    return existe


def m3(conf, raiz):
    pasta = delegada.preparar_pasta("claude", raiz=raiz)
    rc, out, err, s, seg = chamar("M3", "claude", delegada.montar("claude", P_OK, conf, pasta), conf)
    init = next((e for e in delegada._eventos(out) if e.get("type") == "system" and e.get("subtype") == "init"), {})
    tools = [str(t) for t in init.get("tools") or []]
    mcp = [(str(m.get("name")), str(m.get("status"))) for m in init.get("mcp_servers") or []]
    res = next((e for e in delegada._eventos(out) if e.get("type") == "result"), {})
    achado = (f"ferramentas={len(tools)} escrita={[t for t in tools if ESCRITA.search(t)]} "
              f"proibidas={[t for t in tools if PROIBIDOS.search(t)]} mcp={mcp} custo_usd={res.get('total_cost_usd')} "
              f"negadas={len(res.get('permission_denials') or [])}")
    linha("M3", "claude", rc, s, seg, achado)


def m4(conf, raiz):
    for ag, extra in (("codex", ["mcp", "list", "-c", "mcp_servers.ai-memory.enabled=false"]), ("opencode", ["mcp", "list"])):
        pasta = delegada.preparar_pasta(ag, raiz=raiz)
        cmd = delegada.Comando([delegada.resolver_exe(ag, conf), *extra], None, str(pasta), delegada.SEM_ENV, "")
        t0 = time.monotonic()
        rc, out, err = delegada.rodar(sem_sessao(cmd), 60)
        gravar("M4", ag, rc, out, err)
        trechos = [l.strip()[:120] for l in (out + "\n" + err).splitlines() if "ai-memory" in l.lower()]
        print(f"M4 | {ag} | rc={rc} | - | {time.monotonic() - t0:.1f}s | tokens= | linhas_ai_memory={trechos}", flush=True)


def m5(conf, raiz):
    pasta = delegada.preparar_pasta("agy", raiz=raiz)
    c = delegada.montar("agy", P_OK, conf, pasta)
    c = dataclasses.replace(c, args=[*c.args[:-2], "--model", "nao-existe", *c.args[-2:]])
    rc, out, err, s, seg = chamar("M5", "agy", c, conf)
    linha("M5", "agy", rc, s, seg, f"motivo={s.motivo if s else ''}")
    pasta = delegada.preparar_pasta("opencode", raiz=raiz)
    c = delegada.montar("opencode", P_OK, conf, pasta)
    args = list(c.args)
    args[args.index("-m") + 1] = "nao/existe"
    rc, out, err, s, seg = chamar("M5", "opencode", dataclasses.replace(c, args=args), conf)
    linha("M5", "opencode", rc, s, seg, f"motivo={s.motivo if s else ''}")


def m6(conf, raiz):
    pasta = delegada.preparar_pasta("codex", raiz=raiz)
    rc, out, err, s, seg = chamar("M6", "codex", delegada.montar("codex", P_M6, conf, pasta), conf)
    nomes = sorted(set(re.findall(r"[A-Za-z0-9_]*(?:send|draft|delete|reply|forward|move|create|update)[A-Za-z0-9_]*",
                                  s.texto if s else "", re.I)))
    linha("M6", "codex", rc, s, seg, f"nomes_de_escrita_no_texto={nomes}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", default="M1,M2,M3,M4,M5,M6")
    casos = [c.strip().upper() for c in ap.parse_args().casos.split(",") if c.strip()]
    conf = delegada.carregar()
    raiz = Path(tempfile.mkdtemp(prefix="vard-medicao-"))
    repo = subprocess.run(["git", "-C", str(raiz), "rev-parse"], capture_output=True, text=True)
    if repo.returncode == 0:
        print(f"ERRO: {raiz} está dentro de um repositório git", flush=True)
        return 2
    print(f"raiz={raiz} (fora de repositório git) saida={SAIDA}", flush=True)
    feitos = {"M1": m1, "M2": m2, "M3": m3, "M4": m4, "M5": m5, "M6": m6}
    for c in casos:
        r = feitos[c](conf, raiz)
        if c == "M2" and r:
            print("ALERTA: um arquivo prova-<agente>.txt foi criado; parando.", flush=True)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
