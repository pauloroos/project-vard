import pytest
from fastapi.testclient import TestClient

from vard_reuniao import servico


class SessaoFalsa:
    def __init__(self):
        self.ativa, self.chamadas = False, []

    def iniciar(self):
        self.chamadas.append("iniciar")
        if self.ativa:
            return {"ok": False, "erro": "ja_ativa"}
        self.ativa = True
        return {"ok": True, "pasta": "2026-10-13_1500", "inicio": "2026-10-13T15:00:00"}

    def encerrar(self, motivo="pedido"):
        self.chamadas.append(("encerrar", motivo))
        if not self.ativa:
            return {"ok": False, "erro": "inativa"}
        self.ativa = False
        return {"ok": True, "pasta": "2026-10-13_1500", "duracao_s": 61, "falas": 3, "motivo": motivo}

    def diarizar_pasta_em_thread(self, nome):
        self.chamadas.append(("diarizar", nome))
        return {"ok": False, "erro": "rodando"} if getattr(self, "rodando", False) else {"ok": True}

    def status(self):
        return {"ativa": self.ativa, "pasta": "2026-10-13_1500" if self.ativa else None, "inicio": None, "duracao_s": 0, "falas": 0, "fila": 0, "dispositivos": {}}


@pytest.fixture
def cli(tmp_path):
    s = SessaoFalsa()
    app = servico.criar_app(s, raiz=tmp_path, diarizacao_estado=lambda: {"pronta": False, "motivo": "modelo não baixado"})
    return TestClient(app, base_url="http://127.0.0.1:4720"), s, tmp_path


def cli_pronta(tmp_path):
    s = SessaoFalsa()
    app = servico.criar_app(s, raiz=tmp_path, diarizacao_estado=lambda: {"pronta": True, "motivo": "", "modo": "community-1"})
    return TestClient(app, base_url="http://127.0.0.1:4720"), s


def test_saude_supervisor_nao_inicia_reuniao_nem_carrega_modelo(cli):
    import os
    c, sessao, _ = cli
    r = c.get("/saude")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "pid": os.getpid(), "versao": servico.VERSAO}
    assert not sessao.ativa and sessao.chamadas == []


def _reuniao(raiz, nome="2026-10-13_1500"):
    from vard_reuniao import armazenamento as arm
    p = raiz / nome
    p.mkdir()
    arm.Reuniao(pasta=nome, inicio="x").salvar(p)
    return p


def test_diarizar_503_com_o_motivo_quando_modelo_nao_esta_pronto(cli):
    c, s, raiz = cli
    _reuniao(raiz)
    r = c.post("/diarizar", json={"pasta": "2026-10-13_1500"})
    assert r.status_code == 503 and r.json()["motivo"] == "modelo não baixado" and ("diarizar", "2026-10-13_1500") not in s.chamadas


def test_diarizar_404_202_e_409(tmp_path):
    c, s = cli_pronta(tmp_path)
    assert c.post("/diarizar", json={"pasta": "2026-10-13_1500"}).status_code == 404
    assert c.post("/diarizar", json={"pasta": ".."}).status_code == 404
    _reuniao(tmp_path)
    r = c.post("/diarizar", json={"pasta": "2026-10-13_1500"})
    assert r.status_code == 202 and r.json()["ok"] is True and s.chamadas[-1] == ("diarizar", "2026-10-13_1500")
    s.rodando = True
    assert c.post("/diarizar", json={"pasta": "2026-10-13_1500"}).status_code == 409


def test_diarizar_recusa_origin(tmp_path):
    c, s = cli_pronta(tmp_path)
    assert c.post("/diarizar", json={"pasta": "x"}, headers={"Origin": "http://x"}).status_code == 403


def test_status_informa_modo_offline(cli, monkeypatch):
    c, _, _ = cli
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    assert c.get("/status").json()["offline"] is True
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    assert c.get("/status").json()["offline"] is False
    monkeypatch.delenv("HF_HUB_OFFLINE")
    assert c.get("/status").json()["offline"] is False


def test_status(cli):
    c, s, _ = cli
    r = c.get("/status")
    assert r.status_code == 200 and r.json()["ativa"] is False and r.json()["diarizacao"]["pronta"] is False


