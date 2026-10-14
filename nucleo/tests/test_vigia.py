import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.fakes import FakeOrca
from vard import manha, oficina, reuniao, tarefas, vigia

RAIZ = Path(__file__).resolve().parent.parent
CONF = oficina.carregar_conf(RAIZ / "config" / "oficina.toml")
AGORA = dt.datetime.now().astimezone()


@pytest.fixture(autouse=True)
def sem_manutencao_real(monkeypatch):
    """O laço chama a limpeza das reuniões: nos testes nunca toca nas pastas reais."""
    monkeypatch.setattr(reuniao, "manutencao_diaria", lambda: None)


def iso(minutos_atras: float) -> str:
    return (AGORA - dt.timedelta(minutes=minutos_atras)).isoformat(timespec="seconds")


def test_trava_ocupada_por_outro_processo_recusa(tmp_path):
    trava = tmp_path / "vigia.lock"
    codigo = ("import time; from pathlib import Path; from vard import vigia\n"
              f"fd = vigia.adquirir_trava(Path(r'{trava}'))\n"
              "print('pegou' if fd is not None else 'nao', flush=True); time.sleep(3)\n")
    p = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, text=True, cwd=RAIZ)
    try:
        assert p.stdout.readline().strip() == "pegou"
        assert vigia.adquirir_trava(trava) is None
    finally:
        p.wait(timeout=15)
    fd = vigia.adquirir_trava(trava)          # o outro saiu: o SO soltou a trava
    assert fd is not None
    os.close(fd)


def test_passo_avisa_uma_vez_so(loja):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando", terminal="term_1", iniciada_em=iso(5))
    ouvidos = []
    orca = FakeOrca(idle=True, tela="RESUMO: pronto.")
    vigia.passo(orca=orca, conf=CONF, agora=AGORA, avisar=ouvidos.append)
    vigia.passo(orca=orca, conf=CONF, agora=AGORA, avisar=ouvidos.append)
    assert [(a.n, a.estado) for a in ouvidos] == [(1, "terminou")]
    assert tarefas.obter(1).avisado == "terminou"


def test_volta_a_avisar_depois_de_responder(loja):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando", terminal="term_1", iniciada_em=iso(5))
    ouvidos = []
    vigia.passo(orca=FakeOrca(idle=True, tela="Posso rodar? (y/n)"), conf=CONF, agora=AGORA, avisar=ouvidos.append)
    oficina.responder(t.n, "pode", orca=FakeOrca())
    tarefas.atualizar(t.n, iniciada_em=iso(5))     # passou a carência
    vigia.passo(orca=FakeOrca(idle=True, tela="RESUMO: pronto."), conf=CONF, agora=AGORA, avisar=ouvidos.append)
    assert [a.estado for a in ouvidos] == ["esperando", "terminou"]


def test_trabalhador_morto_vira_falhou_e_avisa(loja):
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait(timeout=15)
    t = tarefas.nova("agente_remoto", "", "card?")
    tarefas.atualizar(t.n, estado="rodando", pid=morto.pid)
    ouvidos = []
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=ouvidos.append)
    assert tarefas.obter(t.n).estado == "falhou" and ouvidos[0].estado == "falhou"


def test_trabalhador_que_terminou_antes_de_morrer_nao_vira_falhou(loja):
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait(timeout=15)
    t = tarefas.nova("agente_remoto", "", "card?")
    tarefas.atualizar(t.n, estado="terminou", pid=morto.pid, resumo="em revisão")
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "terminou"


def test_erro_do_orca_nao_derruba_a_volta(loja):
    a = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(a.n, estado="rodando", terminal="term_1")
    b = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(b.n, estado="terminou", resumo="ok")
    ouvidos = []
    vigia.passo(orca=FakeOrca(falha="esperar"), conf=CONF, agora=AGORA, avisar=ouvidos.append)
    assert [x.n for x in ouvidos] == [b.n]


def test_aviso_que_explode_nao_repete(loja):
    t = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(t.n, estado="terminou", resumo="ok")

    def explode(x):
        raise RuntimeError("boom")

    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=explode)
    assert tarefas.obter(t.n).avisado == "terminou"


