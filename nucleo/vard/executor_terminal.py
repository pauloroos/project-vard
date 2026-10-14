"""Executor "terminal" da oficina: a mesma interface do Orca, feita com git e processos do Windows.

A oficina (vard/oficina.py) fala com um objeto `orca` (vard/orca_cli.Orca). Esta classe tem a MESMA
interface pública para o mesmo trabalho, sem depender do orca.exe:
- criar_worktree: `git worktree add -b <nome> <repo>/<nome>` a partir do HEAD do repo;
- criar_terminal: janela NOVA e VISÍVEL do powershell que entra no worktree, roda o comando do agente
  (uma linha só, sem "; exit") e grava TODA a saída (stdout+stderr) em <PASTA>/logs/oficina-<n>.log via
  `| Tee-Object -FilePath`; o pedido vai pelo -EncodedCommand (UTF-16LE em base64) para chegar intacto,
  com aspas e acentos;
- esperar "exit": o processo do handle morreu ou o pid foi reaproveitado (o create_time mudou); não há
  TUI, então "tui-idle" nunca é satisfeita;
- ler/ler_tela: o log em bytes (utf-8, ou UTF-16 com BOM que é o que o Tee-Object do PowerShell 5 grava);
- enviar: recusado — a janela é só de leitura; a resposta do usuário vem por outra tarefa;
- fechar_terminal: mata o processo e os filhos, só se o create_time do handle ainda bate;
- remover_worktree: `git worktree remove` (o repo sai do git-common-dir do próprio worktree); o branch fica.
Handle = "term:<pid>:<create_time>:<caminho do log>". O construtor aceita `popen`, `agora` e `pasta_logs`
para os testes não abrirem janela nem esperarem relógio de verdade.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import psutil

from vard.orca_cli import ErroOrca, Leitura
from vard.segredos import PASTA

JANELA_NOVA = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PASSO_MS = 50
LINHAS_TELA = 120


def _nova_janela(args: list[str]):
    # PWD/OLDPWD de um Git Bash fazem o OpenCode (Bun) achar que a pasta de trabalho é a de quem abriu a janela.
    env = {k: v for k, v in os.environ.items() if k not in ("PWD", "OLDPWD")}
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, creationflags=JANELA_NOVA, env=env)


def _caminho(ref: str) -> str:
    """"id:term::<caminho>", "term::<caminho>" ou "path:<caminho>" -> "<caminho>"."""
    s = str(ref).removeprefix("id:").removeprefix("path:").removeprefix("term::")
    if not s:
        raise ErroOrca("worktree_invalido", f"sem caminho no identificador {ref!r}")
    return s


def _lit(texto) -> str:
    """Literal PowerShell entre aspas simples (aspas simples, inclusive as curvas, são dobradas)."""
    t = re.sub("[‘’‚‛]", "'", str(texto))
    return "'" + t.replace("'", "''") + "'"


def _criacao(pid: int) -> float:
    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.Error, ValueError, TypeError):
        return 0.0


def _vivo(pid: int, criacao: float) -> bool:
    try:
        return abs(psutil.Process(pid).create_time() - criacao) < 1e-3   # pid reaproveitado: create_time muda
    except psutil.Error:
        return False


def _decodificar(bom: bytes, trecho: bytes) -> str:
    """O Tee-Object do PowerShell 5 grava UTF-16 com BOM; o resto do mundo escreve utf-8."""
    if bom.startswith((b"\xff\xfe", b"\xfe\xff")):
        if trecho.startswith((b"\xff\xfe", b"\xfe\xff")):
            return trecho.decode("utf-16", errors="replace")             # trecho de fora do BOM: ele consome
        if len(trecho) % 2:
            trecho = trecho[:-1]                                         # nunca cortar caractere UTF-16 no meio
        return trecho.decode("utf-16-be" if bom.startswith(b"\xfe\xff") else "utf-16-le", errors="replace")
    texto = trecho.decode("utf-8", errors="replace")
    return texto[1:] if texto.startswith("﻿") else texto


class TerminalLocal:
    """Mesma interface da oficina que a classe Orca: git + janela visível do powershell, sem orca.exe."""

    e_terminal = True                     # a oficina troca o montar_comando pelo montar_comando_terminal

    def __init__(self, popen: Callable[[list[str]], object] | None = None,
                 agora: Callable[[], float] | None = None,
                 pasta_logs: Path | str | None = None):
        self._popen = popen or _nova_janela
        self._agora = agora or time.monotonic
        self.pasta_logs = Path(pasta_logs) if pasta_logs is not None else PASTA / "logs"

    def status(self) -> dict:
        return {"executor": "terminal"}

    def repos(self) -> list[str]:
        return []

    def criar_worktree(self, repo_caminho: str, nome: str) -> dict:
        repo = str(repo_caminho).replace("\\", "/").rstrip("/")
        destino = f"{repo}/{nome}"
        self._git(repo, "worktree", "add", "-b", nome, destino, timeout=180)
        return {"worktree": f"term::{destino}", "caminho": destino, "branch": nome}

    def criar_terminal(self, worktree: str, comando: str, titulo: str, shell: str = "") -> str:
        caminho = _caminho(worktree)
        n = re.search(r"#(\d+)", titulo)
        if not n:
            raise ErroOrca("titulo_invalido", f"sem número no título {titulo!r}")
        log = self.pasta_logs / f"oficina-{n.group(1)}.log"
        try:
            self.pasta_logs.mkdir(parents=True, exist_ok=True)
            log.write_bytes(b"")                       # a leitura começa em 0: sobra de tarefa velha não polui
        except OSError as exc:
            raise ErroOrca("log_inacessivel", f"{type(exc).__name__}: {log}") from exc
        # Uma linha só: o pedido vai inteiro pelo -EncodedCommand (nunca por concatenação de shell).
        script = (f"[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
                  f"Set-Location -LiteralPath {_lit(caminho)} -ErrorAction Stop; {comando} 2>&1 | Tee-Object -FilePath {_lit(log)}")
        codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            proc = self._popen([shell or "powershell.exe", "-NoProfile", "-OutputFormat", "Text", "-EncodedCommand", codificado])
        except OSError as exc:
            raise ErroOrca("janela_inacessivel", f"{type(exc).__name__}") from exc
        pid = int(getattr(proc, "pid", 0) or 0)
        return f"term:{pid}:{_criacao(pid)}:{log}"

    def esperar(self, terminal: str, condicao: str, timeout_ms: int) -> tuple[bool, str]:
        if condicao != "exit":
            return False, ""                            # não há TUI no modo terminal
        try:
            pid, criacao, _ = _info(terminal)
        except ErroOrca:
            return True, ""                             # handle nem existe mais: já saiu
        fim = self._agora() + max(timeout_ms, 0) / 1000
        while True:
            if not _vivo(pid, criacao):
                return True, ""
            resto = fim - self._agora()
            if resto <= 0:
                return False, ""
            time.sleep(min(PASSO_MS / 1000, resto))

    def ler(self, terminal: str, cursor: int | None = None, limite: int = 400) -> Leitura:
        _, _, log = _info(terminal)
        try:
            dados = Path(log).read_bytes()
        except OSError:
            return Leitura("", cursor)
        inicio = 0 if cursor is None else max(0, min(int(cursor), len(dados)))
        if dados[:2] in (b"\xff\xfe", b"\xfe\xff") and inicio % 2:
            inicio += 1                                 # cursor em par: não começar no meio de um caractere
        texto = _decodificar(dados[:4], dados[inicio:])
        linhas = texto.splitlines()
        return Leitura("\n".join(linhas[-limite:]), len(dados)) if limite else Leitura("", len(dados))

    def ler_tela(self, terminal: str) -> str:
        return self.ler(terminal, cursor=0, limite=LINHAS_TELA).texto

    def enviar(self, terminal: str, texto: str) -> None:
        raise ErroOrca("sem_entrada", "no modo terminal a janela é só de leitura; responda pelo agente em outra tarefa")

    def fechar_terminal(self, terminal: str) -> None:
        try:
            pid, criacao, _ = _info(terminal)
            proc = psutil.Process(pid)
        except (ErroOrca, psutil.Error):
            return                                      # handle inválido ou terminal já morto
        try:
            if abs(proc.create_time() - criacao) >= 1e-3:
                return                                  # pid reaproveitado: não mato o inocente
            mortos = proc.children(recursive=True) + [proc]
        except psutil.Error:
            return                                      # morreu entre uma chamada e outra
        for p in mortos:
            try:
                p.terminate()
            except psutil.Error:
                pass
        _, restantes = psutil.wait_procs(mortos, timeout=5)
        for p in restantes:
            try:
                p.kill()
            except psutil.Error:
                pass

    def remover_worktree(self, worktree: str, forcar: bool = False) -> None:
        raiz = Path(_caminho(worktree))
        comum = self._git(str(raiz), "rev-parse", "--git-common-dir")
        # O repo sai do próprio worktree; o remove roda de fora (de dentro o git não consegue apagar a pasta).
        self._git(comum if os.path.isabs(comum) else os.path.join(str(raiz), comum), "worktree", "remove",
                  *(("--force",) if forcar else ()), str(raiz), timeout=180)
        if forcar:
            shutil.rmtree(raiz, ignore_errors=True)    # arquivo preso derrubou o remove: a pasta some mesmo assim

    def _git(self, caminho: str, *args: str, timeout: float = 60) -> str:
        try:
            p = subprocess.run(["git", "-C", caminho, *args], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ErroOrca("git_worktree", f"git {args[0] if args else ''}: {type(exc).__name__}") from exc
        if p.returncode != 0:
            linhas = (p.stderr or p.stdout).strip().splitlines()
            raise ErroOrca("git_worktree", (linhas[0] if linhas else f"saiu com {p.returncode}")[:160])
        return p.stdout.strip()


def _info(terminal: str) -> tuple[int, float, str]:
    """Handle "term:<pid>:<create_time>:<log>" -> (pid, create_time, log)."""
    partes = str(terminal).split(":", 3)
    if len(partes) != 4 or partes[0] != "term":
        raise ErroOrca("terminal_stale", "handle de terminal inválido")
    try:
        return int(partes[1]), float(partes[2]), partes[3]
    except ValueError:
        raise ErroOrca("terminal_stale", "handle de terminal inválido") from None
