from vard import executor
from vard.executor_terminal import TerminalLocal
from vard.orca_cli import ErroOrca


class OrcaBom:
    def status(self):
        return {"runtime": {"reachable": True}}


class OrcaQuebrado:
    def status(self):
        raise ErroOrca("orca_ausente", "sem orca")


class OrcaExplosivo:
    def status(self):
        raise RuntimeError("estranho")


def conf(modo: str) -> dict:
    return {"oficina": {"executor": modo}}


def test_auto_com_orca_respondendo_usa_o_orca():
    orca, terminal = OrcaBom(), TerminalLocal()
    assert executor.escolher(conf("auto"), orca=orca, terminal=terminal) is orca


def test_auto_com_orca_quebrando_usa_o_terminal():
    terminal = TerminalLocal()
    assert executor.escolher(conf("auto"), orca=OrcaQuebrado(), terminal=terminal) is terminal


def test_auto_com_falha_qualquer_usa_o_terminal():
    terminal = TerminalLocal()
    assert executor.escolher(conf("auto"), orca=OrcaExplosivo(), terminal=terminal) is terminal


def test_terminal_e_orca_explicitos():
    orca, terminal = OrcaBom(), TerminalLocal()
    assert executor.escolher(conf("terminal"), orca=orca, terminal=terminal) is terminal
    assert executor.escolher(conf("orca"), orca=orca, terminal=terminal) is orca


def test_valor_desconhecido_e_conf_vazia_como_auto():
    orca, terminal = OrcaBom(), TerminalLocal()
    assert executor.escolher(conf("sei-la"), orca=orca, terminal=terminal) is orca
    assert executor.escolher(None, orca=OrcaQuebrado(), terminal=terminal) is terminal
    assert executor.escolher({}, orca=OrcaQuebrado(), terminal=terminal) is terminal


class _Falso:
    def __init__(self, nome, terminal=False):
        self.nome, self.e_terminal, self.chamadas = nome, terminal, []

    def __getattr__(self, m):
        def f(*a, **k):
            self.chamadas.append(m)
            return (False, "") if m == "esperar" else self.nome
        return f


def test_roteador_manda_cada_handle_ao_seu_executor():
    from vard.executor import Roteador
    o, t = _Falso("orca"), _Falso("term", True)
    r = Roteador({"oficina": {"executor": "orca"}}, orca=o, terminal=t)
    assert r.criar_worktree("p", "n") == "orca" and not r.e_terminal
    r.esperar("term:1:2:x", "exit", 10)
    r.fechar_terminal("abc-orca-handle")
    r.remover_worktree("id:term::X:/x")
    r.remover_worktree("id:uuid::X:/y")
    assert t.chamadas == ["esperar", "remover_worktree"] and o.chamadas == ["criar_worktree", "fechar_terminal", "remover_worktree"]


def test_roteador_tarefa_nova_segue_a_config():
    from vard.executor import Roteador
    r = Roteador({"oficina": {"executor": "terminal"}}, orca=_Falso("orca"), terminal=_Falso("term", True))
    assert r.e_terminal and r.criar_worktree("p", "n") == "term"
