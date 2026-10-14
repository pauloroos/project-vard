import datetime as dt
import json

import pytest

from vard import central

EV = {"tipo": "tarefa", "n": 3, "estado": "terminou", "resumo": "ok", "ferramenta": "codex"}
EV_REUNIAO = {"tipo": "reuniao", "estado": "ata_pronta", "duracao_s": 12, "pasta": "2026-10-13_1500",
              "resumo": "A ata da reunião de 13/10 está pronta."}


def test_registrar_guarda_id_hora_e_lido(tmp_path):
    arq = tmp_path / "avisos.jsonl"
    a = central.registrar(EV, arq)
    b = central.registrar({**EV, "estado": "falhou"}, arq)
    assert (a["id"], b["id"]) == (1, 2)
    assert a["lido"] is False and a["n"] == 3 and a["estado"] == "terminou" and a["resumo"] == "ok"
    assert dt.datetime.fromisoformat(a["hora"])            # hora é ISO local
    assert central.listar(arq) == [a, b]                   # mais novo por último
    assert arq.read_text(encoding="utf-8").splitlines()[0] == json.dumps(a, ensure_ascii=False)


def test_preflight_nao_e_guardado(tmp_path):
    arq = tmp_path / "avisos.jsonl"
    assert central.registrar({"tipo": "preflight", "marca": "abc"}, arq) is None
    assert central.listar(arq) == []


def test_reuniao_nao_tem_n(tmp_path):
    a = central.registrar(EV_REUNIAO, tmp_path / "avisos.jsonl")
    assert "n" not in a and a["tipo"] == "reuniao" and a["estado"] == "ata_pronta"


def test_arquivo_inexistente_lista_vazio(tmp_path):
    assert central.listar(tmp_path / "nada.jsonl") == []


def test_guarda_somente_os_ultimos_100(tmp_path):
    arq = tmp_path / "avisos.jsonl"
    for _ in range(105):
        central.registrar(EV, arq)
    lista = central.listar(arq)
    assert len(lista) == central.LIMITE == 100
    assert [a["id"] for a in lista] == list(range(6, 106))
    assert len(arq.read_text(encoding="utf-8").splitlines()) == 100
    assert central.registrar(EV, arq)["id"] == 106          # o id continua crescente depois do corte


def test_linha_corrompida_e_ignorada(tmp_path):
    arq = tmp_path / "avisos.jsonl"
    a = central.registrar(EV, arq)
    with arq.open("a", encoding="utf-8") as f:
        f.write("isto não é json\n")
        f.write('{"id": "x", "estado": "?"}\n')
        f.write("[1, 2]\n")
    b = central.registrar(EV, arq)
    assert [x["id"] for x in central.listar(arq)] == [a["id"], b["id"]]


def test_marcar_lidos_todos_e_so_os_escolhidos(tmp_path):
    arq = tmp_path / "avisos.jsonl"
    a = central.registrar(EV, arq)
    central.registrar(EV, arq)
    central.registrar(EV, arq)
    assert central.marcar_lidos([a["id"]], arq) == 2
    assert [x["lido"] for x in central.listar(arq)] == [True, False, False]
    assert central.marcar_lidos(None, arq) == 0             # None = todos
    assert all(x["lido"] for x in central.listar(arq))
    antes = arq.read_text(encoding="utf-8")                 # já todos lidos: nada é regravado
    assert central.marcar_lidos(None, arq) == 0
    assert arq.read_text(encoding="utf-8") == antes


def test_arquivo_padrao_monkeypatchavel(tmp_path, monkeypatch):
    monkeypatch.setattr(central, "ARQUIVO", tmp_path / "avisos.jsonl")
    central.registrar(EV)
    assert central.listar()[0]["n"] == 3 and central.ARQUIVO.exists()


def test_gravacao_e_atomica(tmp_path, monkeypatch):
    arq = tmp_path / "avisos.jsonl"
    a = central.registrar(EV, arq)
    antes = arq.read_text(encoding="utf-8")

    def falha(origem, destino):
        raise OSError("disco cheio")

    monkeypatch.setattr(central.os, "replace", falha)
    with pytest.raises(OSError):
        central.registrar(EV, arq)
    assert arq.read_text(encoding="utf-8") == antes          # o arquivo bom ficou intacto
    assert [x["id"] for x in central.listar(arq)] == [a["id"]]


def test_dados_trocados_apos_importacao(tmp_path, monkeypatch):
    for nome in ("primeira", "segunda"):
        pasta = tmp_path / nome
        monkeypatch.setenv("VARD_DADOS", str(pasta))
        assert central.listar() == []
        assert central.registrar(EV)["id"] == 1
        assert (pasta / "avisos.jsonl").exists()


@pytest.mark.parametrize("token,chat_id", [("", "42"), ("ficticio", ""), ("", "")])
def test_canal_incompleto_nao_envia(token, chat_id, monkeypatch):
    from vard import avisos, tarefas
    def proibido(*args, **kwargs):
        pytest.fail("canal incompleto não pode acessar a rede")
    monkeypatch.setattr(avisos.httpx, "post", proibido)
    monkeypatch.setattr(avisos, "publicar", lambda ev: True)
    monkeypatch.setattr(avisos.segredos, "carregar", lambda: {"telegram": {"token": token, "chat_id": chat_id}})
    monkeypatch.setattr(avisos, "_conf_oficina", lambda: {"telegram": "sempre"})
    assert avisos.avisar(tarefas.Tarefa(n=1, ferramenta="agente_remoto", repo="", pedido="oi", estado="terminou"))
    assert avisos.telegram("oi", token=token, chat_id=chat_id) is False


def test_aviso_le_canal_externo_na_chamada(tmp_path, monkeypatch):
    from vard import avisos, config, tarefas
    vistos = []
    monkeypatch.setattr(avisos, "publicar", lambda ev: True)
    monkeypatch.setattr(avisos, "telegram", lambda texto, **kw: vistos.append(kw) or True)
    monkeypatch.setattr(avisos, "_conf_oficina", lambda: {"telegram": "sempre"})
    for nome in ("primeira", "segunda"):
        pasta = tmp_path / nome
        pasta.mkdir()
        monkeypatch.setenv("VARD_CONFIG", str(pasta / "config"))
        config.arquivo_segredos().write_text(
            f'[telegram]\ntoken="ficticio-{nome}"\nchat_id="42"\n', encoding="utf-8")
        assert avisos.avisar(tarefas.Tarefa(n=1, ferramenta="pesquisa", repo="", pedido="oi", estado="terminou"))
    assert vistos == [{"token": "ficticio-primeira", "chat_id": "42"},
                      {"token": "ficticio-segunda", "chat_id": "42"}]
