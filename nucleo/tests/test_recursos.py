"""Monitor de recursos do Vard (0.9.4 leve): prova da rota /recursos com processos falsos."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class ProcessoFalso:
    """Dublê de psutil.Process para testes sem dependência de processos reais."""

    def __init__(self, pid: int, nome: str = "vard.exe", rss_mb: float = 100.0, cpu: float = 5.0,
                 ppid: int = 0, comando: str = ""):
        self.pid = pid
        self._nome = nome
        self._rss = int(rss_mb * 1024 * 1024)
        self._cpu = cpu
        self._ppid = ppid
        self._comando = comando
        self._filhos: list[ProcessoFalso] = []

    def status(self) -> str:
        return "running"

    def name(self) -> str:
        return self._nome

    def cmdline(self) -> list[str]:
        return self._comando.split() if self._comando else [self._nome]

    def memory_info(self):
        class MemInfo:
            rss = self._rss
        return MemInfo()

    def cpu_percent(self, interval: float = 0.0) -> float:
        return self._cpu

    def ppid(self) -> int:
        return self._ppid

    def children(self, recursive: bool = False):
        if not recursive:
            return list(self._filhos)
        return [d for f in self._filhos for d in (f, *f.children(recursive=True))]


def _ligar(mapa: dict[int, "ProcessoFalso"]) -> dict[int, "ProcessoFalso"]:
    """Liga cada processo falso ao pai pelo ppid (como o psutil enxerga a árvore)."""
    for p in mapa.values():
        if p._ppid in mapa:
            mapa[p._ppid]._filhos.append(p)
    return mapa


@pytest.fixture
def pids_registrados(tmp_path: Path, monkeypatch):
    """Cria pasta pids/ fictícia e aponta config.pasta_dados() para ela."""
    pasta_pids = tmp_path / "pids"
    pasta_pids.mkdir()
    (pasta_pids / "widget.pid").write_text("1001\n", encoding="utf-8")
    (pasta_pids / "nucleo.pid").write_text("2001\n", encoding="utf-8")
    (pasta_pids / "voz.pid").write_text("3001\n", encoding="utf-8")

    from vard import config as modulo_config
    monkeypatch.setattr(modulo_config, "pasta_dados", lambda: tmp_path)
    return pasta_pids


@pytest.fixture
def processos_falsos(monkeypatch):
    """Substitui psutil.Process por dublês controláveis."""
    from vard import recursos as mod_recursos

    mapa = {
        1001: ProcessoFalso(1001, "vard.exe", rss_mb=200.0, cpu=3.0),
        2001: ProcessoFalso(2001, "python.exe", rss_mb=150.0, cpu=2.0),
        3001: ProcessoFalso(3001, "python.exe", rss_mb=500.0, cpu=1.0),
    }

    def processo_seguro(pid: int):
        return mapa.get(pid)

    monkeypatch.setattr(mod_recursos, "_processo_seguro", processo_seguro)
    monkeypatch.setattr(mod_recursos, "_vard_ancestral", lambda: [])
    monkeypatch.setattr(mod_recursos, "_vard_por_nome", lambda: [])
    monkeypatch.setattr(mod_recursos, "_esperar", lambda s: None)
    # Desativa detecção de XTTS e externos para isolar o teste
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: False)
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: [])
    return mapa


def test_coletar_recursos_retorna_componentes(pids_registrados, processos_falsos):
    from vard import recursos as mod_recursos

    resultado = mod_recursos.coletar_recursos()
    assert "componentes" in resultado
    assert "total_memoria_mb" in resultado
    nomes = [c["nome"] for c in resultado["componentes"]]
    assert "Widget" in nomes
    assert "Núcleo" in nomes
    assert "Voz" in nomes
    assert resultado["total_memoria_mb"] > 0


def test_coletar_recursos_sem_pids_registrados(tmp_path, monkeypatch):
    """Sem pasta pids/, devolve estrutura válida com componentes vazios."""
    from vard import config as modulo_config
    from vard import recursos as mod_recursos

    monkeypatch.setattr(modulo_config, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: False)
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: [])
    monkeypatch.setattr(mod_recursos, "_vard_ancestral", lambda: [])
    monkeypatch.setattr(mod_recursos, "_vard_por_nome", lambda: [])
    monkeypatch.setattr(mod_recursos, "_esperar", lambda s: None)

    resultado = mod_recursos.coletar_recursos()
    assert isinstance(resultado["componentes"], list)
    assert resultado["total_memoria_mb"] >= 0


def test_rota_recursos_no_servidor(pids_registrados, processos_falsos):
    """Prova integrada: GET /recursos devolve 200 com JSON válido."""
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as c:
        r = c.get("/recursos", headers={"host": "127.0.0.1"})
        assert r.status_code == 200
        dados = r.json()
        assert "componentes" in dados
        assert "total_memoria_mb" in dados

def test_le_pid_no_formato_real_do_vard_modo(tmp_path, monkeypatch):
    """vard-modo grava "PID|início" com BOM em ponte.pid, voz.pid etc."""
    from vard import config, recursos
    monkeypatch.setattr(config, "pasta_dados", lambda: tmp_path)
    pasta = tmp_path / "pids"
    pasta.mkdir()
    (pasta / "ponte.pid").write_text("﻿33344|2026-10-16T23:27:20.7078358-04:00\n", encoding="utf-8")
    (pasta / "voz.pid").write_text("73904|2026-10-16T23:31:52-04:00", encoding="utf-8")
    assert recursos._ler_pids_registrados() == {"ponte": [33344], "voz": [73904]}


# ------------------------------------------------------------------ app único (0.9.7)
# O vard.exe é pai do núcleo, da voz, da reunião e dos MCPs. A classificação vem do comando de
# cada processo; quem não se reconhece herda a do pai. Cada processo conta uma vez só.

PY = "C:/Exemplo/python.exe"


def _app_unico() -> dict[int, ProcessoFalso]:
    """Árvore fictícia como a do app único: vard.exe -> WebView2, núcleo (com MCPs e uma CLI), voz, reunião."""
    procs = [
        ProcessoFalso(10, "vard.exe", rss_mb=50, cpu=1.0, ppid=1),
        ProcessoFalso(11, "msedgewebview2.exe", rss_mb=100, cpu=2.0, ppid=10, comando="msedgewebview2.exe --embedded-browser-webview=1"),
        ProcessoFalso(12, "msedgewebview2.exe", rss_mb=150, cpu=1.0, ppid=11, comando="msedgewebview2.exe --type=renderer"),
        ProcessoFalso(20, "python.exe", rss_mb=10, cpu=0.0, ppid=10, comando=f"{PY} -X utf8 -m uvicorn server:app --port 4700"),
        ProcessoFalso(21, "conhost.exe", rss_mb=5, cpu=0.0, ppid=20, comando="conhost.exe 0x4"),
        ProcessoFalso(22, "python.exe", rss_mb=80, cpu=4.0, ppid=20, comando=f"{PY} -X utf8 -m uvicorn server:app --port 4700"),
        ProcessoFalso(23, "python.exe", rss_mb=70, cpu=0.5, ppid=22, comando=f"{PY} C:/Exemplo/nucleo/mesa_mcp.py"),
        ProcessoFalso(24, "python.exe", rss_mb=70, cpu=0.5, ppid=22, comando=f"{PY} C:/Exemplo/nucleo/memoria_mcp.py"),
        ProcessoFalso(25, "claude.exe", rss_mb=300, cpu=3.0, ppid=22, comando="claude -p --input-format stream-json"),
        ProcessoFalso(26, "python.exe", rss_mb=60, cpu=0.0, ppid=25, comando=f"{PY} C:/Exemplo/nucleo/oficina_mcp.py"),
        ProcessoFalso(30, "python.exe", rss_mb=10, cpu=0.0, ppid=10, comando=f"{PY} -X utf8 -m vard_voz"),
        ProcessoFalso(31, "python.exe", rss_mb=2600, cpu=6.0, ppid=30, comando=f"{PY} -X utf8 -m vard_voz"),
        ProcessoFalso(40, "python.exe", rss_mb=10, cpu=0.0, ppid=10, comando=f"{PY} -X utf8 -m vard_reuniao"),
        ProcessoFalso(41, "python.exe", rss_mb=70, cpu=0.5, ppid=40, comando=f"{PY} -X utf8 -m vard_reuniao"),
        ProcessoFalso(99, "explorer.exe", rss_mb=999, cpu=9.0, ppid=1, comando="explorer.exe"),
    ]
    return _ligar({p.pid: p for p in procs})


@pytest.fixture
def app_unico(tmp_path, monkeypatch):
    from vard import config as modulo_config
    from vard import recursos as mod_recursos
    mapa = _app_unico()
    monkeypatch.setattr(modulo_config, "pasta_dados", lambda: tmp_path)  # sem pids/ registrados
    monkeypatch.setattr(mod_recursos, "_vard_ancestral", lambda: [10])   # o núcleo é neto do vard.exe
    monkeypatch.setattr(mod_recursos, "_vard_por_nome", lambda: pytest.fail("varredura por nome com o app achado"))
    monkeypatch.setattr(mod_recursos, "_processo_seguro", lambda pid: mapa.get(pid))
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: False)
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: [])
    monkeypatch.setattr(mod_recursos, "_esperar", lambda s: None)
    monkeypatch.setattr(mod_recursos.psutil, "cpu_count", lambda logical=True: 1)
    return mapa


def _por_nome(resultado: dict) -> dict[str, dict]:
    return {c["nome"]: c for c in resultado["componentes"]}


def test_classifica_pelo_comando():
    from vard.recursos import classificar
    assert classificar("python.exe", ["python.exe", "-m", "uvicorn", "server:app", "--port", "4700"]) == "Núcleo"
    assert classificar("python.exe", ["python.exe", "C:/x/nucleo/mesa_mcp.py"]) == "MCPs"
    assert classificar("python.exe", ["python.exe", "C:\\x\\nucleo\\memoria_mcp.py"]) == "MCPs"
    assert classificar("windows-mcp.exe", ["windows-mcp.exe", "serve"]) == "MCPs"
    assert classificar("python.exe", ["python.exe", "-X", "utf8", "-m", "vard_voz"]) == "Voz"
    assert classificar("python.exe", ["python.exe", "-m", "vard_reuniao"]) == "Reunião"
    assert classificar("python.exe", ["python.exe", "C:/x/scripts/windows/bandeja.py"]) == "Bandeja"
    assert classificar("msedgewebview2.exe", ["msedgewebview2.exe", "--type=renderer"]) == "Widget"
    assert classificar("vard.exe", ["vard.exe"]) == "Widget"
    assert classificar("claude.exe", ["claude", "-p", "--input-format", "stream-json"]) == "Cérebro (CLI)"
    assert classificar("agy.exe", ["agy", "--input-format", "stream-json"]) == "Cérebro (CLI)"
    assert classificar("conhost.exe", ["conhost.exe", "0x4"]) is None   # herda a do pai


def test_app_unico_separa_cada_componente(app_unico):
    from vard import recursos as mod_recursos
    c = _por_nome(mod_recursos.coletar_recursos())
    assert sorted(c["Widget"]["pids"]) == [10, 11, 12]
    assert c["Widget"]["memoria_mb"] == 300.0
    # Núcleo: lançador, conhost e o processo real.
    assert sorted(c["Núcleo"]["pids"]) == [20, 21, 22]
    assert c["Núcleo"]["memoria_mb"] == 95.0
    # A CLI do cérebro (claude.exe) é filha do núcleo e tem linha própria, com os filhos dela (o MCP que ela abriu).
    assert sorted(c["Cérebro (CLI)"]["pids"]) == [25, 26]
    assert c["Cérebro (CLI)"]["memoria_mb"] == 360.0
    # MCPs: os que o núcleo abriu.
    assert sorted(c["MCPs"]["pids"]) == [23, 24]
    assert c["MCPs"]["memoria_mb"] == 140.0
    assert sorted(c["Voz"]["pids"]) == [30, 31]
    assert c["Voz"]["memoria_mb"] == 2610.0
    assert sorted(c["Reunião"]["pids"]) == [40, 41]


def test_app_unico_nao_conta_duas_vezes_nem_processo_de_fora(app_unico):
    from vard import recursos as mod_recursos
    r = mod_recursos.coletar_recursos()
    todos = [pid for comp in r["componentes"] for pid in comp["pids"]]
    assert len(todos) == len(set(todos))
    assert 99 not in todos   # explorer.exe não é do Vard
    soma = sum(p._rss for pid, p in app_unico.items() if pid != 99) / (1024 * 1024)
    assert r["total_memoria_mb"] == round(soma, 1)


def test_pid_registrado_da_voz_dentro_da_arvore_do_app_conta_uma_vez(app_unico, tmp_path):
    """O vard-modo pode ter adotado a voz (voz.pid) que o vard.exe subiu: a voz não duplica."""
    (tmp_path / "pids").mkdir()
    (tmp_path / "pids" / "voz.pid").write_text("31|2026-01-01T00:00:00-03:00", encoding="utf-8")
    from vard import recursos as mod_recursos
    c = _por_nome(mod_recursos.coletar_recursos())
    assert sorted(c["Voz"]["pids"]) == [30, 31]
    assert c["Voz"]["memoria_mb"] == 2610.0


def test_cpu_numa_amostragem_unica_e_dividida_pelos_nucleos(app_unico, monkeypatch):
    from vard import recursos as mod_recursos
    esperas: list[float] = []
    monkeypatch.setattr(mod_recursos, "_esperar", lambda s: esperas.append(s))
    monkeypatch.setattr(mod_recursos.psutil, "cpu_count", lambda logical=True: 4)
    c = _por_nome(mod_recursos.coletar_recursos())
    assert len(esperas) == 1 and esperas[0] <= 0.5   # uma espera para todos, não uma por processo
    assert c["Voz"]["cpu_percent"] == 1.5            # (0 + 6) / 4 núcleos, como o Gerenciador de Tarefas


def test_coletar_recursos_responde_rapido_com_sondas_lentas(app_unico, monkeypatch):
    """Sondas externas lentas rodam juntas e em paralelo com a amostragem de CPU."""
    import time as _time
    from vard import recursos as mod_recursos
    monkeypatch.setattr(mod_recursos, "_esperar", _time.sleep)
    monkeypatch.setattr(mod_recursos, "_detectar_xtts_carregado", lambda pids: (_time.sleep(0.6), True)[1])
    monkeypatch.setattr(mod_recursos, "_detectar_externos", lambda: (_time.sleep(0.6), [])[1])
    t0 = _time.monotonic()
    c = _por_nome(mod_recursos.coletar_recursos())
    assert _time.monotonic() - t0 < 1.0
    assert c["Voz"]["detalhes"] == "XTTS carregado"


def test_externos_com_portas_fechadas_respondem_rapido(monkeypatch):
    """No Windows, porta fechada no loopback leva ~2 s para recusar; a sonda não espera tudo isso."""
    import socket
    import time as _time
    from vard import recursos as mod_recursos

    def fechada() -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
        s.close()
        return porta

    monkeypatch.setattr(mod_recursos, "URL_OPENJARVIS", f"http://127.0.0.1:{fechada()}/health")
    monkeypatch.setattr(mod_recursos, "URL_LMSTUDIO", f"http://127.0.0.1:{fechada()}/v1/models")
    t0 = _time.monotonic()
    assert mod_recursos._detectar_externos() == []
    assert _time.monotonic() - t0 < 1.2


def test_sem_app_acima_do_nucleo_procura_o_widget_pelo_nome(app_unico, monkeypatch):
    """Instalação antiga (vard-modo): o núcleo não é filho do vard.exe; o widget é achado pelo nome."""
    from vard import recursos as mod_recursos
    monkeypatch.setattr(mod_recursos, "_vard_ancestral", lambda: [])
    monkeypatch.setattr(mod_recursos, "_vard_por_nome", lambda: [10])
    c = _por_nome(mod_recursos.coletar_recursos())
    assert sorted(c["Widget"]["pids"]) == [10, 11, 12]
    assert sorted(c["Voz"]["pids"]) == [30, 31]


def test_cli_do_supervisor_conta_no_cerebro_mesmo_com_outro_nome(app_unico):
    """O supervisor de CLIs do núcleo informa os PIDs vivos: valem mesmo se o executável tiver outro nome."""
    from vard import recursos as mod_recursos
    app_unico[25]._nome = "node.exe"
    c = _por_nome(mod_recursos.coletar_recursos(cli_pids=[25]))
    assert sorted(c["Cérebro (CLI)"]["pids"]) == [25, 26]
