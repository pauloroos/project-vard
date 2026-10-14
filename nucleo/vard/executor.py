"""Escolhe o executor da oficina: o Orca se o CLI dele responder, senão o terminal local (vard/executor_terminal.py).

A seção [oficina] de config/oficina.toml manda: `executor = "auto"` (padrão), "orca" ou "terminal"; valor
desconhecido conta como "auto". Os parâmetros orca/terminal existem para os testes injetarem fakes.
"""
from __future__ import annotations

from vard import orca_cli
from vard.executor_terminal import TerminalLocal


def escolher(conf: dict | None = None, *, orca=None, terminal=None):
    modo = str(((conf or {}).get("oficina") or {}).get("executor", "auto"))
    if modo == "terminal":
        return terminal if terminal is not None else TerminalLocal()
    if modo == "orca":
        return orca if orca is not None else orca_cli.Orca()
    o = orca if orca is not None else orca_cli.Orca()
    try:
        o.status()
    except Exception:  # noqa: BLE001 — ErroOrca (CLI ausente ou fora do ar) ou qualquer outra surpresa: terminal
        return terminal if terminal is not None else TerminalLocal()
    return o


class Roteador:
    """Mesma interface do Orca e do TerminalLocal; cada chamada vai ao executor a que o handle ou o worktree pertence
    ("term:" e "term::" = terminal local; o resto = Orca). Tarefa nova usa o executor da config. Assim uma tarefa
    aberta no terminal continua observável se o Orca voltar a responder (e vice-versa)."""

    def __init__(self, conf: dict | None = None, *, orca=None, terminal=None):
        self._conf, self._orca, self._terminal = conf, orca, terminal
        self._novo = None

    def _o(self):
        if self._orca is None:
            self._orca = orca_cli.Orca()
        return self._orca

    def _t(self):
        if self._terminal is None:
            self._terminal = TerminalLocal()
        return self._terminal

    def _para_novo(self):
        if self._novo is None:
            self._novo = escolher(self._conf, orca=self._o() if self._orca is not None else None,
                                  terminal=self._t() if self._terminal is not None else None)
        return self._novo

    def _por(self, ref: str):
        r = str(ref)
        return self._t() if r.startswith(("term:", "id:term::", "term::")) else self._o()

    @property
    def e_terminal(self) -> bool:
        return bool(getattr(self._para_novo(), "e_terminal", False))

    def status(self) -> dict:
        return self._para_novo().status()

    def criar_worktree(self, repo_caminho, nome):
        return self._para_novo().criar_worktree(repo_caminho, nome)

    def criar_terminal(self, worktree, comando, titulo, shell=""):
        return self._por(worktree).criar_terminal(worktree, comando, titulo, shell)

    def esperar(self, terminal, condicao, timeout_ms):
        return self._por(terminal).esperar(terminal, condicao, timeout_ms)

    def ler(self, terminal, cursor=None, limite=400):
        return self._por(terminal).ler(terminal, cursor, limite)

    def ler_tela(self, terminal):
        return self._por(terminal).ler_tela(terminal)

    def enviar(self, terminal, texto):
        return self._por(terminal).enviar(terminal, texto)

    def fechar_terminal(self, terminal):
        return self._por(terminal).fechar_terminal(terminal)

    def remover_worktree(self, worktree, forcar=False):
        return self._por(worktree).remover_worktree(worktree, forcar)


def roteador(conf: dict | None = None, **kw) -> Roteador:
    return Roteador(conf, **kw)
