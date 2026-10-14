import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def remoto_config(tmp_path):
    from vard import config
    pasta = config.pasta_config()
    pasta.mkdir(parents=True)
    (pasta / "remoto.toml").write_text(' [remoto]\ndestino = "usuario@exemplo.com"\nchave = "k"\ncomando = "sudo docker exec -i {container} agente --stdin"\ncontainer_prefixo = "agente-"\n', encoding="utf-8")
    return pasta

from vard import avisos, remoto, tarefas
from vard.consulta import ErroConsulta


def test_comando_ssh():
    assert remoto.comando_ssh("k", "usuario@exemplo.com", "x") == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-i", "k", "usuario@exemplo.com", "x"]
    assert "-i" not in remoto.comando_ssh("", "usuario@exemplo.com", "x")


def test_achar_container_com_exclusoes():
    nomes = "agente-abc\nagente-abc-adapter\nagente-hook-1\n"
    assert remoto.achar_container(nomes, "agente-", excluir=("adapter", "hook")) == "agente-abc"
    with pytest.raises(ErroConsulta):
        remoto.achar_container(nomes, "agente-")


def test_achar_container():
    assert remoto.achar_container("agente-abc\noutro-x\n", "agente-") == "agente-abc"
    for ruim in ("", "omniroute-x", "agente-a\nagente-b"):
        with pytest.raises(ErroConsulta):
            remoto.achar_container(ruim, "agente-")


def test_container_com_caractere_estranho_recusado():
    with pytest.raises(ErroConsulta, match="estranho"):
        remoto.achar_container("agente-abc;rm", "agente-")


def test_perguntar_manda_o_pedido_pelo_stdin_e_nunca_no_comando(remoto_config):
    chamadas = []

    def executar(args, **kw):
        chamadas.append((args, kw))
        if "docker ps" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="agente-abc\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="O card 42 está em revisão.\n", stderr="")

    pedido = "e o card 42? $(rm -rf /) 'aspas'"
    assert remoto.perguntar(pedido, executar=executar) == "O card 42 está em revisão."
    args, kw = chamadas[1]
    assert kw["input"] == pedido and "card 42" not in " ".join(args)
    assert kw["timeout"] == 180 == remoto.TIMEOUT_S
    assert args[-1] == "sudo docker exec -i agente-abc agente --stdin"
    assert chamadas[0][1]["stdin"] is subprocess.DEVNULL


def test_ssh_que_falha_vira_frase(remoto_config):
    def executar(args, **kw):
        return SimpleNamespace(returncode=255, stdout="", stderr="Permission denied (publickey).")

    with pytest.raises(ErroConsulta, match="Não consegui chegar em o agente remoto") as exc:
        remoto.perguntar("x", executar=executar)
    assert "ssh falhou" in str(exc.value)


def test_ssh_que_estoura_o_tempo_vira_frase(remoto_config):
    def executar(args, **kw):
        raise subprocess.TimeoutExpired(args, 180)

    with pytest.raises(ErroConsulta, match="demorou demais"):
        remoto.perguntar("x", executar=executar)


def test_executar_grava_resposta_e_resumo(loja, monkeypatch):
    monkeypatch.setattr(avisos, "resumo_curto", lambda texto, **k: "o card está em revisão")
    t = tarefas.nova("agente_remoto", "", "card 42?")
    u = remoto.executar(t.n, perguntar_fn=lambda p: "Oi ! O card 42 está em revisão desde ontem.")
    assert u.estado == "terminou" and u.resumo == "o card está em revisão"
    assert "desde ontem" in open(u.resultado, encoding="utf-8").read()


def test_executar_com_falha_vira_falhou(loja):
    def falha(p):
        raise ErroConsulta("A o agente remoto não respondeu: timeout do gateway")

    t = tarefas.nova("agente_remoto", "", "card 42?")
    u = remoto.executar(t.n, perguntar_fn=falha)
    assert u.estado == "falhou" and "gateway" in u.resumo


def test_executar_ja_reivindicada(loja):
    from vard.oficina import JaReivindicada
    t = tarefas.nova("agente_remoto", "", "x")
    tarefas.atualizar(t.n, estado="rodando")
    with pytest.raises(JaReivindicada):
        remoto.executar(t.n, perguntar_fn=lambda p: "nao deveria rodar")


