import json
import subprocess
from pathlib import Path

import pytest

from vard import orca_cli
from vard.orca_cli import ErroOrca, Orca

FX = Path(__file__).resolve().parent / "fixtures" / "orca"


def executor(respostas: dict):
    """respostas: "<cmd> <sub>" -> (rc, corpo dict ou texto). Guarda as chamadas."""
    chamadas = []

    def executar(args, timeout):
        chamadas.append(args)
        rc, corpo = respostas[" ".join(args[1:3])]
        return rc, corpo if isinstance(corpo, str) else json.dumps(corpo), ""

    executar.chamadas = chamadas
    return executar


def ok(result):
    return 0, {"id": "x", "ok": True, "result": result}


def test_todo_comando_vai_com_json_e_o_exe():
    ex = executor({"status --json": ok({"runtime": {"reachable": True}})})
    assert Orca(exe="X:/orca.exe", executar=ex).status()["runtime"]["reachable"] is True
    assert ex.chamadas[0] == ["X:/orca.exe", "status", "--json"]


def test_erro_do_orca_vira_ErroOrca_com_codigo():
    ex = executor({"terminal read": (1, {"ok": False, "error": {"code": "terminal_not_found", "message": "no such terminal"}})})
    with pytest.raises(ErroOrca) as e:
        Orca(executar=ex).ler("term_9")
    assert e.value.codigo == "terminal_not_found" and e.value.sumiu


def test_esperar_que_estoura_devolve_false():
    ex = executor({"terminal wait": (1, {"ok": False, "error": {"code": "timeout", "message": "timed out"}})})
    assert Orca(executar=ex).esperar("term_1", "tui-idle", 1000) == (False, "")


def test_esperar_ok_mas_nao_satisfeito_devolve_false():
    ex = executor({"terminal wait": ok({"wait": {"condition": "tui-idle", "satisfied": False, "blockedReason": "x"}})})
    assert Orca(executar=ex).esperar("term_1", "tui-idle", 1000) == (False, "x")
    ex = executor({"terminal wait": ok({"wait": {"condition": "tui-idle", "satisfied": True}})})
    assert Orca(executar=ex).esperar("term_1", "tui-idle", 1000) == (True, "")


def test_esperar_exit_em_terminal_sumido_conta_como_saida():
    ex = executor({"terminal wait": (1, {"ok": False, "error": {"code": "terminal_not_found", "message": ""}})})
    assert Orca(executar=ex).esperar("term_1", "exit", 1000) == (True, "")
    ex = executor({"terminal wait": (1, {"ok": False, "error": {"code": "terminal_handle_stale", "message": ""}})})
    assert Orca(executar=ex).esperar("term_1", "exit", 1000) == (True, "")
    assert Orca(executar=ex).esperar("term_1", "tui-idle", 1000) == (False, "")


def test_criar_worktree_tira_id_caminho_e_branch_do_create():
    ex = executor({"worktree create": ok({"worktree": {
        "id": "r1::X:/DEV/demo-app/vard-3-x", "path": "X:/DEV/demo-app/vard-3-x",
        "branch": "refs/heads/usuario/vard-3-x"}})})
    r = Orca(executar=ex).criar_worktree("X:/DEV/demo-app", "vard-3-x")
    assert r == {"worktree": "r1::X:/DEV/demo-app/vard-3-x", "caminho": "X:/DEV/demo-app/vard-3-x",
                 "branch": "usuario/vard-3-x"}
    assert "path:X:/DEV/demo-app" in ex.chamadas[0] and "--no-parent" in ex.chamadas[0]
    assert len(ex.chamadas) == 1


def test_criar_worktree_sem_branch_no_create_pergunta_ao_show():
    ex = executor({
        "worktree create": ok({"worktree": {"id": "r1::X:/wt/vard-3-x"}}),
        "worktree show": ok({"worktree": {"branch": "refs/heads/vard-3-x"}}),
    })
    r = Orca(executar=ex).criar_worktree("X:/DEV/demo-app", "vard-3-x")
    assert r == {"worktree": "r1::X:/wt/vard-3-x", "caminho": "X:/wt/vard-3-x", "branch": "vard-3-x"}


def test_criar_terminal_acha_o_handle_aninhado():
    ex = executor({"terminal create": ok({"terminal": {"handle": "term_abc"}})})
    assert Orca(executar=ex).criar_terminal("id:r1::X:/wt", "codex 'oi'; exit", "Vard #1", shell="powershell.exe") == "term_abc"
    assert "--shell" in ex.chamadas[0] and "powershell.exe" in ex.chamadas[0]


def test_ler_junta_tail_em_lista_e_devolve_cursor():
    ex = executor({"terminal read": ok({"tail": ["linha 1", "linha 2"], "nextCursor": 42})})
    leitura = Orca(executar=ex).ler("term_1", cursor=7)
    assert leitura.texto == "linha 1\nlinha 2" and leitura.proximo == 42
    args = ex.chamadas[0]
    assert args[args.index("--cursor") + 1] == "7"


