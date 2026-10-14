"""Cliente fino da CLI do Orca (orca.exe): subprocess + JSON, sem regra da oficina.

Flags conferidas em 12/10 com `orca <comando> --help` (Orca 1.4.224). Todo comando vai com --json;
a resposta é {"ok": true, "result": {...}} ou {"ok": false, "error": {"code", "message"}}.
Formatos reais em tests/fixtures/orca/ (Tarefa 1, passo 1). O que a fixture mostrou e o plano não previa:
- worktree create devolve result.worktree.{id, path, branch}; o id é "<repoId>::<caminho>" (não há `worktreeId`);
- terminal wait só devolve erro (ok:false, code "timeout") em timeout de fato; com ok:true o resultado
  está em result.wait.satisfied (false = não aconteceu; rc 1 do processo), com blockedReason quando o agente
  está parado numa pergunta de confiança da pasta;
- terminal que já morreu: code "terminal_handle_stale".
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

EXE_PADRAO = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "orca" / "resources" / "bin" / "orca.exe"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

Executor = Callable[[list[str], float], tuple[int, str, str]]


class ErroOrca(Exception):
    def __init__(self, codigo: str, mensagem: str = ""):
        super().__init__(f"{codigo}: {mensagem}" if mensagem else codigo)
        self.codigo = codigo
        self.mensagem = mensagem

    @property
    def e_timeout(self) -> bool:
        return "timeout" in self.codigo.lower() or "timed out" in self.mensagem.lower()

    @property
    def sumiu(self) -> bool:
        """O terminal (não qualquer coisa) não existe mais: handle velho, fechado ou desconhecido."""
        codigo, mensagem = self.codigo.lower(), self.mensagem.lower()
        if codigo.startswith("terminal") and any(p in codigo for p in ("not_found", "stale", "exited", "closed")):
            return True
        return any(p in mensagem for p in ("no such terminal", "unknown terminal", "terminal not found"))


def executar_real(args: list[str], timeout: float) -> tuple[int, str, str]:
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
    return p.returncode, p.stdout, p.stderr


def achar(dados: Any, chave: str) -> Any:
    """Primeiro valor de `chave` numa árvore de dicts e listas (o nível de cima primeiro)."""
    if isinstance(dados, dict):
        if chave in dados:
            return dados[chave]
        filhos = list(dados.values())
    elif isinstance(dados, list):
        filhos = dados
    else:
        return None
    for filho in filhos:
        achado = achar(filho, chave)
        if achado is not None:
            return achado
    return None


def todos(dados: Any, chave: str) -> list:
    achados: list = []
    if isinstance(dados, dict):
        for k, v in dados.items():
            if k == chave:
                achados.append(v)
            achados.extend(todos(v, chave))
    elif isinstance(dados, list):
        for v in dados:
            achados.extend(todos(v, chave))
    return achados


def _texto(tail: Any) -> str:
    if isinstance(tail, list):
        return "\n".join(str(l) for l in tail)
    return str(tail or "")


@dataclass
class Leitura:
    texto: str
    proximo: int | None


class Orca:
    def __init__(self, exe: Path | str | None = None, executar: Executor | None = None):
        self.exe = str(exe or os.environ.get("VARD_ORCA_EXE") or EXE_PADRAO)
        self._executar = executar or executar_real

    def _json(self, *args: str, timeout: float = 30) -> dict:
        try:
            rc, out, err = self._executar([self.exe, *args, "--json"], timeout)
        except FileNotFoundError as exc:
            raise ErroOrca("orca_ausente", self.exe) from exc
        except subprocess.TimeoutExpired as exc:
            raise ErroOrca("timeout_local", f"orca {' '.join(args[:2])} passou de {timeout:.0f} s") from exc
        except OSError as exc:
            raise ErroOrca("orca_inacessivel", f"{type(exc).__name__}: {exc}"[:200]) from exc
        try:
            dados = json.loads(out)
        except ValueError:
            raise ErroOrca("nao_json", (err or out).strip()[:200]) from None
        if not isinstance(dados, dict) or not dados.get("ok", rc == 0):
            erro = (dados.get("error") if isinstance(dados, dict) else None) or {}
            raise ErroOrca(str(erro.get("code", f"rc{rc}")), str(erro.get("message", ""))[:300])
        return dados.get("result") or {}

    def status(self) -> dict:
        return self._json("status")

    def repos(self) -> list[str]:
        return [str(p).replace("\\", "/") for p in todos(self._json("repo", "list"), "path")]

    def criar_worktree(self, repo_caminho: str, nome: str) -> dict:
        r = self._json("worktree", "create", "--name", nome, "--repo", f"path:{repo_caminho}", "--no-parent",
                       timeout=180)
        w = r.get("worktree") if isinstance(r.get("worktree"), dict) else {}
        wid = str(w.get("id") or achar(r, "worktreeId") or "")
        if "::" not in wid:
            raise ErroOrca("sem_worktree", "worktree create não devolveu o id do worktree")
        branch = str(w.get("branch") or "")
        if not branch:
            branch = str(achar(self._json("worktree", "show", "--worktree", f"id:{wid}"), "branch") or "")
        caminho = str(w.get("path") or wid.split("::", 1)[1]).replace("\\", "/")
        return {"worktree": wid, "caminho": caminho, "branch": branch.removeprefix("refs/heads/")}

    def criar_terminal(self, worktree: str, comando: str, titulo: str, shell: str = "") -> str:
        args = ["terminal", "create", "--worktree", worktree, "--command", comando, "--title", titulo]
        if shell:
            args += ["--shell", shell]
        handle = achar(self._json(*args, timeout=60), "handle")
        if not handle:
            raise ErroOrca("sem_handle", "terminal create não devolveu handle")
        return str(handle)

    def esperar(self, terminal: str, condicao: str, timeout_ms: int) -> tuple[bool, str]:
        """(satisfeita, bloqueio). satisfeita: a condição (exit | tui-idle) aconteceu. bloqueio: o motivo que o
        Orca dá quando o agente está parado numa pergunta (ex. "agent-trust-workspace",
        "agent-hooks-review-prompt"); vazio se não há. Tempo esgotado = (False, "")."""
        try:
            r = self._json("terminal", "wait", "--terminal", terminal, "--for", condicao,
                           "--timeout-ms", str(timeout_ms), timeout=timeout_ms / 1000 + 15)
        except ErroOrca as exc:
            if exc.e_timeout:
                return False, ""
            if exc.sumiu:
                return condicao == "exit", ""
            raise
        espera = r.get("wait") if isinstance(r.get("wait"), dict) else r
        return espera.get("satisfied") is True, str(espera.get("blockedReason") or "")

    def ler(self, terminal: str, cursor: int | None = None, limite: int = 400) -> Leitura:
        args = ["terminal", "read", "--terminal", terminal, "--limit", str(limite)]
        if cursor is not None:
            args += ["--cursor", str(cursor)]
        r = self._json(*args)
        proximo = achar(r, "nextCursor")
        try:
            cursor = int(proximo) if proximo is not None else None
        except (TypeError, ValueError):
            cursor = None
        return Leitura(_texto(achar(r, "tail")), cursor)

    def ler_tela(self, terminal: str) -> str:
        return _texto(achar(self._json("terminal", "read", "--terminal", terminal, "--screen"), "tail"))

    def enviar(self, terminal: str, texto: str) -> None:
        """Digita `texto` e Enter num agente. Recusa tecla solta: texto vazio ou com caractere de controle
        (Esc, setas, Enter puro). Essas teclas são o que responderia, às cegas, a uma pergunta de confiança
        da pasta ("Trust this folder?", "Hooks need review"): decisão de segurança que só o usuário toma, no
        Orca. Pergunta normal do agente (sim/não, y/n, 1) continua passando."""
        if not texto.strip() or any(ord(c) < 32 for c in texto):
            raise ErroOrca("entrada_recusada", "só mando texto de resposta, nunca tecla solta")
        self._json("terminal", "send", "--terminal", terminal, "--text", texto, "--enter", "--wait-submit", "10",
                   timeout=60)

    def fechar_terminal(self, terminal: str) -> None:
        self._json("terminal", "close", "--terminal", terminal, "--tab")

    def remover_worktree(self, worktree: str, forcar: bool = False) -> None:
        args = ["worktree", "rm", "--worktree", worktree]
        if forcar:
            args.append("--force")
        self._json(*args, timeout=180)
