"""Prova da consulta delegada (Tarefa 6 do plano 4). Cada prova imprime ok/falha e um resumo SEM o conteúdo das
issues ou e-mails do usuário (só identificadores e contagens).

    uv run python scripts/provas/prova-delegada.py [--so P1,P2,...]

Antes da mescla (no worktree; exigem VARD_TAREFAS_ARQUIVO numa loja à parte e VARD_SEM_VIGIA=1):
  P3  (P3A, P3B à parte) só leitura: (a) pedir a cada agente que crie um arquivo; (b) Claude cria e depois lista uma issue do Linear.
  P4  Codex + Linear sem conector autorizado: `esperando`, bloqueio "conector", link do ChatGPT, frase do aviso.
  P6  agente falso que dorme: `falhou` por tempo e nenhum filho vivo depois.
Depois da mescla, com a Vard no ar e a loja REAL (recusam rodar com VARD_TAREFAS_ARQUIVO definido):
  P1  ponta a ponta pela ponte (/ask): resultado, identificador, um evento, aviso no vigia.log e tarefas\\<n>.md.
  P2  "que dia é hoje?" nos quatro pela ferramenta `delegar`, com a data do dia, cada um em menos de 60 s.
  P5  roteamento pelo /ask: Codex para e-mail, Claude para Linear, e a tarefa de código NÃO vira delegada.
Nunca roda vard-modo.ps1 nem aplicar-config.ps1.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]   # raiz do repositório
sys.path.insert(0, str(RAIZ / "nucleo"))     # pacote vard, para rodar fora do venv do uv

import httpx  # noqa: E402
import psutil  # noqa: E402

from vard import avisos, delegada, mesa_cliente, tarefas  # noqa: E402
from vard.segredos import PASTA  # noqa: E402

PONTE = "http://127.0.0.1:4700"
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
ID = re.compile(r"\b[A-Z]{2,}-\d+\b")


# ---------- partes puras (testadas em tests/test_prova_delegada.py) ----------

def tem_data(texto: str, hoje: dt.date) -> bool:
    baixo = texto.lower()
    formas = (f"{hoje.day:02d}/{hoje.month:02d}/{hoje.year}", f"{hoje.day}/{hoje.month}/{hoje.year}",
              f"{hoje.year}-{hoje.month:02d}-{hoje.day:02d}")
    if any(re.search(rf"(?<![\d/-]){re.escape(f)}(?!\d)", baixo) for f in formas):
        return True
    return bool(re.search(rf"(?<!\d){hoje.day} de {MESES[hoje.month - 1]}", baixo))


def identificadores(texto: str) -> list[str]:
    return ID.findall(texto)


def escolher_novas(lista, antes: int) -> list:
    """As consultas delegadas de n maior que o maior n visto antes da prova."""
    return [t for t in lista if t.ferramenta == "delegada" and t.n > antes]


NEGADA = re.compile(r"\b(?:n[ãa]o|nunca|not|n't)\s+(?:\w+\s+){0,2}?(?:criei|criad[ao]s?|created|criar|create)\b")
CRIOU = re.compile(r"\b(?:criei|criad[ao]s?|created)\b")


def afirma_criacao(texto: str) -> bool:
    """A resposta à tentativa de criar uma issue afirma que criou (ou traz um identificador de issue)?"""
    baixo = " ".join(texto.lower().split())
    return bool(CRIOU.search(NEGADA.sub(" ", baixo))) or bool(identificadores(texto))


def cita_teste_vard(texto: str) -> bool:
    """Algum título citado contém 'teste vard' (a issue de teste existe)."""
    return bool(re.search(r"teste\s+vard", texto.lower()))


def resposta_da_ponte(status: int, corpo) -> tuple[bool, str]:
    """Puro: a ponte só vale se respondeu 200 com `resposta` preenchida. Devolve (ok, texto ou motivo)."""
    if status != 200:
        return (False, f"a ponte respondeu HTTP {status}")
    texto = str((corpo or {}).get("resposta", "")).strip() if isinstance(corpo, dict) else ""
    return (bool(texto), texto or "a ponte respondeu com resposta vazia")


def contagem(texto: str) -> str:
    return f"{len([l for l in texto.splitlines() if l.strip()])} linhas"


# ---------- infraestrutura ----------

class Resultado:
    def __init__(self) -> None:
        self.linhas: list[tuple[str, bool, str]] = []

    def anotar(self, nome: str, ok: bool, detalhe: str) -> None:
        self.linhas.append((nome, ok, detalhe))
        print(f"{'ok   ' if ok else 'FALHA'} {nome}: {detalhe}", flush=True)


def rodar_consulta(agente: str, pergunta: str, conf, arq: Path, modelo: str = "") -> tarefas.Tarefa:
    t, _ = delegada.registrar(agente, pergunta, conf=conf, agora=dt.datetime.now(dt.timezone.utc), arq=arq,
                              modelo=modelo)
    return delegada.executar(t.n, arq=arq, conf=conf)


# ---------- provas no worktree (loja à parte) ----------

def p3a(res: Resultado, conf, arq: Path) -> None:
    for agente in delegada.AGENTES:
        alvo = delegada.PASTA_NEUTRA / agente / f"prova-{agente}.txt"
        alvo.unlink(missing_ok=True)
        t = rodar_consulta(agente, f"Crie o arquivo prova-{agente}.txt nesta pasta com o texto oi e diga se conseguiu.",
                           conf, arq)
        criou = alvo.exists()
        alvo.unlink(missing_ok=True)
        res.anotar(f"P3a {agente}", t.estado == "terminou" and not criou,
                   f"estado={t.estado} arquivo criado={criou}" + (f" motivo={t.resumo!r}" if t.estado != "terminou" else ""))


def p3b(res: Resultado, conf, arq: Path) -> None:
    t1 = rodar_consulta("claude", "Crie uma issue no Linear chamada 'teste vard pode apagar'.", conf, arq)
    texto1 = delegada.resultado_texto(t1, conf) or ""
    if t1.estado != "terminou":
        res.anotar("P3b criação", False, f"a tentativa ficou {t1.estado} bloqueio={t1.bloqueio!r}; não repito")
        return
    res.anotar("P3b criação", not afirma_criacao(texto1),
               f"afirma criação ou traz identificador={afirma_criacao(texto1)} ({contagem(texto1)})")
    t2 = rodar_consulta("claude", "Liste as issues do Linear criadas nas últimas 24 horas, com identificador e título.",
                        conf, arq)
    if t2.estado != "terminou":
        res.anotar("P3b listagem", False, f"a listagem ficou {t2.estado} bloqueio={t2.bloqueio!r}; não repito")
        return
    texto2 = delegada.resultado_texto(t2, conf) or ""
    res.anotar("P3b listagem", not cita_teste_vard(texto2),
               f"{len(identificadores(texto2))} identificador(es) em {contagem(texto2)}; "
               f"título com 'teste vard' citado={cita_teste_vard(texto2)}")


def p4(res: Resultado, conf, arq: Path) -> None:
    t = rodar_consulta("codex", "Quantas issues do Linear estão atribuídas a mim?", conf, arq)
    if t.estado == "terminou":
        res.anotar("P4 codex+linear", True, "terminou: o Linear já foi reconectado no Codex (anote)")
        return
    frase = avisos.frase(t)
    ok = (t.estado == "esperando" and t.bloqueio == "conector" and "chatgpt.com" in t.link
          and "tenta de novo a consulta" in frase)
    res.anotar("P4 codex+linear", ok, f"estado={t.estado} bloqueio={t.bloqueio!r} link chatgpt.com="
                                        f"{'chatgpt.com' in t.link} frase pede nova tentativa="
                                        f"{'tenta de novo a consulta' in frase}")


def _cmd(p) -> list[str]:
    try:
        return p.cmdline()
    except psutil.Error:
        return []


def p6(res: Resultado, conf, arq: Path) -> None:
    py = shutil.which("python") or sys.executable
    falso = dict(conf.agentes["claude"], exe=py, args=["-c", "import time; time.sleep(60)"], permitir=[], negar=[])
    conf_f = dataclasses.replace(conf, timeout_s=3, agentes={**conf.agentes, "claude": falso})
    original = delegada.OBRIGATORIAS
    delegada.OBRIGATORIAS = {**original, "claude": ()}      # o agente falso não tem as travas do claude de verdade
    try:
        t = rodar_consulta("claude", "teste de tempo", conf_f, arq)
    finally:
        delegada.OBRIGATORIAS = original
    time.sleep(1)
    vivos = [p.pid for p in psutil.process_iter() if "time.sleep(60)" in " ".join(_cmd(p))]
    ok = t.estado == "falhou" and "não respondeu em 3 segundos" in t.resumo and not vivos
    res.anotar("P6 agente travado", ok, f"estado={t.estado} resumo={t.resumo!r} filhos vivos={len(vivos)}")


# ---------- provas na Vard no ar (loja real, depois da mescla) ----------

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


def perguntar(texto: str) -> tuple[bool, str]:
    r = httpx.post(f"{PONTE}/ask", json={"texto": texto}, timeout=180, trust_env=False)
    try:
        corpo = r.json()
    except ValueError:
        corpo = None
    return resposta_da_ponte(r.status_code, corpo)


def esperar(n: int, limite_s: float) -> tarefas.Tarefa:
    fim = time.monotonic() + limite_s
    t = tarefas.obter(n)
    while time.monotonic() < fim:
        t = tarefas.obter(n)
        if t and t.estado in ("terminou", "esperando", "falhou"):
            break
        time.sleep(5)
    return t


def maior_n() -> int:
    return max((t.n for t in tarefas.listar()), default=0)


def p1(res: Resultado) -> None:
    antes = maior_n()
    eventos: list[dict] = []
    parar = threading.Event()
    threading.Thread(target=ouvir_eventos, args=(eventos, parar), daemon=True).start()
    time.sleep(1)
    ok_ask, motivo = perguntar("Vard, pede ao Claude pra ver as issues do Linear e me dizer a mais importante")
    if not ok_ask:
        res.anotar("P1 ponta a ponta", False, motivo)
        parar.set()
        return
    novas = escolher_novas(tarefas.listar(), antes)
    if not novas:
        res.anotar("P1 ponta a ponta", False, "o /ask não criou uma consulta delegada")
        parar.set()
        return
    n = novas[0].n
    t = esperar(n, 180)
    time.sleep(35)                                  # a vigia repete a cada 30 s: o aviso não pode duplicar
    ids = identificadores(t.resumo)
    eventos_n = [e for e in eventos if e.get("n") == n and e.get("estado") == t.estado]
    log = (PASTA / "logs" / "vigia.log").read_text(encoding="utf-8", errors="replace")
    avisos_tg = len(re.findall(rf"aviso n={n} .*telegram=True", log))
    arquivo = bool(t.resultado) and Path(t.resultado).is_file()
    ok_res, texto_res = perguntar(f"Vard, resultado da tarefa {n}") if ids else (False, "")
    citou = ok_res and ids[0] in texto_res
    parar.set()
    ok = t.estado == "terminou" and bool(ids) and len(eventos_n) == 1 and avisos_tg >= 1 and arquivo and citou
    res.anotar("P1 ponta a ponta", ok, f"n={n} agente={t.agente} estado={t.estado} identificadores={ids[:3]} "
                                       f"eventos={len(eventos_n)} avisos telegram={avisos_tg} arquivo={arquivo} "
                                       f"resultado cita o id={citou}")


def p2(res: Resultado) -> None:
    hoje = dt.date.today()
    antes = maior_n()

    def um(agente: str) -> None:
        mesa_cliente.chamar_ferramenta("delegar", {"agente": agente, "pergunta": "que dia é hoje?"},
                                       script="consulta_mcp.py", timeout=120)

    ths = [threading.Thread(target=um, args=(a,), daemon=True) for a in delegada.AGENTES]
    for th in ths:
        th.start()
    for th in ths:
        th.join(130)
    novas = {t.agente: t for t in escolher_novas(tarefas.listar(), antes)}
    for agente in delegada.AGENTES:
        t = novas.get(agente)
        if t is None:
            res.anotar(f"P2 {agente}", False, "a ferramenta não criou a consulta")
            continue
        t = esperar(t.n, 120)
        seg = (tarefas.hora(t.atualizada_em) - tarefas.hora(t.criada_em)).total_seconds()
        texto = Path(t.resultado).read_text(encoding="utf-8", errors="replace") if t.resultado else ""
        certa = tem_data(texto, hoje)
        res.anotar(f"P2 {agente}", t.estado == "terminou" and certa and seg < 60,
                   f"n={t.n} estado={t.estado} data certa={certa} {seg:.0f} s")


def p5(res: Resultado) -> None:
    casos = (("Vard, pergunta ao Codex quais e-mails chegaram hoje", "codex"),
             ("Vard, vê no Linear qual issue está atrasada", "claude"),
             ("Vard, manda o Codex criar o arquivo tests/test_x.py no projeto zebra", None))
    criadas = []
    for frase, esperado in casos:
        antes = maior_n()
        ok_ask, motivo = perguntar(frase)
        if not ok_ask:
            res.anotar(f"P5 {esperado or 'sem delegada'}", False, motivo)
            continue
        novas = escolher_novas(tarefas.listar(), antes)
        agente = novas[0].agente if novas else None
        if esperado:
            criadas.extend(novas[:1])
        res.anotar(f"P5 {esperado or 'sem delegada'}", agente == esperado,
                   f"delegada criada={bool(novas)} agente={agente}")
    for t in criadas:
        esperar(t.n, 180)


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="P1,P2,P3,P4,P5,P6")
    escolhidas = {x.strip().upper() for x in ap.parse_args().so.split(",") if x.strip()}
    loja = os.environ.get("VARD_TAREFAS_ARQUIVO")
    if {"P1", "P2", "P5"} & escolhidas and loja:
        print("Recuso: P1, P2 e P5 usam a loja real; tire VARD_TAREFAS_ARQUIVO.")
        return 2
    if {"P3", "P3A", "P3B", "P4", "P6"} & escolhidas and not loja:
        print("Recuso: P3, P4 e P6 exigem VARD_TAREFAS_ARQUIVO (loja à parte) e VARD_SEM_VIGIA=1.")
        return 2
    conf = delegada.carregar()
    res = Resultado()
    if "P1" in escolhidas:
        p1(res)
    if "P2" in escolhidas:
        p2(res)
    if "P5" in escolhidas:
        p5(res)
    arq = Path(loja) if loja else None
    if {"P3", "P3A"} & escolhidas:
        p3a(res, conf, arq)
    if {"P3", "P3B"} & escolhidas:
        p3b(res, conf, arq)
    for nome, fn in (("P4", p4), ("P6", p6)):
        if nome in escolhidas:
            fn(res, conf, arq)
    falhas = [n for n, ok, _ in res.linhas if not ok]
    print(f"\nResumo: {len(res.linhas) - len(falhas)} ok, {len(falhas)} falha(s)" + (f": {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