def test_iniciar_encerrar_409(cli):
    c, s, _ = cli
    assert c.post("/encerrar").status_code == 409
    assert c.post("/iniciar").status_code == 200 and c.post("/iniciar").status_code == 409
    r = c.post("/encerrar")
    assert r.status_code == 200 and r.json()["duracao_s"] == 61 and s.chamadas[-1] == ("encerrar", "pedido")


def test_post_com_origin_403_e_host_estranho_421(cli):
    c, s, _ = cli
    assert c.post("/iniciar", headers={"Origin": "http://127.0.0.1:4700"}).status_code == 403
    assert c.get("/status", headers={"Origin": "http://tauri.localhost"}).status_code == 403
    assert c.get("/status", headers={"Host": "evil"}).status_code == 421
    assert s.chamadas == []


def test_lista_e_reuniao(cli):
    from vard_reuniao import armazenamento as arm
    c, _, raiz = cli
    p = raiz / "2026-10-13_1500"
    p.mkdir()
    arm.Reuniao(pasta=p.name, inicio="2026-10-13T15:00:00", fim="2026-10-13T16:00:00", duracao_s=3600).salvar(p)
    arm.Transcricao(p).acrescentar(arm.Fala(1.0, 2.0, "eu", "Oi"))
    r = c.get("/lista")
    assert r.status_code == 200 and r.json()[0]["pasta"] == "2026-10-13_1500" and r.json()[0]["ata"] is False
    r = c.get("/reuniao/2026-10-13_1500")
    assert r.status_code == 200 and r.json()["falas"][0]["texto"] == "Oi" and r.json()["duracao_s"] == 3600
    assert c.get("/reuniao/..").status_code == 404 and c.get("/reuniao/2026-10-13_1600").status_code == 404


def test_falante_grava_e_reescreve(cli):
    from vard_reuniao import armazenamento as arm
    c, _, raiz = cli
    p = raiz / "2026-10-13_1500"
    p.mkdir()
    arm.Reuniao(pasta=p.name, inicio="x").salvar(p)
    arm.Transcricao(p).acrescentar(arm.Fala(1.0, 2.0, "outros", "Oi", falante=2))
    r = c.post("/falante", json={"pasta": "2026-10-13_1500", "n": 2, "nome": "Ana"})
    assert r.status_code == 200 and r.json()["falantes"] == {"2": "Ana"}
    assert "falante 2 (Ana): Oi" in (p / "transcricao.md").read_text(encoding="utf-8")
    assert c.post("/falante", json={"pasta": "2026-10-13_1500", "n": 0, "nome": ""}).status_code == 422
    assert c.post("/falante", json={"pasta": "x", "n": 1, "nome": "A"}).status_code == 404


def test_pasta_com_quebra_de_linha_final_e_recusada():
    assert servico.PASTA_RE.fullmatch("2026-10-13_1500\n") is None
    assert servico.PASTA_RE.fullmatch("2026-10-13_1500-2") is not None


def test_diarizar_recusa_a_pasta_da_reuniao_ativa(tmp_path):
    c, s = cli_pronta(tmp_path)
    _reuniao(tmp_path)
    s.ativa = True                      # a fake responde pasta 2026-10-13_1500 enquanto ativa
    r = c.post("/diarizar", json={"pasta": "2026-10-13_1500"})
    assert r.status_code == 409 and r.json() == {"ok": False, "erro": "ativa"}
    assert ("diarizar", "2026-10-13_1500") not in s.chamadas
    _reuniao(tmp_path, "2026-10-12_1000")           # outra pasta continua liberada
    assert c.post("/diarizar", json={"pasta": "2026-10-12_1000"}).status_code == 202


def test_status_informa_telemetria_desligada(cli, monkeypatch):
    c, _, _ = cli
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "0")
    assert c.get("/status").json()["telemetria_desligada"] is True
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "1")
    assert c.get("/status").json()["telemetria_desligada"] is False
    monkeypatch.delenv("PYANNOTE_METRICS_ENABLED")
    assert c.get("/status").json()["telemetria_desligada"] is False


def test_criar_app_fecha_reunioes_orfas_no_arranque(tmp_path):
    from vard_reuniao import armazenamento as arm

    p = tmp_path / "2026-10-13_1000"
    arm.Reuniao(pasta=p.name, inicio="2026-10-13T10:00:00").salvar(p)
    servico.criar_app(SessaoFalsa(), raiz=tmp_path, diarizacao_estado=lambda: {"pronta": False})
    assert arm.Reuniao.carregar(p).fim != ""
