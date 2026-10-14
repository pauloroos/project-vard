"""Prova da oficina de ponta a ponta (Tarefa 7 do plano 3). Com a Vard no ar e o Orca aberto:

    uv run python scripts/provas/prova-oficina.py [--ferramenta codex|opencode|claude|agy] [--ponte]

1. Dispara uma tarefa trivial no próprio rdl-vard pela ferramenta MCP da oficina (ou, com --ponte, pede à Vard
   pelo /ask, que depende do Gemma escolher a ferramenta).
2. Escuta o SSE da ponte e espera a vigia (até 20 min): `terminou` ou `esperando` (o agente parado na pergunta de
   confiança da pasta é o caso esperado quando o usuário ainda não confiou no pai dos worktrees).
3. Confere que o aviso saiu UMA vez só (SSE + Telegram, pelo vigia.log), descarta com confirmação e
   confere que o worktree sumiu e que o git do rdl-vard está limpo. O branch da tarefa é apagado se não tem commits.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]   # raiz do repositório (o git da prova é este)
sys.path.insert(0, str(RAIZ / "nucleo"))     # pacote vard, para rodar fora do venv do uv

from vard import mesa_cliente, tarefas  # noqa: E402
from vard.oficina import ErroGit, git  # noqa: E402
from vard.segredos import PASTA  # noqa: E402

PONTE = "http://127.0.0.1:4700"
PEDIDO = ("criar o arquivo tests/test_trivial.py com um teste que confere 1 + 1 == 2, rodar "
          "uv run pytest tests/test_trivial.py e fazer commit.")
LIMITE_S = 20 * 60


def ouvir_eventos(eventos: list[dict], parar: threading.Event) -> None:
    try:
        with httpx.stream("GET", f"{PONTE}/events", timeout=httpx.Timeout(10, read=None), trust_env=False) as r:
            nome = ""
            for linha in r.iter_lines():
                if parar.is_set():
                    return
                if linha.startswith("event: "):
                    nome = linha[len("event: "):]
                elif linha.startswith("data: ") and nome == "oficina":
                    eventos.append(json.loads(linha[len("data: "):]))
    except (httpx.HTTPError, ValueError):
        return


def ferramenta(nome: str, **args) -> str:
    return mesa_cliente.chamar_ferramenta(nome, args, script="oficina_mcp.py", timeout=180)


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ferramenta", default="codex", choices=("codex", "opencode", "claude", "agy"))
    ap.add_argument("--ponte", action="store_true", help="pede pelo /ask em vez de chamar a ferramenta MCP")
    a = ap.parse_args()
    status_antes = git(str(RAIZ), "status", "--porcelain")      # a prova não pode mudar o git do rdl-vard
    antes = max((t.n for t in tarefas.listar()), default=0)
    eventos: list[dict] = []
    parar = threading.Event()
    threading.Thread(target=ouvir_eventos, args=(eventos, parar), daemon=True).start()
    time.sleep(1)
    if a.ponte:
        texto = f"Use a ferramenta disparar_tarefa com ferramenta {a.ferramenta}, repo rdl-vard e o pedido: {PEDIDO}"
        r = httpx.post(f"{PONTE}/ask", json={"texto": texto}, timeout=120, trust_env=False)
        print("Vard:", str(r.json().get("resposta", r.text))[:200])
    else:
        print("Oficina:", ferramenta("disparar_tarefa", ferramenta=a.ferramenta, repo="rdl-vard", pedido=PEDIDO))
    novas = [t for t in tarefas.listar() if t.n > antes and t.ferramenta == a.ferramenta]
    if not novas:
        print("FALHOU: a tarefa não foi disparada.")
        return 1
    n = novas[0].n
    print(f"Tarefa {n} disparada; esperando a vigia (até 20 min)...")
    fim = time.monotonic() + LIMITE_S
    t = tarefas.obter(n)
    while time.monotonic() < fim:
        t = tarefas.obter(n)
        if t.estado in ("terminou", "esperando", "falhou") and t.avisado == t.estado:
            break
        time.sleep(10)
    print(f"Estado: {t.estado} ({t.resumo}) bloqueio={t.bloqueio!r}")
    if t.estado not in ("terminou", "esperando"):
        print("FALHOU: a tarefa nem terminou nem parou numa pergunta; veja a aba no Orca.")
        return 1
    time.sleep(35)      # tempo de a vigia repetir (30 s) e provar que o aviso não duplica
    ok_sse = any(e.get("n") == n and e.get("estado") == t.estado for e in eventos)
    log = (PASTA / "logs" / "vigia.log").read_text(encoding="utf-8", errors="replace")
    marca = f"aviso n={n} estado={t.estado} ponte=True telegram=True"
    vezes = log.count(marca)
    print(f"Evento no SSE: {ok_sse}; avisos ponte+Telegram no vigia.log: {vezes} (esperado 1)")
    print(ferramenta("resultado_tarefa", n=n))
    # Sem trabalho não aprovado, descartar não pede confirmação; com trabalho, o 1º pede e o 2º (confirmado) remove.
    print(ferramenta("descartar_tarefa", n=n))
    print(ferramenta("descartar_tarefa", n=n, confirmado=True))
    t = tarefas.obter(n)
    # O `worktree rm` responde antes de a pasta sumir do disco quando o agente (agy) ainda solta arquivos ao fechar.
    prazo = time.monotonic() + 30
    while Path(t.caminho).exists() and time.monotonic() < prazo:
        time.sleep(1)
    sumiu = not Path(t.caminho).exists()
    limpo = git(str(RAIZ), "status", "--porcelain") == status_antes
    try:
        if t.branch and not git(str(RAIZ), "log", "--oneline", f"main..{t.branch}"):
            git(str(RAIZ), "branch", "-D", t.branch)           # sem commits: lixo da prova
    except ErroGit:
        pass                                                   # o branch já saiu junto com o worktree
    print(f"Estado final: {t.estado}; worktree removido: {sumiu}; git status igual ao de antes: {limpo}")
    parar.set()
    ok = ok_sse and vezes == 1 and t.estado == "descartada" and sumiu and limpo
    print("PROVA OK" if ok else "PROVA FALHOU")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
