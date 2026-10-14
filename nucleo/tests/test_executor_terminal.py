"""Executor terminal da oficina: git de verdade (tmp_path) e janela falsa (o popen é injetado)."""
import base64
import os
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from vard.executor_terminal import TerminalLocal
from vard.orca_cli import ErroOrca

COMANDO = "orca-cli tarefa '[Tarefa 7] Falar com o José — ação já, com aspas'"


def git(caminho, *args):
    p = subprocess.run(["git", "-C", str(caminho), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def repo_novo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "arquivo.txt").write_text("x", encoding="utf-8")
    git(repo, "add", "arquivo.txt")
    git(repo, "-c", "user.name=Vard", "-c", "user.email=vard@localhost", "commit", "-q", "-m", "primeiro")
    return repo


class JanelaFalsa:
    def __init__(self, args, pid):
        self.args = args
        self.pid = pid


def terminal(tmp_path, pid=None):
    """TerminalLocal com popen falso que guarda os args e devolve a janela (pid = o do pytest)."""
    abertos = []

    def popen(args):
        abertos.append(args)
        return JanelaFalsa(args, os.getpid() if pid is None else pid)

    return TerminalLocal(popen=popen, pasta_logs=tmp_path / "logs"), abertos


def test_criar_worktree_usa_git_de_verdade_a_partir_do_head(tmp_path):
    repo = repo_novo(tmp_path)
    t = TerminalLocal(pasta_logs=tmp_path / "logs")
    wt = t.criar_worktree(str(repo).replace("\\", "/"), "vard-7-falar-com-o-jose")
    assert wt == {"worktree": f"term::{str(repo).replace(chr(92), '/')}/vard-7-falar-com-o-jose",
                  "caminho": f"{str(repo).replace(chr(92), '/')}/vard-7-falar-com-o-jose",
                  "branch": "vard-7-falar-com-o-jose"}
    assert Path(wt["caminho"]).is_dir() and (Path(wt["caminho"]) / "arquivo.txt").is_file()
    assert "vard-7-falar-com-o-jose" in git(repo, "worktree", "list")


def test_criar_worktree_que_falla_vira_ErroOrca(tmp_path):
    t = TerminalLocal(pasta_logs=tmp_path / "logs")
    with pytest.raises(ErroOrca) as e:
        t.criar_worktree(str(tmp_path / "nao-existe"), "vard-1-x")
    assert e.value.codigo == "git_worktree" and e.value.mensagem


def test_remover_worktree_apaga_a_pasta_e_deixa_o_branch(tmp_path):
    repo = repo_novo(tmp_path)
    t = TerminalLocal(pasta_logs=tmp_path / "logs")
    wt = t.criar_worktree(str(repo).replace("\\", "/"), "vard-2-x")
    t.remover_worktree(f"id:{wt['worktree']}", forcar=True)
    assert not Path(wt["caminho"]).exists()
    assert "vard-2-x" not in git(repo, "worktree", "list")
    assert "vard-2-x" in git(repo, "branch", "--list")


def test_remover_worktree_por_path_sem_forcar(tmp_path):
    repo = repo_novo(tmp_path)
    t = TerminalLocal(pasta_logs=tmp_path / "logs")
    wt = t.criar_worktree(str(repo).replace("\\", "/"), "vard-3-y")
    t.remover_worktree(f"path:{wt['caminho']}")
    assert not Path(wt["caminho"]).exists()


def test_criar_terminal_abre_janela_visivel_com_log_no_titulo():
    t, abertos = terminal(Path(os.environ.get("TEMP", ".")), pid=1234)
    handle = t.criar_terminal("id:term::X:/wt/vard-7", COMANDO, "Vard #7 Ortografia")
    args = abertos[0]
    assert args[0] == "powershell.exe" and args[1] == "-NoProfile"
    assert args[2:4] == ["-OutputFormat", "Text"] and args[4] == "-EncodedCommand"
    script = base64.b64decode(args[5]).decode("utf-16-le")
    assert COMANDO in script                      # pedido com aspas e acentos chega inteiro
    assert "Set-Location -LiteralPath 'X:/wt/vard-7'" in script and "UTF8Encoding" in script
    assert "Tee-Object -FilePath" in script and "oficina-7.log" in script
    assert handle.startswith(f"term:1234:")
    assert handle.endswith(str(t.pasta_logs / "oficina-7.log"))


def test_criar_terminal_com_shell_diferente_e_titulo_sem_numero():
    t, abertos = terminal(Path(os.environ.get("TEMP", ".")))
    t.criar_terminal("id:term::X:/wt", "algo", "Vard #12 agy", shell="pwsh.exe")
    assert abertos[0][0] == "pwsh.exe"
    with pytest.raises(ErroOrca) as e:
        t.criar_terminal("id:term::X:/wt", "algo", "sem número")
    assert e.value.codigo == "titulo_invalido"


def test_ler_incremental_em_utf8(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    log = Path(handle.split(":", 3)[3])
    log.write_bytes("primeira linha\n".encode("utf-8"))
    r1 = t.ler(handle)
    assert r1.texto == "primeira linha" and r1.proximo == log.stat().st_size
    with log.open("ab") as f:
        f.write("olá, José\n".encode("utf-8"))
    r2 = t.ler(handle, cursor=r1.proximo)
    assert r2.texto == "olá, José" and r2.proximo == log.stat().st_size
    assert t.ler_tela(handle) == "primeira linha\nolá, José"


def test_ler_com_limite_de_linhas(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    log = Path(handle.split(":", 3)[3])
    log.write_bytes("\n".join(f"linha {i}" for i in range(200)).encode("utf-8"))
    assert t.ler(handle, limite=3).texto == "linha 197\nlinha 198\nlinha 199"
    assert t.ler_tela(handle).splitlines() == [f"linha {i}" for i in range(80, 200)]


def test_ler_tolerante_a_utf16_com_bom_do_tee(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    log = Path(handle.split(":", 3)[3])
    log.write_bytes("﻿saída do José\n".encode("utf-16-le"))     # BOM de verdade, como o PowerShell 5 grava
    r1 = t.ler(handle)
    assert r1.texto == "saída do José" and r1.proximo == log.stat().st_size
    with log.open("ab") as f:
        f.write("fim\n".encode("utf-16-le"))
    assert t.ler(handle, cursor=r1.proximo).texto == "fim"


def test_ler_sem_log_devolve_vazio(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    Path(handle.split(":", 3)[3]).unlink()
    assert t.ler(handle, cursor=0).texto == "" and t.ler_tela(handle) == ""


def test_esperar_exit_com_processo_vivo_nao_sai(tmp_path):
    t, _ = terminal(tmp_path, pid=os.getpid())       # pid do pytest: vivo, create_time certo
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    assert t.esperar(handle, "exit", 50) == (False, "")
    assert t.esperar(handle, "tui-idle", 50) == (False, "")       # não há TUI no modo terminal


def test_esperar_exit_com_pid_morto_ou_reaproveitado(tmp_path):
    vivo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    criacao = psutil.Process(vivo.pid).create_time()
    vivo.terminate()
    vivo.wait(timeout=10)
    t, _ = terminal(tmp_path)
    log = tmp_path / "logs" / "oficina-1.log"
    assert t.esperar(f"term:{vivo.pid}:{criacao}:{log}", "exit", 50) == (True, "")       # morreu
    assert t.esperar(f"term:{os.getpid()}:{criacao - 99}:{log}", "exit", 50) == (True, "")  # pid reaproveitado
    assert t.esperar("lixo", "exit", 50) == (True, "")
    assert t.esperar("lixo", "tui-idle", 50) == (False, "")


def test_enviar_e_sempre_recusado(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    with pytest.raises(ErroOrca) as e:
        t.enviar(handle, "sim, pode commitar")
    assert e.value.codigo == "sem_entrada"


def test_fechar_terminal_tolerante_a_ja_morto_e_handle_invalido(tmp_path):
    t, _ = terminal(tmp_path)
    handle = t.criar_terminal("id:term::X:/wt", COMANDO, "Vard #7 Ortografia")
    t.fechar_terminal(f"term:{os.getpid()}:{psutil.Process(os.getpid()).create_time() - 99}:x")  # pid reaproveitado
    t.fechar_terminal("term:999999999:1.0:x")                                                     # não existe
    t.fechar_terminal("lixo")                                                                     # handle inválido


def test_status_e_repos():
    t = TerminalLocal()
    assert t.status() == {"executor": "terminal"} and t.repos() == []


def test_literal_powershell_dobra_aspas_simples_e_curvas():
    from vard.executor_terminal import _lit
    assert _lit("X:/o'brien/\u2019x") == "'X:/o''brien/''x'"
