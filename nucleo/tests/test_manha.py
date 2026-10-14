import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

from vard import manha, tarefas

RAIZ = Path(__file__).resolve().parent.parent
CONF = {"hora": "08:00", "ate": "11:00", "dias": [0, 1, 2, 3, 4], "perguntar_remoto": True, "pedido_remoto": "cards?"}
SEGUNDA = dt.datetime(2026, 10, 12, 8, 5)      # 12/10/2026 é segunda-feira


@pytest.fixture(autouse=True)
def _sem_google_real(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "oj"))


@pytest.mark.parametrize("agora,ultima,esperado", [
    (SEGUNDA, "", True),
    (SEGUNDA.replace(hour=7, minute=59), "", False),
    (SEGUNDA.replace(hour=11, minute=0), "", False),
    (SEGUNDA + dt.timedelta(days=5), "", False),                 # sábado
    (SEGUNDA, "2026-10-12", False),                               # já rodou hoje
    (SEGUNDA + dt.timedelta(days=1), "2026-10-12", True),
])
def test_deve_rodar(agora, ultima, esperado):
    assert manha.deve_rodar(agora, ultima, CONF) is esperado


def test_agendar_grava_o_dia_antes_e_nao_repete(loja, tmp_path):
    ultima = tmp_path / "manha-ultima.txt"
    lancados = []
    assert manha.agendar_se_preciso(SEGUNDA, conf=CONF, ultima_arq=ultima, lancar=lancados.append) == 1
    assert ultima.read_text(encoding="ascii") == "2026-10-12"
    assert manha.agendar_se_preciso(SEGUNDA, conf=CONF, ultima_arq=ultima, lancar=lancados.append) is None
    t = tarefas.obter(1)
    assert lancados == [1] and (t.ferramenta, t.origem) == ("manha", "agenda")


def test_escrever_feeds(tmp_path):
    origem = tmp_path / "n.toml"
    origem.write_text('[[feeds]]\nnome = "A"\nurl = "https://a.exemplo/rss"\n', encoding="utf-8")
    destino = tmp_path / "connectors" / "news_rss.json"
    assert manha.escrever_feeds(origem, destino) == 1
    assert json.loads(destino.read_text(encoding="utf-8")) == {"feeds": [{"name": "A", "url": "https://a.exemplo/rss"}]}
    origem.write_text('[[feeds]]\nnome = "B"\nurl = "http://b.exemplo/rss"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        manha.escrever_feeds(origem, destino)


def test_noticias_configuradas_sao_validas(tmp_path):
    origem = tmp_path / "noticias.toml"
    origem.write_text('[[feeds]]\nnome="A"\nurl="https://exemplo.com/a"\n[[feeds]]\nnome="B"\nurl="https://exemplo.com/b"\n[[feeds]]\nnome="C"\nurl="https://exemplo.com/c"\n', encoding="utf-8")
    assert manha.escrever_feeds(origem, tmp_path / "x.json") >= 3


def test_executar_junta_digest_e_remoto(loja):
    t = tarefas.nova("manha", "", "rotina da manhã (voz)")
    u = manha.executar(t.n, conf=CONF, gerar=lambda: "Bom dia. Duas reuniões hoje.",
                       perguntar_remoto=lambda p: "DEMO-12 está bloqueado.")
    texto = open(u.resultado, encoding="utf-8").read()
    assert u.estado == "terminou" and "Duas reuniões" in texto and "Do agente remoto: DEMO-12 está bloqueado." in texto


def test_executar_sem_digest_e_sem_remoto_falha(loja):
    def cai():
        raise httpx.ConnectError("x")

    def remoto_cai(p):
        raise RuntimeError("x")

    t = tarefas.nova("manha", "", "x")
    assert manha.executar(t.n, conf=CONF, gerar=cai, perguntar_remoto=remoto_cai).estado == "falhou"


def test_executar_sem_a_remoto_diz_que_nao_conseguiu(loja):
    def remoto_cai(p):
        raise RuntimeError("x")

    t = tarefas.nova("manha", "", "x")
    u = manha.executar(t.n, conf=CONF, gerar=lambda: "Bom dia.", perguntar_remoto=remoto_cai)
    texto = open(u.resultado, encoding="utf-8").read()
    assert u.estado == "terminou" and "Do agente remoto: não consegui falar com ele agora." in texto


def test_executar_so_uma_vez(loja):
    t = tarefas.nova("manha", "", "x")
    manha.executar(t.n, conf={**CONF, "perguntar_remoto": False}, gerar=lambda: "Bom dia.")
    with pytest.raises(manha.JaReivindicada):
        manha.executar(t.n, conf={**CONF, "perguntar_remoto": False}, gerar=lambda: "Bom dia.")


def test_montar_texto():
    assert manha.montar_texto("", "") == "Não consegui montar o resumo do dia."
    assert manha.montar_texto("Bom dia.", "  a\n b ") == "Bom dia.\n\nDo agente remoto: a b"


def test_sem_google_o_texto_avisa_e_segue():
    texto = manha.montar_texto("Bom dia. Manchete.", "x", google=False)
    assert "Agenda: ainda não conectada." in texto and "Manchete" in texto and "Do agente remoto: x" in texto


def test_google_conectado_olha_a_pasta_de_conectores(tmp_path):
    assert not manha.google_conectado(tmp_path)
    (tmp_path / "connectors").mkdir()
    (tmp_path / "connectors" / "gmail.json").write_text("{}", encoding="utf-8")
    assert manha.google_conectado(tmp_path)


def test_ultima_corrompida_vale_como_vazia(loja, tmp_path):
    ultima = tmp_path / "manha-ultima.txt"
    ultima.write_bytes(b"\xff\xfe\x00lixo")
    lancados = []
    assert manha.agendar_se_preciso(SEGUNDA, conf=CONF, ultima_arq=ultima, lancar=lancados.append) is not None
    assert ultima.read_text(encoding="ascii") == "2026-10-12"



def test_manha_sem_config_nao_dispara_integracoes(loja):
    assert manha.carregar_conf() == {}
    assert manha.agendar_se_preciso(SEGUNDA, lancar=lambda n: pytest.fail("Não deve agendar")) is None
    t = tarefas.nova("manha", "", "bom dia")
    u = manha.executar(t.n, gerar=lambda: pytest.fail("Não deve consultar"))
    assert u.estado == "terminou" and u.resumo == "A rotina da manhã não está configurada."


def test_config_manha_e_noticias_do_usuario(config_usuario, tmp_path):
    (config_usuario / "manha.toml").write_text('hora="09:00"\n', encoding="utf-8")
    assert manha.carregar_conf() == {"hora": "09:00"}
    (config_usuario / "noticias.toml").write_text('[[feeds]]\nnome="Demo"\nurl="https://exemplo.com/rss"\n', encoding="utf-8")
    assert manha.escrever_feeds(None, tmp_path / "feeds.json") == 1
