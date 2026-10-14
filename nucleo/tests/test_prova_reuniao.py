import importlib.util
from pathlib import Path

import pytest

import preflight

_spec = importlib.util.spec_from_file_location("prova_reuniao", Path(__file__).resolve().parent.parent.parent / "scripts" / "provas" / "prova-reuniao.py")
prova = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prova)


@pytest.fixture(autouse=True)
def _estado_limpo():
    prova.SALVAR_FALHOU.clear()
    preflight.LOOPBACK.update(pasta=None, salvar_falhou=False)
    yield
    prova.SALVAR_FALHOU.clear()
    preflight.LOOPBACK.update(pasta=None, salvar_falhou=False)


def _apagadas(monkeypatch):
    lista = []
    monkeypatch.setattr(prova.shutil, "rmtree", lambda p, **kw: lista.append(str(p)))
    monkeypatch.setattr(prova.reuniao_mod, "caminho_pasta", lambda n: Path("X") / n)
    return lista


def test_apagar_so_com_status_conhecido_e_inativo(monkeypatch):
    prova.SALVAR_FALHOU.clear()
    lista = _apagadas(monkeypatch)
    preflight.LOOPBACK["pasta"] = "2026-10-13_0777"
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: None)            # desconhecido: não apaga
    prova.apagar_pasta_de_teste()
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": True})  # ativa: não apaga
    prova.apagar_pasta_de_teste()
    assert not lista
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": False})
    prova.apagar_pasta_de_teste()
    assert len(lista) == 1 and preflight.LOOPBACK["pasta"] is None


def test_apagar_nao_apaga_se_o_encerramento_nao_salvou(monkeypatch):
    lista = _apagadas(monkeypatch)
    preflight.LOOPBACK["pasta"] = "2026-10-13_0777"
    prova.SALVAR_FALHOU[:] = [True]
    monkeypatch.setattr(preflight, "_reuniao_no_ar", lambda: {"ativa": False})
    prova.apagar_pasta_de_teste()
    assert not lista
    prova.SALVAR_FALHOU.clear()


def test_caminho_direto_409_salvar_mantem_a_pasta(monkeypatch, capsys):
    """Sem --ponte: /iniciar 200, /encerrar 409 "salvar", /status inativo. O finally do main não pode apagar a pasta."""
    lista = _apagadas(monkeypatch)
    monkeypatch.setattr(preflight.httpx, "get", lambda url, **kw: _Resp(200, {"ativa": False, "falas": 0}))
    monkeypatch.setattr(preflight.httpx, "post", lambda url, **kw: _Resp(409, {"ok": False, "erro": "salvar"})
                        if url.endswith("/encerrar") else _Resp(200, {"pasta": "2026-10-13_0555"}))
    monkeypatch.setattr(preflight, "_tocar_wav", lambda c: type("P", (), {"wait": lambda self, timeout=0: 0})())
    monkeypatch.setattr(preflight.time, "sleep", lambda s: None)
    monkeypatch.setattr(preflight, "reuniao_servico_no_ar", lambda: (True, "ok"))
    monkeypatch.setattr(preflight, "transcrever_wav_reuniao", lambda: ("", 0.0))
    monkeypatch.setattr(preflight, "avaliar_latencia_reuniao", lambda t, s: (True, "ok"))
    monkeypatch.setattr(prova.sys, "argv", ["prova-reuniao.py"])
    monkeypatch.setattr(prova.time, "monotonic", iter(range(0, 10_000, 20)).__next__)   # sai do laço de 15 s
    assert prova.main() == 1
    out = capsys.readouterr().out
    assert not lista and "sem salvar" in out and "2026-10-13_0555 mantida" in out
    assert preflight.LOOPBACK["pasta"] == "2026-10-13_0555"


class _Resp:
    def __init__(self, codigo=200, corpo=None):
        self.status_code, self._corpo = codigo, corpo or {}
        self.text = str(self._corpo)

    def json(self):
        return self._corpo