def test_saida_que_nao_e_json():
    ex = executor({"terminal read": (2, "boom")})
    with pytest.raises(ErroOrca) as e:
        Orca(executar=ex).ler("t")
    assert e.value.codigo == "nao_json"


def test_orca_ausente_e_tempo_local():
    def nao_acha(args, timeout):
        raise FileNotFoundError(args[0])

    def demora(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    with pytest.raises(ErroOrca) as e:
        Orca(executar=nao_acha).status()
    assert e.value.codigo == "orca_ausente"
    with pytest.raises(ErroOrca) as e:
        Orca(executar=demora).status()
    assert e.value.codigo == "timeout_local" and e.value.e_timeout


def test_achar_e_todos():
    dados = {"a": [{"b": 1}, {"c": {"path": "x"}}], "path": "y"}
    assert orca_cli.achar(dados, "path") == "y"
    assert sorted(orca_cli.todos(dados, "path")) == ["x", "y"]


def _codigos() -> dict[str, int]:
    saida = {}
    for linha in (FX / "codigos.txt").read_text(encoding="utf-8").splitlines():
        nome, _, resto = linha.partition(" rc=")
        saida[nome.strip()] = int(resto.split()[0])
    return saida


def _com_fixtures(**por_comando):
    """por_comando: "terminal wait" -> nome do arquivo (sem .json); o rc vem de codigos.txt."""
    codigos = _codigos()
    return executor({cmd: (codigos.get(nome, 0), (FX / f"{nome}.json").read_text(encoding="utf-8"))
                     for cmd, nome in por_comando.items()})


def test_fixtures_reais_batem():
    orca = Orca(executar=_com_fixtures(**{"worktree create": "worktree-create", "worktree show": "worktree-show",
                                          "terminal create": "terminal-create", "terminal read": "terminal-read",
                                          "terminal wait": "wait-tui-idle-timeout"}))
    wt = orca.criar_worktree("X:/DEV/vard-app", "vard-0-spike")
    assert "::" in wt["worktree"] and wt["caminho"] == "X:/DEV/vard-app/vard-0-spike"
    assert wt["branch"] == "usuario/vard-0-spike"
    assert orca.criar_terminal(f"id:{wt['worktree']}", "x", "t").startswith("term_")
    assert "Tarefa 0 do Vard" in orca.ler("term_1").texto          # o pedido entrou pelo argumento do agente
    assert orca.esperar("term_1", "tui-idle", 1000) == (False, "")       # ok:false, code "timeout", rc 1


def test_fixtures_de_wait_ok_e_bloqueado_e_saida():
    for arquivo, condicao, esperado in [("wait-tui-idle-ok", "tui-idle", (True, "")),
                                        ("wait-tui-idle-bloqueado", "tui-idle", (False, "agent-trust-workspace")),
                                        ("wait-exit-depois-de-fechar", "exit", (True, "")),
                                        ("wait-exit-terminal-sumido", "exit", (True, "")),
                                        ("wait-exit-timeout", "exit", (False, ""))]:
        orca = Orca(executar=_com_fixtures(**{"terminal wait": arquivo}))
        assert orca.esperar("term_1", condicao, 1000) == esperado, arquivo


def test_fixture_do_repo_list_e_do_rm():
    orca = Orca(executar=_com_fixtures(**{"repo list": "repo-list", "worktree rm": "worktree-rm"}))
    assert orca.repos() == ["X:/exemplo/projeto-a", "X:/exemplo/projeto-b"]
    orca.remover_worktree("id:x", forcar=True)


def test_sumiu_so_vale_para_terminal():
    assert ErroOrca("terminal_handle_stale").sumiu and ErroOrca("terminal_not_found", "x").sumiu
    assert ErroOrca("x", "no such terminal").sumiu
    assert not ErroOrca("worktree_not_found", "worktree not found").sumiu
    ex = executor({"terminal wait": (1, {"ok": False, "error": {"code": "worktree_not_found", "message": "not found"}})})
    with pytest.raises(ErroOrca):
        Orca(executar=ex).esperar("term_1", "exit", 1000)


def test_oserror_e_cursor_estranho_nao_escapam():
    def sem_permissao(args, timeout):
        raise PermissionError("negado")

    with pytest.raises(ErroOrca) as e:
        Orca(executar=sem_permissao).status()
    assert e.value.codigo == "orca_inacessivel"
    ex = executor({"terminal read": ok({"tail": ["a"], "nextCursor": "abc"})})
    assert Orca(executar=ex).ler("t").proximo is None


@pytest.mark.parametrize("texto", ["", "   ", "\x1b", "\x1b[B", "\r", "a\x1bb"])
def test_enviar_recusa_tecla_solta(texto):
    ex = executor({})
    with pytest.raises(ErroOrca) as e:
        Orca(executar=ex).enviar("term_1", texto)
    assert e.value.codigo == "entrada_recusada" and ex.chamadas == []


def test_enviar_deixa_passar_resposta_de_texto():
    ex = executor({"terminal send": ok({"send": {"accepted": True}})})
    Orca(executar=ex).enviar("term_1", "y")
    assert "--text" in ex.chamadas[0] and "--enter" in ex.chamadas[0]