def test_executar_descartada_no_meio_nao_ressuscita(loja, monkeypatch):
    monkeypatch.setattr(avisos, "resumo_curto", lambda texto, **k: "x")
    t = tarefas.nova("agente_remoto", "", "x")

    def responde_e_descarta(p):
        tarefas.atualizar(t.n, estado="descartada")
        return "resposta"

    u = remoto.executar(t.n, perguntar_fn=responde_e_descarta)
    assert u.estado == "descartada"


@pytest.mark.parametrize("conteudo", [None, '[remoto]\ncomando="agente --stdin"\n'])
def test_sem_config_nao_roda_nada(tmp_path, conteudo):
    from vard import config
    if conteudo is not None:
        config.pasta_config().mkdir(parents=True)
        config.arquivo_config("remoto.toml").write_text(conteudo, encoding="utf-8")
    with pytest.raises(ErroConsulta, match="O agente remoto não está configurado"):
        remoto.perguntar("x", executar=lambda *a, **k: pytest.fail("SSH não deveria rodar"))


def test_perfil_antigo_e_precedencia(remoto_config):
    from vard import config
    # Adaptador legado: somente leitura da seção [liv].
    config.arquivo_segredos().write_text('[liv]\nssh_chave="antiga"\nssh_destino="antigo@exemplo.com"\n', encoding="utf-8")
    arq = remoto_config / "remoto.toml"
    arq.write_text('[remoto]\ncomando="agente --stdin"\n', encoding="utf-8")
    chamadas = []
    def executar(args, **kw):
        chamadas.append((args, kw))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    assert remoto.perguntar("pedido", executar=executar) == "ok"
    assert chamadas[-1][0][-2:] == ["antigo@exemplo.com", "agente --stdin"]
    assert "antiga" in chamadas[-1][0]
    arq.write_text('[remoto]\ndestino="novo@exemplo.com"\nchave=""\ncomando="outro --stdin"\ntimeout_s=7\nnome="agente de teste"\n', encoding="utf-8")
    assert remoto.perguntar("pedido", executar=executar) == "ok"
    assert chamadas[-1][0][-2:] == ["novo@exemplo.com", "outro --stdin"]
    assert "-i" not in chamadas[-1][0] and chamadas[-1][1]["timeout"] == 7
    assert '[liv]' in config.arquivo_segredos().read_text(encoding="utf-8")


def test_secao_nova_vazia_nao_recupera_legado(remoto_config):
    from vard import config
    # Adaptador legado: [liv] só é lida quando [remoto] não existe.
    config.arquivo_segredos().write_text('[remoto]\n[liv]\nssh_destino="antigo@exemplo.com"\n', encoding="utf-8")
    (remoto_config / "remoto.toml").write_text('[remoto]\ncomando="agente --stdin"\n', encoding="utf-8")
    with pytest.raises(ErroConsulta, match="não está configurado"):
        remoto.perguntar("x", executar=lambda *a, **k: pytest.fail("SSH indevido"))


def test_erro_ssh_nao_reproduz_segredos(remoto_config):
    def executar(args, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="conteudo-sigiloso")
    with pytest.raises(ErroConsulta) as exc:
        remoto.perguntar("x", executar=executar)
    assert "conteudo-sigiloso" not in str(exc.value)



@pytest.mark.parametrize("saida", ["", "agente-a\nagente-b", "agente-a;comando"])
def test_descoberta_recusada_nao_executa_pedido(remoto_config, saida):
    chamadas = []
    def executar(args, **kw):
        chamadas.append(args)
        return SimpleNamespace(returncode=0, stdout=saida, stderr="")
    with pytest.raises(ErroConsulta):
        remoto.perguntar("pedido", executar=executar)
    assert len(chamadas) == 1 and chamadas[0][-1] == remoto.LISTAR


def test_trava_impede_segunda_conversa(remoto_config, monkeypatch):
    import threading
    from vard import config
    iniciou = threading.Event()
    liberar = threading.Event()
    erros = []
    def perguntar(pedido):
        iniciou.set()
        assert liberar.wait(3)
        return "ok"
    monkeypatch.setattr(remoto, "perguntar", perguntar)
    def primeira():
        try:
            remoto.perguntar_com_trava("primeiro")
        except Exception as exc:
            erros.append(exc)
    fio = threading.Thread(target=primeira)
    fio.start()
    try:
        assert iniciou.wait(3)
        with pytest.raises(TimeoutError):
            remoto.perguntar_com_trava("segundo", espera=0.05)
        assert (config.pasta_dados() / "remoto.lock").exists()
    finally:
        liberar.set()
        fio.join(3)
    assert not fio.is_alive() and not erros