def test_iniciar_respeita_VARD_SEM_VIGIA(monkeypatch):
    monkeypatch.setenv("VARD_SEM_VIGIA", "1")
    assert vigia.iniciar() is None


def test_bloqueio_de_confianca_avisa_uma_vez_so(loja):
    t = tarefas.nova("codex", "demo", "x")
    tarefas.atualizar(t.n, estado="rodando", terminal="term_1", iniciada_em=iso(5))
    ouvidos = []
    orca = FakeOrca(idle=False, bloqueio="agent-trust-workspace", tela="Do you trust this folder?")
    for _ in range(3):
        vigia.passo(orca=orca, conf=CONF, agora=AGORA, avisar=ouvidos.append)
    assert [(a.estado, a.bloqueio) for a in ouvidos] == [("esperando", "agent-trust-workspace")]


def test_pesquisa_com_trabalhador_morto_falha(loja):
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait(timeout=15)
    t = tarefas.nova("pesquisa", "", "dólar?")
    tarefas.atualizar(t.n, estado="rodando", pid=morto.pid)
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "falhou"


def test_trabalhador_que_termina_durante_a_checagem_nao_vira_falhou(loja, monkeypatch):
    """A tarefa está 'rodando' na lista, mas o trabalhador grava 'terminou' antes de a vigia reler: sem a releitura
    (e o comparar-e-trocar) ela viraria falhou por cima do resultado."""
    t = tarefas.nova("agente_remoto", "", "card?")
    tarefas.atualizar(t.n, estado="rodando", pid=999999)

    def morre_gravando(_pid):
        tarefas.atualizar(t.n, estado="terminou", resumo="em revisão")
        return False

    monkeypatch.setattr(vigia, "trabalhador_vivo", lambda t, agora=None: not morre_gravando(t.pid))
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "terminou"


def test_falhou_do_trabalhador_morto_usa_compara_e_troca(loja, monkeypatch):
    """Mesmo com a releitura vendo 'rodando', se alguém grava entre ela e a escrita, a escrita da vigia perde."""
    t = tarefas.nova("agente_remoto", "", "card?")
    tarefas.atualizar(t.n, estado="rodando", pid=999999)
    velho = tarefas.obter(t.n)
    tarefas.atualizar(t.n, estado="terminou", resumo="em revisão")
    monkeypatch.setattr(vigia.tarefas, "obter", lambda n, arq=None: velho)
    vigia._trabalhador_sumiu(velho, None)
    assert tarefas.listar()[0].estado == "terminou"


def test_aviso_que_nao_chegou_repete_e_desiste_na_terceira(loja):
    t = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(t.n, estado="terminou", resumo="ok")
    vigia._tentativas.clear()
    chamadas = []

    def falha(x):
        chamadas.append(x.n)
        return False

    for _ in range(5):
        vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=falha)
    assert len(chamadas) == 3 and tarefas.obter(t.n).avisado == "terminou"


def test_aviso_entregue_na_segunda_tentativa(loja):
    t = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(t.n, estado="terminou", resumo="ok")
    vigia._tentativas.clear()
    respostas = iter([False, True])
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: next(respostas))
    assert tarefas.obter(t.n).avisado == ""
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: next(respostas))
    assert tarefas.obter(t.n).avisado == "terminou"


def test_avisado_nao_grava_se_o_estado_mudou_durante_o_aviso(loja):
    t = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(t.n, estado="terminou", resumo="ok")

    def usuario_descarta(x):
        tarefas.atualizar(x.n, estado="descartada")
        return True

    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=usuario_descarta)
    assert tarefas.obter(t.n).avisado == "" and tarefas.obter(t.n).estado == "descartada"


def esperar_ate(condicao, prazo=5.0):
    """Espera pela condição com prazo (não por um sleep fixo): não falha à toa sob carga."""
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return bool(condicao())


