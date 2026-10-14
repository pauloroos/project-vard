import subprocess
import sys
from pathlib import Path

from vard import oficina, pesquisa, tarefas, trabalhador


def test_lancar_usa_intermediario_que_sai_para_nao_ser_descendente_do_mcp(loja):
    t = tarefas.nova("agente_remoto", "", "oi")
    visto = {}

    class Processo:
        pid = 4321

    def popen(args, **kw):
        visto.update(kw, args=args)
        return Processo()

    assert trabalhador.lancar(t.n, popen=popen) == 4321
    assert visto["args"] == [sys.executable, "-m", "vard.trabalhador", "--destacar", str(t.n)]
    assert visto["stdin"] is subprocess.DEVNULL and visto["stdout"] is subprocess.DEVNULL
    assert visto["creationflags"] & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    assert tarefas.obter(t.n).pid is None          # quem grava o pid é o próprio trabalhador


def test_comecar_nao_herda_stdout_nem_stdin(loja, tmp_path, monkeypatch):
    monkeypatch.setattr(trabalhador, "PASTA_LOGS", tmp_path / "logs")
    visto = {}

    class Processo:
        pid = 777

    def popen(args, **kw):
        visto.update(kw, args=args)
        return Processo()

    assert trabalhador._comecar(5, popen=popen) == 777
    assert visto["args"] == [sys.executable, "-m", "vard.trabalhador", "5"]
    assert visto["stdin"] is subprocess.DEVNULL and visto["stderr"] is subprocess.STDOUT
    assert visto["stdout"] is not None and visto["stdout"] is not sys.stdout
    assert Path(visto["stdout"].name).parent == tmp_path / "logs"
    assert visto["env"]["PYTHONUTF8"] == "1" and visto["env"]["VARD_SEM_VIGIA"] == "1"
    assert visto["close_fds"] is True and visto["cwd"] == str(trabalhador.REPO)


def test_executar_agente_chama_preparar(loja, monkeypatch):
    t = tarefas.nova("codex", "demo", "x")
    chamados = []
    monkeypatch.setattr(oficina, "preparar", lambda n, **kw: chamados.append(n))
    monkeypatch.setattr("vard.orca_cli.Orca", lambda: object())
    trabalhador.executar(t.n)
    assert chamados == [t.n]


def test_executar_pesquisa(loja, monkeypatch):
    t = tarefas.nova("pesquisa", "", "x")
    chamados = []
    monkeypatch.setattr(pesquisa, "executar", lambda n, **kw: chamados.append(n))
    trabalhador.executar(t.n)
    assert chamados == [t.n]