def test_laco_assume_a_trava_quando_o_dono_morre(tmp_path, monkeypatch):
    trava = tmp_path / "vigia.lock"
    dono = vigia.adquirir_trava(trava)
    monkeypatch.setattr(vigia, "TRAVA", trava)
    voltas = []
    monkeypatch.setattr(vigia, "passo", lambda **k: voltas.append(1))
    monkeypatch.setattr(manha, "agendar_se_preciso", lambda: None)
    monkeypatch.setattr(vigia, "INTERVALO_S", 0.05)
    vigia.PARAR.clear()
    th = vigia.threading.Thread(target=vigia._laco, args=(None, {}, None), daemon=True)
    th.start()
    time.sleep(0.3)
    assert voltas == []                       # o dono ainda segura: ninguém vigia aqui
    os.close(dono)                            # o dono morreu
    assert esperar_ate(lambda: voltas)        # assumiu
    vigia.parar()
    th.join(timeout=5)
    assert not th.is_alive()
    fd = vigia.adquirir_trava(trava)          # a saída soltou a trava
    assert fd is not None
    os.close(fd)


def test_laco_chama_a_agenda_da_manha_e_sobrevive_a_erro(tmp_path, monkeypatch):
    trava = tmp_path / "vigia.lock"
    monkeypatch.setattr(vigia, "TRAVA", trava)
    chamadas = []

    def agenda():
        chamadas.append(1)
        raise RuntimeError("agenda quebrou")

    monkeypatch.setattr(vigia, "passo", lambda **k: None)
    monkeypatch.setattr(manha, "agendar_se_preciso", agenda)
    monkeypatch.setattr(vigia, "INTERVALO_S", 0.05)
    vigia.PARAR.clear()
    fd = vigia.adquirir_trava(trava)
    th = vigia.threading.Thread(target=vigia._laco, args=(None, {}, fd), daemon=True)
    th.start()
    esperar_ate(lambda: len(chamadas) >= 2)
    vigia.parar()
    th.join(timeout=5)
    assert len(chamadas) >= 2 and not th.is_alive()      # o erro não derrubou o laço


def test_agenda_das_8h_nao_roda_sem_a_trava(tmp_path, monkeypatch):
    trava = tmp_path / "vigia.lock"
    dono = vigia.adquirir_trava(trava)        # outro processo é o dono da trava
    monkeypatch.setattr(vigia, "TRAVA", trava)
    chamadas = []
    monkeypatch.setattr(vigia, "passo", lambda **k: None)
    monkeypatch.setattr(manha, "agendar_se_preciso", lambda: chamadas.append(1))
    monkeypatch.setattr(vigia, "INTERVALO_S", 0.05)
    vigia.PARAR.clear()
    th = vigia.threading.Thread(target=vigia._laco, args=(None, {}, None), daemon=True)
    th.start()
    time.sleep(0.4)
    assert chamadas == []                     # sem a trava, a agenda não dispara a rotina
    vigia.parar()
    th.join(timeout=5)
    os.close(dono)


def test_pid_reaproveitado_nao_conta_como_trabalhador_vivo(loja):
    t = tarefas.nova("agente_remoto", "", "x")
    meu = vigia.psutil.Process().create_time()
    t = tarefas.atualizar(t.n, estado="rodando", pid=os.getpid(), pid_inicio=meu)
    assert vigia.trabalhador_vivo(t) is True
    t = tarefas.atualizar(t.n, pid_inicio=meu - 3600)         # o mesmo pid, mas outro processo (reboot)
    assert vigia.trabalhador_vivo(t) is False
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=AGORA, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "falhou"


def test_preparando_sem_pid_so_e_dado_como_morto_depois_de_5_minutos(loja):
    t = tarefas.nova("codex", "demo", "x")
    cedo = tarefas.hora(t.criada_em) + dt.timedelta(minutes=2)
    tarde = tarefas.hora(t.criada_em) + dt.timedelta(minutes=6)
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=cedo, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "preparando"
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=tarde, avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "falhou"


def test_rodando_sem_pid_nao_e_dado_como_morto(loja):
    t = tarefas.nova("agente_remoto", "", "x")
    tarefas.atualizar(t.n, estado="rodando")
    vigia.passo(orca=FakeOrca(), conf=CONF, agora=tarefas.hora(t.criada_em) + dt.timedelta(hours=1),
                avisar=lambda x: None)
    assert tarefas.obter(t.n).estado == "rodando"