def test_erro_no_trabalho_vira_falhou(loja, monkeypatch):
    t = tarefas.nova("pesquisa", "", "x")
    tarefas.atualizar(t.n, estado="rodando")           # a pesquisa reivindicou e começou

    def explode(n, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(pesquisa, "executar", explode)
    trabalhador.executar(t.n)
    u = tarefas.obter(t.n)
    assert u.estado == "falhou" and "RuntimeError: boom" in u.erro


def test_tarefa_inexistente_nao_faz_nada(loja):
    trabalhador.executar(99)


def test_executar_grava_o_proprio_pid(loja, monkeypatch):
    import os
    t = tarefas.nova("codex", "demo", "x")
    monkeypatch.setattr(oficina, "preparar", lambda n, **kw: None)
    monkeypatch.setattr("vard.orca_cli.Orca", lambda: object())
    trabalhador.executar(t.n)
    assert tarefas.obter(t.n).pid == os.getpid()


def test_perder_a_reivindicacao_nao_derruba_a_tarefa_do_outro(loja, monkeypatch):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando", terminal="term_1")

    def preparar(n, **kw):
        raise oficina.JaReivindicada("já está sendo aberta por outro trabalhador")

    monkeypatch.setattr(oficina, "preparar", preparar)
    monkeypatch.setattr("vard.orca_cli.Orca", lambda: object())
    trabalhador.executar(t.n)
    assert tarefas.obter(t.n).estado == "rodando"


def test_erro_inesperado_so_falha_se_ainda_esta_preparando(loja, monkeypatch):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando")           # o dono já avançou
    monkeypatch.setattr(oficina, "preparar", lambda n, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("vard.orca_cli.Orca", lambda: object())
    trabalhador.executar(t.n)
    assert tarefas.obter(t.n).estado == "rodando"


def test_executar_remoto(loja, monkeypatch):
    from vard import remoto
    t = tarefas.nova("agente_remoto", "", "x")
    chamados = []
    monkeypatch.setattr(remoto, "executar", lambda n, **kw: chamados.append(n))
    trabalhador.executar(t.n)
    assert chamados == [t.n]


def test_executar_manha(loja, monkeypatch):
    from vard import manha
    t = tarefas.nova("manha", "", "x")
    chamados = []
    monkeypatch.setattr(manha, "executar", lambda n, **kw: chamados.append(n))
    trabalhador.executar(t.n)
    assert chamados == [t.n]


def test_executar_grava_pid_e_inicio_do_processo(loja, monkeypatch):
    t = tarefas.nova("pesquisa", "", "x")
    monkeypatch.setattr("vard.pesquisa.executar", lambda n, arq=None: None)
    trabalhador.executar(t.n)
    u = tarefas.obter(t.n)
    assert u.pid == __import__("os").getpid() and u.pid_inicio and u.pid_inicio > 0

def test_executar_ata_chama_o_ramo_da_reuniao(loja, monkeypatch):
    from vard import reuniao
    t = tarefas.nova("ata", "2026-10-13_1500", "ata")
    chamados = []
    monkeypatch.setattr(reuniao, "executar_ata", lambda n, arq=None: chamados.append((n, arq)))
    trabalhador.executar(t.n)
    assert chamados == [(t.n, None)]


def test_executar_ata_que_explode_vira_falhou(loja, monkeypatch):
    from vard import reuniao
    t = tarefas.nova("ata", "2026-10-13_1500", "ata")
    tarefas.atualizar(t.n, estado="rodando")

    def explode(n, arq=None):
        raise RuntimeError("quebrou")

    monkeypatch.setattr(reuniao, "executar_ata", explode)
    trabalhador.executar(t.n)
    assert tarefas.obter(t.n).estado == "falhou"


def test_lancar_passa_o_arquivo_de_tarefas_ao_filho(loja, tmp_path):
    t = tarefas.nova("agente_remoto", "", "oi")
    visto = {}

    class Processo:
        pid = 1

    def popen(args, **kw):
        visto.update(kw)
        return Processo()

    alvo = tmp_path / "t.json"
    trabalhador.lancar(t.n, arq=alvo, popen=popen)
    assert visto["env"]["VARD_TAREFAS_ARQUIVO"] == str(alvo)
    trabalhador.lancar(t.n, popen=popen)
    assert "VARD_TAREFAS_ARQUIVO" not in visto["env"] or visto["env"]["VARD_TAREFAS_ARQUIVO"] != str(alvo)


def test_filho_recebe_config_e_dados_do_ambiente(loja, tmp_path, monkeypatch):
    config_espaco = tmp_path / "minha config"
    dados_espaco = tmp_path / "meus dados"
    monkeypatch.setenv("VARD_CONFIG", str(config_espaco))
    monkeypatch.setenv("VARD_DADOS", str(dados_espaco))
    monkeypatch.setattr(trabalhador, "PASTA_LOGS", tmp_path / "logs")
    t = tarefas.nova("agente_remoto", "", "oi")
    vistos = []

    class Processo:
        pid = 1

    def popen(args, **kw):
        vistos.append(kw)
        return Processo()

    trabalhador._comecar(t.n, popen=popen)
    trabalhador.lancar(t.n, popen=popen)
    assert len(vistos) == 2
    for env in (vistos[0]["env"], vistos[1]["env"]):
        assert env["VARD_CONFIG"] == str(config_espaco)
        assert env["VARD_DADOS"] == str(dados_espaco)


def test_filho_recebe_as_pastas_mesmo_sem_variavel_no_pai(loja, tmp_path, monkeypatch):
    """O pai pode não ter as variáveis (serviço, atalho): o filho recebe as pastas resolvidas na hora."""
    base = tmp_path / "dados locais"                       # caminho com espaço de propósito
    monkeypatch.delenv("VARD_CONFIG", raising=False)
    monkeypatch.delenv("VARD_DADOS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(base))
    monkeypatch.setattr(trabalhador, "PASTA_LOGS", tmp_path / "logs")
    visto = {}

    class Processo:
        pid = 2

    def popen(args, **kw):
        visto.update(kw)
        return Processo()

    trabalhador.lancar(tarefas.nova("agente_remoto", "", "oi").n, popen=popen)
    assert visto["env"]["VARD_CONFIG"] == str(base / "rdl-vard" / "config")
    assert visto["env"]["VARD_DADOS"] == str(base / "rdl-vard")


def test_executar_delegada(loja, monkeypatch):
    from vard import delegada
    t = tarefas.nova("delegada", "", "x", agente="claude")
    chamados = []
    monkeypatch.setattr(delegada, "executar", lambda n, **kw: chamados.append((n, sorted(kw))))
    monkeypatch.setattr("vard.orca_cli.Orca", lambda: object())
    trabalhador.executar(t.n)
    assert chamados == [(t.n, ["arq", "orca", "repos"])]