def test_laco_chama_a_manutencao_diaria_e_sobrevive_a_erro(tmp_path, monkeypatch):
    from vard import reuniao
    trava = tmp_path / "vigia.lock"
    monkeypatch.setattr(vigia, "TRAVA", trava)
    chamadas = []

    def manutencao():
        chamadas.append(1)
        raise RuntimeError("limpeza quebrou")

    monkeypatch.setattr(vigia, "passo", lambda **k: None)
    monkeypatch.setattr(manha, "agendar_se_preciso", lambda: None)
    monkeypatch.setattr(reuniao, "manutencao_diaria", manutencao)
    monkeypatch.setattr(vigia, "INTERVALO_S", 0.05)
    vigia.PARAR.clear()
    fd = vigia.adquirir_trava(trava)
    th = vigia.threading.Thread(target=vigia._laco, args=(None, {}, fd), daemon=True)
    th.start()
    esperar_ate(lambda: len(chamadas) >= 2)
    vigia.parar()
    th.join(timeout=5)
    assert len(chamadas) >= 2 and not th.is_alive()


def test_manutencao_nao_roda_sem_a_trava(tmp_path, monkeypatch):
    from vard import reuniao
    trava = tmp_path / "vigia.lock"
    dono = vigia.adquirir_trava(trava)
    monkeypatch.setattr(vigia, "TRAVA", trava)
    chamadas = []
    monkeypatch.setattr(vigia, "passo", lambda **k: None)
    monkeypatch.setattr(manha, "agendar_se_preciso", lambda: None)
    monkeypatch.setattr(reuniao, "manutencao_diaria", lambda: chamadas.append(1))
    monkeypatch.setattr(vigia, "INTERVALO_S", 0.05)
    vigia.PARAR.clear()
    th = vigia.threading.Thread(target=vigia._laco, args=(None, {}, None), daemon=True)
    th.start()
    time.sleep(0.4)
    assert chamadas == []
    vigia.parar()
    th.join(timeout=5)
    os.close(dono)


def test_vigia_observa_login_da_delegada(loja, monkeypatch):
    t = tarefas.nova("delegada", "", "x", agente="claude")
    tarefas.atualizar(t.n, estado="esperando", bloqueio="login", terminal="term_1", avisado="esperando")
    monkeypatch.setattr("vard.trabalhador.lancar", lambda n, **k: None)
    vigia.passo(orca=FakeOrca(exit=True), conf={}, avisar=lambda t: True)
    assert tarefas.obter(t.n).estado == "preparando"


def test_trabalhador_vivo_carencia_conta_da_ultima_gravacao(loja):
    import dataclasses
    agora = dt.datetime.now().astimezone()
    t = tarefas.nova("delegada", "", "x", agente="claude")
    relancada = dataclasses.replace(tarefas.obter(t.n), criada_em=(agora - dt.timedelta(hours=1)).isoformat(),
                                    atualizada_em=agora.isoformat())
    assert vigia.trabalhador_vivo(relancada, agora) is True
    parada = dataclasses.replace(relancada, atualizada_em=(agora - dt.timedelta(minutes=6)).isoformat())
    assert vigia.trabalhador_vivo(parada, agora) is False


def test_passo_chama_a_limpeza_e_excecao_nao_impede_avisos(loja, monkeypatch):
    chamadas = []

    def limpa(**k):
        chamadas.append(k)
        raise RuntimeError("boom")
    monkeypatch.setattr("vard.delegada.limpar_antigas", limpa)
    t = tarefas.nova("agente_remoto", "", "x")
    tarefas.atualizar(t.n, estado="terminou")
    avisos_ = []
    vigia.passo(orca=FakeOrca(), conf={}, avisar=lambda t: avisos_.append(t.n) or True)
    assert len(chamadas) == 1 and avisos_ == [t.n]


def test_passo_excecao_numa_tarefa_nao_impede_o_aviso_de_outra(loja, monkeypatch):
    def quebra(t, **k):
        raise OSError("disco")
    monkeypatch.setattr("vard.delegada.observar_login", quebra)
    a = tarefas.nova("delegada", "", "x", agente="claude")
    tarefas.atualizar(a.n, estado="esperando", bloqueio="login", terminal="term_1")
    b = tarefas.nova("agente_remoto", "", "y")
    tarefas.atualizar(b.n, estado="terminou")
    avisos_ = []
    vigia.passo(orca=FakeOrca(), conf={}, avisar=lambda t: avisos_.append(t.n) or True)
    assert avisos_ == [b.n]
